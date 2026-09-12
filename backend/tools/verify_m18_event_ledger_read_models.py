from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import UUID, uuid4

import psycopg

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.security import create_access_token  # noqa: E402
from tools.acceptance.harness import (  # noqa: E402
    http,
    start_uvicorn,
    stop_process,
)
from tools.verify_m16_full_system_acceptance import (  # noqa: E402
    _create_actor,
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


def _post(
    base_url: str,
    path: str,
    token: str,
) -> tuple[int, object]:
    request = urllib.request.Request(
        f"{base_url}{path}",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
        data=b"",
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def _assert_schema() -> None:
    required_tables = {
        "event_ledger",
        "projection_checkpoints",
        "institution_event_daily",
        "aggregate_activity_snapshots",
    }
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        assert cur.fetchone() == ("0017_m18",)

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
            SELECT tgname
            FROM pg_trigger
            WHERE tgname = ANY(%s)
              AND NOT tgisinternal
            """,
            (
                [
                    "trg_event_ledger_immutable",
                    "trg_event_ledger_no_truncate",
                ],
            ),
        )
        assert {row[0] for row in cur.fetchall()} == {
            "trg_event_ledger_immutable",
            "trg_event_ledger_no_truncate",
        }

    print("M18 schema + FORCE RLS + immutable ledger catalog: PASSED")


def _bootstrap(ctx: dict) -> dict[str, dict]:
    suffix = uuid4().hex[:8].upper()
    actors: dict[str, dict] = {}
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        for actor_key, role_key in (
            ("admin", "SYSTEM_ADMIN"),
            ("coordinator", "ACADEMIC_COORDINATOR"),
            ("teacher", "TEACHER"),
        ):
            actors[actor_key] = _create_actor(
                cur,
                organization_id=ctx["organization_id"],
                institution_id=ctx["institution_id"],
                actor_key=f"m18-{actor_key}",
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


def _seed_outbox(ctx: dict, actors: dict[str, dict]) -> dict[str, object]:
    aggregate_id = uuid4()
    correlation_id = uuid4()
    event_ids = [uuid4(), uuid4(), uuid4()]

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        specs = (
            (
                event_ids[0],
                "m18.student.activity",
                1,
                {"kind": "activity"},
                0,
            ),
            (
                event_ids[1],
                "m18.attendance.recorded",
                1,
                {"status": "ABSENT"},
                1,
            ),
            (
                event_ids[2],
                "m18.grade.published",
                2,
                {"score": 8.75},
                2,
            ),
        )
        for event_id, event_type, event_version, payload, offset_ms in specs:
            envelope_payload = {
                "_education_os_event": {
                    "version": event_version,
                    "actor_user_id": str(actors["admin"]["user_id"]),
                    "correlation_id": str(correlation_id),
                    "causation_id": None,
                    "metadata": {"source": "m18-verifier"},
                },
                "data": payload,
            }
            cur.execute(
                """
                INSERT INTO outbox_events (
                    id,
                    institution_id,
                    event_type,
                    aggregate_type,
                    aggregate_id,
                    payload_json,
                    status,
                    attempts,
                    created_at
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    'student',
                    %s,
                    %s::json,
                    'PENDING',
                    0,
                    NOW() + (%s * INTERVAL '1 millisecond')
                )
                """,
                (
                    event_id,
                    ctx["institution_id"],
                    event_type,
                    aggregate_id,
                    json.dumps(envelope_payload),
                    offset_ms,
                ),
            )
        conn.commit()

    return {
        "aggregate_id": aggregate_id,
        "correlation_id": correlation_id,
        "event_ids": event_ids,
    }


def _verify_http(
    base_url: str,
    ctx: dict,
    actors: dict[str, dict],
    seeded: dict[str, object],
) -> None:
    status, _body, _headers = http(
        base_url,
        "/api/v1/event-platform/summary",
        token=actors["teacher"]["token"],
    )
    assert status == 403

    status, before, _headers = http(
        base_url,
        "/api/v1/event-platform/summary",
        token=actors["coordinator"]["token"],
    )
    assert status == 200 and isinstance(before, dict)
    assert before["milestone"] == "M18"

    status, denied = _post(
        base_url,
        "/api/v1/event-platform/pipeline/run?limit=5000",
        actors["coordinator"]["token"],
    )
    assert status == 403, denied

    total_ingested = 0
    total_projected = 0
    drained = False
    for _attempt in range(20):
        status, result = _post(
            base_url,
            "/api/v1/event-platform/pipeline/run?limit=5000",
            actors["admin"]["token"],
        )
        assert status == 200 and isinstance(result, dict), result
        total_ingested += int(result["ingested"])
        total_projected += int(result["projected"])
        if result["ingested"] == 0 and result["projected"] == 0:
            drained = True
            break

    assert drained, "M18 pipeline did not drain within 20 batches"
    assert total_ingested >= 3
    assert total_projected >= 3

    status, idempotent = _post(
        base_url,
        "/api/v1/event-platform/pipeline/run?limit=5000",
        actors["admin"]["token"],
    )
    assert status == 200 and isinstance(idempotent, dict), idempotent
    assert idempotent["ingested"] == 0, idempotent
    assert idempotent["projected"] == 0, idempotent

    status, recent, _headers = http(
        base_url,
        "/api/v1/event-platform/events/recent?limit=200",
        token=actors["coordinator"]["token"],
    )
    assert status == 200 and isinstance(recent, list)
    seeded_ids = {str(item) for item in seeded["event_ids"]}
    recent_by_id = {
        item["event_id"]: item
        for item in recent
        if item["event_id"] in seeded_ids
    }
    assert set(recent_by_id) == seeded_ids
    assert {
        recent_by_id[str(seeded["event_ids"][0])]["event_version"],
        recent_by_id[str(seeded["event_ids"][2])]["event_version"],
    } == {1, 2}
    for item in recent_by_id.values():
        assert "payload_json" not in item
        assert item["correlation_id"] == str(seeded["correlation_id"])

    status, daily, _headers = http(
        base_url,
        "/api/v1/event-platform/read-models/daily?limit=500",
        token=actors["coordinator"]["token"],
    )
    assert status == 200 and isinstance(daily, list)
    daily_types = {item["event_type"] for item in daily}
    assert {
        "m18.student.activity",
        "m18.attendance.recorded",
        "m18.grade.published",
    }.issubset(daily_types)

    status, after, _headers = http(
        base_url,
        "/api/v1/event-platform/summary",
        token=actors["coordinator"]["token"],
    )
    assert status == 200 and isinstance(after, dict)
    assert after["projection"]["last_position"] > 0
    assert (
        after["projection"]["last_position"]
        == after["ledger"]["latest_position"]
    )

    print("M18 API boundaries + idempotent pipeline + read models: PASSED")


def _verify_database_semantics(
    ctx: dict,
    actors: dict[str, dict],
    seeded: dict[str, object],
) -> None:
    event_ids = list(seeded["event_ids"])

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                event_type,
                event_version,
                correlation_id,
                source_outbox_event_id
            FROM event_ledger
            WHERE id = ANY(%s)
            ORDER BY position
            """,
            (event_ids,),
        )
        rows = cur.fetchall()
        assert len(rows) == 3
        assert [row[2] for row in rows] == [1, 1, 2]
        for row in rows:
            assert row[0] == row[4]
            assert row[3] == seeded["correlation_id"]

        cur.execute(
            """
            SELECT event_count, last_event_type, last_event_version
            FROM aggregate_activity_snapshots
            WHERE institution_id = %s
              AND aggregate_type = 'student'
              AND aggregate_id = %s
            """,
            (ctx["institution_id"], seeded["aggregate_id"]),
        )
        snapshot = cur.fetchone()
        assert snapshot is not None
        assert snapshot[0] == 3
        assert snapshot[1] == "m18.grade.published"
        assert snapshot[2] == 2

    try:
        with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE event_ledger
                SET event_type = 'm18.illegal.mutation'
                WHERE id = %s
                """,
                (event_ids[0],),
            )
            conn.commit()
    except psycopg.Error as exc:
        assert "append-only" in str(exc)
    else:
        raise AssertionError("event_ledger UPDATE unexpectedly succeeded")

    try:
        with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE event_ledger")
            conn.commit()
    except psycopg.Error as exc:
        assert "append-only" in str(exc)
    else:
        raise AssertionError("event_ledger TRUNCATE unexpectedly succeeded")

    print("M18 canonical lineage + aggregate snapshot + immutability: PASSED")

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
        cur.execute("SELECT COUNT(id) FROM event_ledger")
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
                str(actors["coordinator"]["user_id"]),
            ),
        )
        cur.execute(
            """
            SELECT COUNT(id)
            FROM event_ledger
            WHERE id = ANY(%s)
            """,
            (event_ids,),
        )
        assert cur.fetchone()[0] == 3

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
                    str(actors["coordinator"]["user_id"]),
                ),
            )
            cur.execute(
                "SELECT payload_json FROM event_ledger WHERE id = %s",
                (event_ids[0],),
            )
            cur.fetchone()
    except psycopg.errors.InsufficientPrivilege:
        pass
    else:
        raise AssertionError(
            "Coordinator unexpectedly received direct ledger payload access"
        )

    print("M18 direct runtime RLS + payload-column boundary: PASSED")


def main() -> None:
    _assert_schema()
    ctx = _pick_tenant()
    actors = _bootstrap(ctx)
    seeded = _seed_outbox(ctx, actors)

    evidence_dir = Path(
        os.getenv(
            "M18_EVIDENCE_DIR",
            str(Path.home() / "Downloads" / "Education_OS_M18_Evidence"),
        )
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)

    process, base_url = start_uvicorn(BACKEND_ROOT)
    print(f"M18 actual HTTP server READY at {base_url}")
    try:
        _verify_http(base_url, ctx, actors, seeded)
    finally:
        time.sleep(0.25)
        stop_process(process)

    _verify_database_semantics(ctx, actors, seeded)

    report = {
        "milestone": "M18",
        "version": "0.18.0",
        "database_revision": "0017_m18",
        "projection": "institution_activity_v1",
        "event_ids": [str(item) for item in seeded["event_ids"]],
        "aggregate_id": str(seeded["aggregate_id"]),
        "result": "PASS",
    }
    report_path = evidence_dir / "m18_event_ledger_read_models.json"
    report_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"M18 evidence report={report_path}")
    print("M18 EVENT LEDGER + READ MODELS v0.18.0: PASSED")


if __name__ == "__main__":
    main()
