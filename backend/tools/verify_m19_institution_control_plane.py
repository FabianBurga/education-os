from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from playwright.sync_api import sync_playwright

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.security import create_access_token  # noqa: E402
from tools.acceptance.harness import (  # noqa: E402
    free_port,
    stop_process,
    wait_for_health,
)
from tools.verify_m16_full_system_acceptance import (  # noqa: E402
    _create_actor,
    _edge_path,
    _pick_tenant,
)

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)
RUNTIME_URL = os.getenv(
    "DATABASE_URL_PG",
    "postgresql://education_app:education_app_dev@localhost:5432/education_os",
)


def _start_m19_uvicorn(
    evidence_dir: Path,
) -> tuple[subprocess.Popen, str, Path]:
    """Start Uvicorn without an undrained subprocess PIPE."""
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    log_path = evidence_dir / "m19_uvicorn.log"

    with log_path.open(
        "w",
        encoding="utf-8",
        buffering=1,
    ) as log_file:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "info",
                "--no-access-log",
            ],
            cwd=str(BACKEND_ROOT),
            env=os.environ.copy(),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )

    wait_for_health(base_url, process)
    return process, base_url, log_path


def _request(
    base_url: str,
    path: str,
    *,
    token: str | None = None,
    method: str = "GET",
    payload: dict | None = None,
) -> tuple[int, object]:
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        f"{base_url}{path}",
        headers=headers,
        data=data,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8")
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                return response.status, json.loads(raw)
            return response.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def _assert_schema() -> None:
    required_tables = {
        "institution_control_state",
        "institution_policy_controls",
        "institution_control_changes",
    }
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        assert cur.fetchone() == ("0018_m19",)

        cur.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c
            WHERE c.relname = ANY(%s)
            """,
            (list(required_tables),),
        )
        rows = {row[0]: (row[1], row[2]) for row in cur.fetchall()}
        assert set(rows) == required_tables, rows
        for table, flags in rows.items():
            assert flags == (True, True), (table, flags)

        cur.execute(
            """
            SELECT key
            FROM permissions
            WHERE key IN ('control_plane.view', 'control_plane.manage')
            ORDER BY key
            """
        )
        assert {row[0] for row in cur.fetchall()} == {
            "control_plane.view",
            "control_plane.manage",
        }

        cur.execute(
            """
            SELECT tgname
            FROM pg_trigger
            WHERE tgname = ANY(%s)
              AND NOT tgisinternal
            """,
            (
                [
                    "trg_control_changes_immutable",
                    "trg_control_changes_no_truncate",
                ],
            ),
        )
        assert {row[0] for row in cur.fetchall()} == {
            "trg_control_changes_immutable",
            "trg_control_changes_no_truncate",
        }

    print("M19 schema + permissions + FORCE RLS + immutable changes: PASSED")


def _bootstrap(ctx: dict) -> dict[str, dict]:
    suffix = uuid4().hex[:8].upper()
    actors: dict[str, dict] = {}
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        for actor_key, role_key in (
            ("admin", "SYSTEM_ADMIN"),
            ("rector", "RECTOR"),
            ("teacher", "TEACHER"),
        ):
            actors[actor_key] = _create_actor(
                cur,
                organization_id=ctx["organization_id"],
                institution_id=ctx["institution_id"],
                actor_key=f"m19-{actor_key}",
                role_key=role_key,
                profile_kind="staff",
                suffix=suffix,
            )
        conn.commit()

    for actor in actors.values():
        actor["token"] = create_access_token(
            user_id=UUID(str(actor["user_id"])),
            organization_id=UUID(str(ctx["organization_id"])),
            institution_id=UUID(str(ctx["institution_id"])),
        )
    return actors


def _find_capability(items: list[dict], key: str) -> dict:
    for item in items:
        if item["capability_key"] == key:
            return item
    raise AssertionError(f"Required capability missing: {key}")


def _drain_event_pipeline(base_url: str, token: str) -> None:
    drained = False
    for _attempt in range(20):
        status, body = _request(
            base_url,
            "/api/v1/event-platform/pipeline/run?limit=5000",
            token=token,
            method="POST",
        )
        assert status == 200 and isinstance(body, dict), (status, body)
        if body["ingested"] == 0 and body["projected"] == 0:
            drained = True
            break
    assert drained, "Event pipeline did not drain within 20 batches"


def _verify_permissions_and_control_flow(
    base_url: str,
    actors: dict[str, dict],
) -> dict[str, object]:
    token = {key: actor["token"] for key, actor in actors.items()}

    for actor_key, expected in (
        ("admin", 200),
        ("rector", 200),
        ("teacher", 403),
    ):
        status, body = _request(
            base_url,
            "/api/v1/control-plane/summary",
            token=token[actor_key],
        )
        assert status == expected, (actor_key, status, body)

    for actor_key in ("admin", "rector"):
        status, bootstrap = _request(
            base_url,
            "/api/v1/ui/bootstrap",
            token=token[actor_key],
        )
        assert status == 200 and isinstance(bootstrap, dict)
        assert "control_plane.view" in bootstrap["permissions"]
        if actor_key == "admin":
            assert "control_plane.manage" in bootstrap["permissions"]
        else:
            assert "control_plane.manage" not in bootstrap["permissions"]

    status, capabilities = _request(
        base_url,
        "/api/v1/control-plane/capabilities",
        token=token["admin"],
    )
    assert status == 200 and isinstance(capabilities, list)
    finance = _find_capability(capabilities, "finance.billing")
    original_enabled = bool(finance["enabled"])

    status, denied = _request(
        base_url,
        "/api/v1/control-plane/capabilities/finance.billing",
        token=token["rector"],
        method="PUT",
        payload={
            "enabled": not original_enabled,
            "reason": "Rector must not manage capabilities",
        },
    )
    assert status == 403, denied

    status, managed = _request(
        base_url,
        "/api/v1/control-plane/capabilities/finance.billing",
        token=token["admin"],
        method="PUT",
        payload={
            "enabled": not original_enabled,
            "reason": "M19 verifier capability control",
        },
    )
    assert status == 200 and isinstance(managed, dict), managed
    assert managed["enabled"] is (not original_enabled)
    assert managed["managed_enabled"] is (not original_enabled)
    assert managed["drift"] is False
    first_revision = int(managed["managed_revision"])

    status, external = _request(
        base_url,
        "/api/v1/finance/capability",
        token=token["admin"],
        method="PUT",
        payload={"enabled": original_enabled},
    )
    assert status == 200 and isinstance(external, dict), external
    assert external["enabled"] is original_enabled

    status, drifted = _request(
        base_url,
        "/api/v1/control-plane/capabilities",
        token=token["admin"],
    )
    assert status == 200 and isinstance(drifted, list)
    finance_drift = _find_capability(drifted, "finance.billing")
    assert finance_drift["drift"] is True

    print("M19 verifier phase: drift summary")
    drift_started = time.perf_counter()
    status, drift_summary = _request(
        base_url,
        "/api/v1/control-plane/summary",
        token=token["admin"],
    )
    drift_elapsed = time.perf_counter() - drift_started
    print(f"M19 drift summary latency: {drift_elapsed:.3f}s")
    assert drift_elapsed < 5.0, (
        f"Control Plane drift summary exceeded 5s budget: "
        f"{drift_elapsed:.3f}s"
    )
    assert status == 200 and isinstance(drift_summary, dict)
    assert drift_summary["health"]["capability_drift_count"] >= 1
    assert drift_summary["health"]["status"] == "ATTENTION"

    status, reconciled = _request(
        base_url,
        "/api/v1/control-plane/capabilities/finance.billing",
        token=token["admin"],
        method="PUT",
        payload={
            "enabled": original_enabled,
            "reason": "Reconcile external capability drift",
        },
    )
    assert status == 200 and isinstance(reconciled, dict)
    assert reconciled["enabled"] is original_enabled
    assert reconciled["managed_enabled"] is original_enabled
    assert reconciled["drift"] is False
    assert int(reconciled["managed_revision"]) > first_revision

    policy_key = "pilot.notifications.guardrail"
    status, policy_v1 = _request(
        base_url,
        f"/api/v1/control-plane/policies/{policy_key}",
        token=token["admin"],
        method="PUT",
        payload={
            "enabled": True,
            "policy": {
                "channel": "IN_APP",
                "max_per_hour": 5,
            },
            "reason": "Create M19 pilot policy",
        },
    )
    assert status == 200 and isinstance(policy_v1, dict), policy_v1
    assert policy_v1["policy_version"] == 1

    status, policy_v2 = _request(
        base_url,
        f"/api/v1/control-plane/policies/{policy_key}",
        token=token["admin"],
        method="PUT",
        payload={
            "enabled": True,
            "policy": {
                "channel": "IN_APP",
                "max_per_hour": 6,
            },
            "reason": "Revise M19 pilot policy",
        },
    )
    assert status == 200 and isinstance(policy_v2, dict), policy_v2
    assert policy_v2["policy_version"] == 2
    assert int(policy_v2["managed_revision"]) > int(
        reconciled["managed_revision"]
    )

    status, denied_policy = _request(
        base_url,
        "/api/v1/control-plane/policies/rector.forbidden.change",
        token=token["rector"],
        method="PUT",
        payload={
            "enabled": True,
            "policy": {"value": 1},
            "reason": "Rector must not manage policies",
        },
    )
    assert status == 403, denied_policy

    status, secret_rejected = _request(
        base_url,
        "/api/v1/control-plane/policies/pilot.secret.guardrail",
        token=token["admin"],
        method="PUT",
        payload={
            "enabled": True,
            "policy": {"api_key": "must-not-be-stored"},
            "reason": "Verify secret rejection",
        },
    )
    assert status == 422, secret_rejected

    status, changes = _request(
        base_url,
        "/api/v1/control-plane/changes?limit=50",
        token=token["rector"],
    )
    assert status == 200 and isinstance(changes, list)
    assert len(changes) >= 4
    revisions = [int(item["revision"]) for item in changes]
    assert revisions == sorted(revisions, reverse=True)
    change_types = {item["change_type"] for item in changes}
    assert {"CAPABILITY", "POLICY"}.issubset(change_types)

    _drain_event_pipeline(base_url, token["admin"])

    print("M19 verifier phase: converged health summary")
    healthy_started = time.perf_counter()
    status, healthy = _request(
        base_url,
        "/api/v1/control-plane/summary",
        token=token["admin"],
    )
    healthy_elapsed = time.perf_counter() - healthy_started
    print(f"M19 converged summary latency: {healthy_elapsed:.3f}s")
    assert healthy_elapsed < 5.0, (
        f"Control Plane converged summary exceeded 5s budget: "
        f"{healthy_elapsed:.3f}s"
    )
    assert status == 200 and isinstance(healthy, dict)
    assert healthy["health"]["unledgered_outbox_count"] == 0
    assert healthy["health"]["projection_lag"] == 0
    assert healthy["health"]["capability_drift_count"] == 0
    assert healthy["health"]["status"] == "HEALTHY"
    assert healthy["health"]["database_revision"] == "0018_m19"

    print(
        "M19 role boundaries + capability drift + policy governance "
        "+ event health: PASSED"
    )
    return {
        "policy_key": policy_key,
        "original_finance_enabled": original_enabled,
        "final_revision": int(healthy["control_revision"]),
    }


def _verify_browser(
    base_url: str,
    token: str,
    evidence_dir: Path,
) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=_edge_path(),
            headless=True,
        )
        context = browser.new_context()
        page = context.new_page()
        page.goto(f"{base_url}/app/", wait_until="networkidle")
        page.evaluate(
            "(token) => sessionStorage.setItem('education_os_access_token', token)",
            token,
        )
        page.goto(
            f"{base_url}/app/workspace/control-plane",
            wait_until="networkidle",
        )
        page.get_by_test_id("workspace-control-plane").wait_for(
            state="visible",
            timeout=15_000,
        )
        workspace_shot = evidence_dir / "m19_control_plane_workspace_edge.png"
        page.screenshot(path=str(workspace_shot), full_page=True)

        page.get_by_test_id("legacy-control-plane").click()
        page.wait_for_url("**/api/v1/control-plane/dashboard")
        page.locator("#metrics .metric").first.wait_for(
            state="visible",
            timeout=15_000,
        )
        dashboard_shot = evidence_dir / "m19_control_plane_dashboard_edge.png"
        page.screenshot(path=str(dashboard_shot), full_page=True)

        context.close()
        browser.close()

    print(f"M19 browser workspace screenshot={workspace_shot}")
    print(f"M19 browser dashboard screenshot={dashboard_shot}")
    print("M19 real Microsoft Edge Control Plane acceptance: PASSED")


def _verify_database_semantics(
    ctx: dict,
    actors: dict[str, dict],
    result: dict[str, object],
) -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT revision
            FROM institution_control_state
            WHERE institution_id = %s
            """,
            (ctx["institution_id"],),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == result["final_revision"]
        assert row[0] >= 4

        cur.execute(
            """
            SELECT policy_version, policy_json
            FROM institution_policy_controls
            WHERE institution_id = %s
              AND policy_key = %s
            """,
            (ctx["institution_id"], result["policy_key"]),
        )
        policy = cur.fetchone()
        assert policy is not None
        assert policy[0] == 2
        assert policy[1]["max_per_hour"] == 6

        cur.execute(
            """
            SELECT COUNT(*)
            FROM institution_control_changes
            WHERE institution_id = %s
            """,
            (ctx["institution_id"],),
        )
        assert cur.fetchone()[0] >= 4

        cur.execute(
            """
            SELECT COUNT(*)
            FROM event_ledger
            WHERE institution_id = %s
              AND event_type IN (
                  'institution.capability.changed',
                  'institution.policy.changed'
              )
            """,
            (ctx["institution_id"],),
        )
        assert cur.fetchone()[0] >= 4

    try:
        with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE institution_control_changes
                SET reason = 'illegal mutation'
                WHERE institution_id = %s
                """,
                (ctx["institution_id"],),
            )
            conn.commit()
    except psycopg.Error as exc:
        assert "append-only" in str(exc)
    else:
        raise AssertionError(
            "institution_control_changes UPDATE unexpectedly succeeded"
        )

    try:
        with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE institution_control_changes")
            conn.commit()
    except psycopg.Error as exc:
        assert "append-only" in str(exc)
    else:
        raise AssertionError(
            "institution_control_changes TRUNCATE unexpectedly succeeded"
        )

    with psycopg.connect(RUNTIME_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              set_config('app.organization_id', %s, false),
              set_config('app.institution_id', %s, false),
              set_config('app.user_id', %s, false)
            """,
            (
                str(ctx["organization_id"]),
                str(ctx["institution_id"]),
                str(actors["teacher"]["user_id"]),
            ),
        )
        cur.execute(
            """
            SELECT
              education_os_control_plane_has_permission('control_plane.view'),
              education_os_control_plane_has_permission('control_plane.manage')
            """
        )
        assert cur.fetchone() == (False, False)
        cur.execute("SELECT COUNT(*) FROM institution_policy_controls")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM institution_control_changes")
        assert cur.fetchone()[0] == 0

    with psycopg.connect(RUNTIME_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              set_config('app.organization_id', %s, false),
              set_config('app.institution_id', %s, false),
              set_config('app.user_id', %s, false)
            """,
            (
                str(ctx["organization_id"]),
                str(ctx["institution_id"]),
                str(actors["rector"]["user_id"]),
            ),
        )
        cur.execute(
            """
            SELECT
              education_os_control_plane_has_permission('control_plane.view'),
              education_os_control_plane_has_permission('control_plane.manage')
            """
        )
        assert cur.fetchone() == (True, False)
        cur.execute(
            """
            SELECT COUNT(*)
            FROM institution_policy_controls
            WHERE policy_key = %s
            """,
            (result["policy_key"],),
        )
        assert cur.fetchone()[0] == 1

    try:
        with psycopg.connect(RUNTIME_URL) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  set_config('app.organization_id', %s, false),
                  set_config('app.institution_id', %s, false),
                  set_config('app.user_id', %s, false)
                """,
                (
                    str(ctx["organization_id"]),
                    str(ctx["institution_id"]),
                    str(actors["rector"]["user_id"]),
                ),
            )
            cur.execute(
                """
                INSERT INTO institution_policy_controls (
                    id,
                    organization_id,
                    institution_id,
                    policy_key,
                    enabled,
                    policy_json,
                    policy_version,
                    created_at,
                    updated_at
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    'rector.direct.write',
                    true,
                    '{}'::jsonb,
                    1,
                    NOW(),
                    NOW()
                )
                """,
                (
                    uuid4(),
                    ctx["organization_id"],
                    ctx["institution_id"],
                ),
            )
            conn.commit()
    except psycopg.Error:
        pass
    else:
        raise AssertionError(
            "Rector unexpectedly received direct Control Plane write access"
        )

    print(
        "M19 revision lineage + canonical events + immutable history "
        "+ direct RLS: PASSED"
    )


def main() -> None:
    _assert_schema()
    ctx = _pick_tenant()
    actors = _bootstrap(ctx)

    evidence_dir = Path(
        os.getenv(
            "M19_EVIDENCE_DIR",
            str(Path.home() / "Downloads" / "Education_OS_M19_Evidence"),
        )
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)

    process, base_url, server_log = _start_m19_uvicorn(evidence_dir)
    print(f"M19 actual HTTP server READY at {base_url}")
    print(f"M19 server log evidence={server_log}")
    try:
        result = _verify_permissions_and_control_flow(
            base_url,
            actors,
        )
        _verify_browser(
            base_url,
            actors["admin"]["token"],
            evidence_dir,
        )
    finally:
        time.sleep(0.25)
        stop_process(process)

    _verify_database_semantics(
        ctx,
        actors,
        result,
    )

    report = {
        "milestone": "M19",
        "version": "0.19.0",
        "database_revision": "0018_m19",
        "control_revision": result["final_revision"],
        "policy_key": result["policy_key"],
        "result": "PASS",
    }
    report_path = evidence_dir / "m19_institution_control_plane.json"
    report_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"M19 evidence report={report_path}")
    print("M19 INSTITUTION CONTROL PLANE v0.19.0: PASSED")


if __name__ == "__main__":
    main()
