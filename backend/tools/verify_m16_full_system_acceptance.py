from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import UUID, uuid4

import psycopg

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.security import create_access_token, hash_password  # noqa: E402

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)
RUNTIME_URL = os.getenv(
    "DATABASE_URL_PG",
    "postgresql://education_app:education_app_dev@localhost:5432/education_os",
)

ROLE_SPECS = {
    "admin": ("SYSTEM_ADMIN", "staff"),
    "rector": ("RECTOR", "staff"),
    "coordinator": ("ACADEMIC_COORDINATOR", "staff"),
    "teacher": ("TEACHER", "staff"),
    "student": ("STUDENT", "student"),
    "guardian": ("GUARDIAN", "guardian"),
    "finance": ("FINANCE_MANAGER", "staff"),
    "roleless": (None, "staff"),
}

MODULE_PERMISSION_TO_ID = {
    "admin.console.access": "administration",
    "coord.console.access": "coordination",
    "teacher.console.access": "teacher",
    "student.console.access": "student",
    "guardian.console.access": "guardian",
    "communications.console.access": "communications",
    "finance.console.access": "finance",
}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http(
    base_url: str,
    path: str,
    token: str | None = None,
) -> tuple[int, object]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(
        f"{base_url}{path}",
        headers=headers,
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
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


def _wait_server(base_url: str, process: subprocess.Popen) -> None:
    deadline = time.time() + 30
    last_error = ""
    while time.time() < deadline:
        if process.poll() is not None:
            output = ""
            if process.stdout is not None:
                output = process.stdout.read()
            raise RuntimeError(
                f"uvicorn exited early with code {process.returncode}: {output}"
            )
        try:
            status, body = _http(base_url, "/health")
            if (
                status == 200
                and isinstance(body, dict)
                and body.get("milestone") == "M15"
            ):
                return
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"HTTP server not ready: {last_error}")


def _edge_path() -> str:
    candidates = (
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    raise RuntimeError("Microsoft Edge executable not found")


def _pick_tenant() -> dict:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                i.organization_id,
                i.id,
                i.name,
                i.type
            FROM institutions i
            WHERE i.status = 'ACTIVE'
            ORDER BY i.created_at
            LIMIT 1
            """
        )
        row = cur.fetchone()
        assert row is not None, "M16 requires one active institution"
        return {
            "organization_id": row[0],
            "institution_id": row[1],
            "institution_name": row[2],
            "institution_type": row[3],
        }


def _create_actor(
    cur,
    *,
    organization_id: UUID,
    institution_id: UUID,
    actor_key: str,
    role_key: str | None,
    profile_kind: str,
    suffix: str,
) -> dict:
    person_id = uuid4()
    user_id = uuid4()
    membership_id = uuid4()
    profile_id = uuid4()
    login_email = (
        f"m16-{actor_key}-{suffix.lower()}@education-os.internal"
    )

    cur.execute(
        """
        INSERT INTO persons (
            id,
            organization_id,
            given_names,
            family_names,
            primary_email,
            created_at
        )
        VALUES (%s, %s, 'M16', %s, %s, NOW())
        """,
        (
            person_id,
            organization_id,
            actor_key.upper(),
            login_email,
        ),
    )

    if profile_kind == "staff":
        cur.execute(
            """
            INSERT INTO staff_profiles (
                id,
                organization_id,
                institution_id,
                person_id,
                staff_code,
                status,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, 'ACTIVE', NOW())
            """,
            (
                profile_id,
                organization_id,
                institution_id,
                person_id,
                f"M16-{actor_key.upper()}-{suffix}",
            ),
        )
    elif profile_kind == "student":
        cur.execute(
            """
            INSERT INTO student_profiles (
                id,
                organization_id,
                institution_id,
                person_id,
                student_code,
                status,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, 'ACTIVE', NOW())
            """,
            (
                profile_id,
                organization_id,
                institution_id,
                person_id,
                f"M16-{actor_key.upper()}-{suffix}",
            ),
        )
    elif profile_kind == "guardian":
        cur.execute(
            """
            INSERT INTO guardian_profiles (
                id,
                organization_id,
                institution_id,
                person_id,
                guardian_code,
                status,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, 'ACTIVE', NOW())
            """,
            (
                profile_id,
                organization_id,
                institution_id,
                person_id,
                f"M16-{actor_key.upper()}-{suffix}",
            ),
        )
    else:
        raise AssertionError(f"Unknown profile kind: {profile_kind}")

    cur.execute(
        """
        INSERT INTO user_accounts (
            id,
            person_id,
            login_email,
            password_hash,
            is_active,
            created_at
        )
        VALUES (%s, %s, %s, %s, true, NOW())
        """,
        (
            user_id,
            person_id,
            login_email,
            hash_password("M16-Full-System-Temporary-2026!"),
        ),
    )
    cur.execute(
        """
        INSERT INTO memberships (
            id,
            user_id,
            institution_id,
            status,
            created_at
        )
        VALUES (%s, %s, %s, 'ACTIVE', NOW())
        """,
        (
            membership_id,
            user_id,
            institution_id,
        ),
    )

    role_id = None
    if role_key is not None:
        cur.execute(
            """
            SELECT id
            FROM roles
            WHERE institution_id = %s
              AND key = %s
            """,
            (institution_id, role_key),
        )
        role = cur.fetchone()
        assert role is not None, f"Required role missing: {role_key}"
        role_id = role[0]
        cur.execute(
            """
            INSERT INTO membership_roles (membership_id, role_id)
            VALUES (%s, %s)
            """,
            (membership_id, role_id),
        )

    return {
        "key": actor_key,
        "role_key": role_key,
        "profile_kind": profile_kind,
        "person_id": person_id,
        "profile_id": profile_id,
        "user_id": user_id,
        "membership_id": membership_id,
        "role_id": role_id,
        "login_email": login_email,
    }


def _bootstrap_actor_matrix(ctx: dict) -> dict[str, dict]:
    suffix = uuid4().hex[:8].upper()
    actors: dict[str, dict] = {}
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        for actor_key, (role_key, profile_kind) in ROLE_SPECS.items():
            actors[actor_key] = _create_actor(
                cur,
                organization_id=ctx["organization_id"],
                institution_id=ctx["institution_id"],
                actor_key=actor_key,
                role_key=role_key,
                profile_kind=profile_kind,
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


def _assert_role_catalog(ctx: dict) -> None:
    expected_roles = {
        "SYSTEM_ADMIN",
        "RECTOR",
        "ACADEMIC_COORDINATOR",
        "TEACHER",
        "STUDENT",
        "GUARDIAN",
        "FINANCE_MANAGER",
    }
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT key
            FROM roles
            WHERE institution_id = %s
              AND key = ANY(%s)
            """,
            (ctx["institution_id"], list(expected_roles)),
        )
        actual = {row[0] for row in cur.fetchall()}
    assert actual == expected_roles, (
        f"M16 role catalog mismatch: expected={sorted(expected_roles)} "
        f"actual={sorted(actual)}"
    )
    print("M16 canonical role catalog: PASSED")


def _module_ids_from_bootstrap(bootstrap: dict) -> list[str]:
    permissions = set(bootstrap["permissions"])
    return sorted(
        module_id
        for permission, module_id in MODULE_PERMISSION_TO_ID.items()
        if permission in permissions
    )


def _verify_bootstrap_matrix(
    base_url: str,
    actors: dict[str, dict],
    ctx: dict,
) -> dict[str, list[str]]:
    matrix: dict[str, list[str]] = {}

    for actor_key, actor in actors.items():
        status, body = _http(
            base_url,
            "/api/v1/ui/bootstrap",
            actor["token"],
        )
        assert status == 200 and isinstance(body, dict), (
            actor_key,
            status,
            body,
        )
        assert body["tenant"]["institution_id"] == str(ctx["institution_id"])
        assert body["tenant"]["organization_id"] == str(ctx["organization_id"])

        expected_role = actor["role_key"]
        if expected_role is None:
            assert body["roles"] == [], (actor_key, body["roles"])
        else:
            assert expected_role in body["roles"], (
                actor_key,
                expected_role,
                body["roles"],
            )

        modules = _module_ids_from_bootstrap(body)
        matrix[actor_key] = modules

    required = {
        "admin": {"administration", "coordination", "teacher",
                  "communications", "finance"},
        "rector": {"coordination", "communications", "finance"},
        "coordinator": {"coordination", "communications"},
        "teacher": {"teacher"},
        "student": {"student"},
        "guardian": {"guardian"},
        "finance": {"finance"},
        "roleless": set(),
    }
    for actor_key, minimum in required.items():
        actual = set(matrix[actor_key])
        assert minimum.issubset(actual), (
            f"{actor_key} missing expected modules: "
            f"minimum={sorted(minimum)} actual={sorted(actual)}"
        )

    print("M16 role -> unified workspace matrix: PASSED")
    return matrix


def _expect_status(
    base_url: str,
    path: str,
    token: str,
    expected_status: int,
    label: str,
) -> None:
    status, body = _http(base_url, path, token)
    assert status == expected_status, (
        f"{label}: expected={expected_status} actual={status} body={body}"
    )


def _verify_api_boundaries(
    base_url: str,
    actors: dict[str, dict],
) -> None:
    token = {key: value["token"] for key, value in actors.items()}

    _expect_status(
        base_url,
        "/api/v1/admin/summary",
        token["admin"],
        200,
        "admin -> admin",
    )
    _expect_status(
        base_url,
        "/api/v1/admin/summary",
        token["teacher"],
        403,
        "teacher !-> admin",
    )

    _expect_status(
        base_url,
        "/api/v1/coordination/summary",
        token["rector"],
        200,
        "rector -> coordination",
    )
    _expect_status(
        base_url,
        "/api/v1/coordination/summary",
        token["student"],
        403,
        "student !-> coordination",
    )

    _expect_status(
        base_url,
        "/api/v1/teacher/summary",
        token["teacher"],
        200,
        "teacher -> teacher",
    )
    _expect_status(
        base_url,
        "/api/v1/teacher/summary",
        token["guardian"],
        403,
        "guardian !-> teacher",
    )

    _expect_status(
        base_url,
        "/api/v1/student/me",
        token["student"],
        200,
        "student -> student",
    )
    _expect_status(
        base_url,
        "/api/v1/student/me",
        token["guardian"],
        403,
        "guardian !-> student",
    )

    _expect_status(
        base_url,
        "/api/v1/guardian/me",
        token["guardian"],
        200,
        "guardian -> guardian",
    )
    _expect_status(
        base_url,
        "/api/v1/guardian/me",
        token["student"],
        403,
        "student !-> guardian",
    )

    _expect_status(
        base_url,
        "/api/v1/communications/summary",
        token["coordinator"],
        200,
        "coordinator -> communications",
    )
    _expect_status(
        base_url,
        "/api/v1/communications/summary",
        token["teacher"],
        403,
        "teacher !-> communications",
    )

    _expect_status(
        base_url,
        "/api/v1/finance/capability",
        token["finance"],
        200,
        "finance -> finance",
    )
    _expect_status(
        base_url,
        "/api/v1/finance/capability",
        token["teacher"],
        403,
        "teacher !-> finance",
    )

    _expect_status(
        base_url,
        "/api/v1/admin/summary",
        token["roleless"],
        403,
        "roleless !-> admin",
    )

    print("M16 positive + negative API role boundaries: PASSED")


def _verify_rls_negative_tenant(
    base_url: str,
    admin_actor: dict,
    ctx: dict,
) -> None:
    wrong_institution_id = uuid4()
    wrong_token = create_access_token(
        user_id=UUID(str(admin_actor["user_id"])),
        organization_id=UUID(str(ctx["organization_id"])),
        institution_id=wrong_institution_id,
    )

    status, campuses = _http(
        base_url,
        "/api/v1/campuses",
        wrong_token,
    )
    assert status == 403, (
        "Mismatched institution bypassed membership validation",
        status,
        campuses,
    )

    status, bootstrap = _http(
        base_url,
        "/api/v1/ui/bootstrap",
        wrong_token,
    )
    assert status == 403, (
        "Mismatched institution unexpectedly bootstrapped",
        status,
        bootstrap,
    )

    with psycopg.connect(RUNTIME_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT set_config('app.organization_id', %s, true)",
            (str(ctx["organization_id"]),),
        )
        cur.execute(
            "SELECT set_config('app.institution_id', %s, true)",
            (str(wrong_institution_id),),
        )
        cur.execute(
            "SELECT set_config('app.user_id', %s, true)",
            (str(admin_actor["user_id"]),),
        )
        cur.execute("SELECT COUNT(*) FROM campuses")
        assert cur.fetchone()[0] == 0

    print("M16 mismatched-tenant membership + RLS negative isolation: PASSED")


def _verify_browser_role_matrix(
    base_url: str,
    actors: dict[str, dict],
    matrix: dict[str, list[str]],
    evidence_dir: Path,
) -> None:
    from playwright.sync_api import sync_playwright

    edge = _edge_path()
    evidence_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=edge,
            headless=True,
        )

        for actor_key in (
            "admin",
            "rector",
            "coordinator",
            "teacher",
            "student",
            "guardian",
            "finance",
            "roleless",
        ):
            page = browser.new_page(
                viewport={"width": 1500, "height": 1050},
            )
            page.goto(
                f"{base_url}/app/",
                wait_until="domcontentloaded",
            )
            page.get_by_test_id("unified-token-input").fill(
                actors[actor_key]["token"]
            )
            page.get_by_test_id("unified-enter-button").click()

            home = page.get_by_test_id("unified-home")
            home.wait_for(timeout=15000)

            hrefs = home.locator(
                'a[href^="/app/workspace/"]'
            ).evaluate_all(
                "(nodes) => nodes.map((n) => n.getAttribute('href')).sort()"
            )
            expected_hrefs = sorted(
                f"/app/workspace/{module_id}"
                for module_id in matrix[actor_key]
            )
            assert hrefs == expected_hrefs, (
                f"{actor_key} browser navigation mismatch: "
                f"expected={expected_hrefs} actual={hrefs}"
            )

            screenshot = (
                evidence_dir
                / f"m16_{actor_key}_unified_workspace.png"
            )
            page.screenshot(path=str(screenshot), full_page=True)
            assert screenshot.is_file() and screenshot.stat().st_size > 0
            page.close()

        page = browser.new_page(
            viewport={"width": 1500, "height": 1050},
        )
        page.goto(
            f"{base_url}/app/",
            wait_until="domcontentloaded",
        )
        page.get_by_test_id("unified-token-input").fill(
            actors["roleless"]["token"]
        )
        page.get_by_test_id("unified-enter-button").click()
        page.get_by_test_id("unified-home").wait_for(timeout=15000)
        page.goto(
            f"{base_url}/app/workspace/finance",
            wait_until="domcontentloaded",
        )
        page.get_by_text(
            "Espacio no disponible",
            exact=True,
        ).wait_for(timeout=10000)
        page.close()

        browser.close()

    print("M16 Microsoft Edge multi-role workspace matrix: PASSED")


def _assert_runtime_catalog() -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        row = cur.fetchone()
        assert row == ("0016_m14",), row

        cur.execute(
            """
            SELECT COUNT(*)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname IN (
                'communication_templates',
                'communications',
                'communication_targets',
                'communication_recipients',
                'billing_concepts',
                'billing_accounts',
                'billing_charges',
                'billing_payments',
                'billing_allocations'
              )
              AND c.relrowsecurity
              AND c.relforcerowsecurity
            """
        )
        assert cur.fetchone()[0] == 9

    print("M16 database revision + critical FORCE RLS catalog: PASSED")


def main() -> None:
    assert (FRONTEND_DIST / "index.html").is_file(), (
        "M16 requires a built M15 frontend at frontend/dist"
    )
    _assert_runtime_catalog()

    ctx = _pick_tenant()
    _assert_role_catalog(ctx)
    actors = _bootstrap_actor_matrix(ctx)

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
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
            "warning",
        ],
        cwd=str(BACKEND_ROOT),
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    evidence_dir = Path(
        os.getenv(
            "M16_EVIDENCE_DIR",
            str(
                Path.home()
                / "Downloads"
                / "Education_OS_M16_Evidence"
            ),
        )
    )

    try:
        _wait_server(base_url, process)
        print(f"M16 actual HTTP server READY at {base_url}")

        status, app_html = _http(base_url, "/app/")
        assert status == 200
        assert '<div id="root"></div>' in str(app_html)

        matrix = _verify_bootstrap_matrix(
            base_url,
            actors,
            ctx,
        )
        _verify_api_boundaries(
            base_url,
            actors,
        )
        _verify_rls_negative_tenant(
            base_url,
            actors["admin"],
            ctx,
        )
        _verify_browser_role_matrix(
            base_url,
            actors,
            matrix,
            evidence_dir,
        )
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    evidence_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "release_candidate": "v1.0.0-rc6",
        "database_revision": "0016_m14",
        "institution_id": str(ctx["institution_id"]),
        "actor_roles": {
            key: value["role_key"]
            for key, value in actors.items()
        },
        "workspace_matrix": matrix,
        "result": "PASS",
    }
    report_path = evidence_dir / "m16_full_system_matrix.json"
    report_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"M16 role matrix report={report_path}")
    print(
        "M16 FULL-SYSTEM OPERATIONAL ACCEPTANCE / "
        "v1.0.0-rc6: PASSED"
    )


if __name__ == "__main__":
    main()
