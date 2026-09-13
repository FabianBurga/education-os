from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from playwright.sync_api import sync_playwright

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
from app.core.security import create_access_token  # noqa: E402
from tools.acceptance.harness import (  # noqa: E402
    edge_path,
    free_port,
    stop_process,
    wait_for_health,
)
from tools.verify_m10_teacher_console import bootstrap_teacher_context  # noqa: E402
from tools.verify_m16_full_system_acceptance import _create_actor  # noqa: E402

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)
RUNTIME_URL = os.getenv(
    "DATABASE_URL_PG", "postgresql://education_app:education_app_dev@localhost:5432/education_os"
)


def req(base, path, *, token=None, method="GET", payload=None):
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    r = urllib.request.Request(base + path, headers=headers, data=data, method=method)
    try:
        with urllib.request.urlopen(r, timeout=20) as response:
            raw = response.read().decode()
            ct = response.headers.get("content-type", "")
            return response.status, (json.loads(raw) if "application/json" in ct else raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def start_server(evidence):
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    log = evidence / "m20_uvicorn.log"
    with log.open("w", encoding="utf-8", buffering=1) as f:
        p = subprocess.Popen(
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
            stdout=f,
            stderr=subprocess.STDOUT,
            text=True,
        )
    wait_for_health(base, p)
    return p, base, log


def assert_schema():
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        assert cur.fetchone() == ("0019_m20",)
        cur.execute(
            "SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE relname='teacher_offline_receipts'"
        )
        assert cur.fetchone() == (True, True)
        cur.execute(
            "SELECT tgname FROM pg_trigger WHERE tgname IN ('trg_teacher_offline_receipts_immutable','trg_teacher_offline_receipts_no_truncate') AND NOT tgisinternal"
        )
        assert {r[0] for r in cur.fetchall()} == {
            "trg_teacher_offline_receipts_immutable",
            "trg_teacher_offline_receipts_no_truncate",
        }
    print("M20 schema + FORCE RLS + immutable receipts: PASSED")


def context():
    ctx = bootstrap_teacher_context()
    suffix = ctx["suffix"]
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT CURRENT_DATE")
        ctx["db_today"] = cur.fetchone()[0]
        alt = f"M20L{suffix[:6]}"
        alt_id = uuid4()
        cur.execute(
            """INSERT INTO attendance_codes (id,organization_id,institution_id,code,label,semantic,counts_as_present,counts_as_absent,counts_as_late,status,created_at) VALUES (%s,%s,%s,%s,%s,'LATE',true,false,true,'ACTIVE',NOW()) ON CONFLICT (institution_id,code) DO NOTHING""",
            (alt_id, ctx["organization_id"], ctx["institution_id"], alt, f"Tardanza M20 {suffix}"),
        )
        cur.execute(
            "SELECT id FROM attendance_codes WHERE institution_id=%s AND code=%s",
            (ctx["institution_id"], alt),
        )
        ctx["alt_attendance_code_id"] = cur.fetchone()[0]
        admin = _create_actor(
            cur,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            actor_key="m20-admin",
            role_key="SYSTEM_ADMIN",
            profile_kind="staff",
            suffix=suffix,
        )
        conn.commit()

    def token(user):
        return create_access_token(
            user_id=UUID(str(user)),
            organization_id=UUID(str(ctx["organization_id"])),
            institution_id=UUID(str(ctx["institution_id"])),
        )

    ctx["teacher_token"] = token(ctx["user_id"])
    ctx["non_token"] = token(ctx["non_user_id"])
    ctx["admin_token"] = token(admin["user_id"])
    return ctx


def create_session(base, ctx):
    seed = int(ctx["suffix"][:6], 16)
    hour = 6 + seed % 12
    minute = (seed // 12) % 60
    second = (seed // 720) % 60
    start = f"{hour:02d}:{minute:02d}:{second:02d}"
    end = f"{min(hour + 1, 23):02d}:{minute:02d}:{second:02d}"
    code, body = req(
        base,
        f"/api/v1/teacher/classes/{ctx['course_offering_id']}/sessions",
        token=ctx["teacher_token"],
        method="POST",
        payload={
            "session_date": ctx["db_today"].isoformat(),
            "starts_at": start,
            "ends_at": end,
            "schedule_slot_id": None,
        },
    )
    assert code == 201, (code, body)
    return body


def drain(base, token):
    for _ in range(20):
        code, body = req(
            base, "/api/v1/event-platform/pipeline/run?limit=5000", token=token, method="POST"
        )
        assert code == 200, (code, body)
        if body["ingested"] == 0 and body["projected"] == 0:
            return
    raise AssertionError("pipeline did not drain")



def _set_offline_capability(ctx, enabled: bool, *, phase: str) -> None:
    expected = (bool(enabled),)

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE institution_capabilities
            SET enabled = %s
            WHERE institution_id = %s
              AND capability_key = 'teacher.offline_pwa'
            """,
            (enabled, ctx["institution_id"]),
        )

        if cur.rowcount == 0:
            cur.execute(
                """
                INSERT INTO institution_capabilities (
                    institution_id,
                    capability_key,
                    enabled
                )
                VALUES (%s, 'teacher.offline_pwa', %s)
                """,
                (ctx["institution_id"], enabled),
            )

        cur.execute(
            """
            SELECT enabled
            FROM institution_capabilities
            WHERE institution_id = %s
              AND capability_key = 'teacher.offline_pwa'
            """,
            (ctx["institution_id"],),
        )
        in_tx = cur.fetchone()
        assert in_tx == expected, (
            f"M20 capability {phase} in-transaction mismatch: "
            f"expected={expected} actual={in_tx}"
        )
        conn.commit()

    with psycopg.connect(OWNER_URL) as verify_conn, verify_conn.cursor() as verify_cur:
        verify_cur.execute(
            """
            SELECT enabled
            FROM institution_capabilities
            WHERE institution_id = %s
              AND capability_key = 'teacher.offline_pwa'
            """,
            (ctx["institution_id"],),
        )
        persisted = verify_cur.fetchone()

    assert persisted == expected, (
        f"M20 capability {phase} persistence mismatch: "
        f"expected={expected} actual={persisted}"
    )

    print(
        "M20 capability toggle: "
        f"phase={phase} enabled={enabled} persisted={persisted[0]}"
    )
    if enabled:
        print("M20 acceptance fixture capability row: READY")


def api_acceptance(base, ctx):
    non_status, non_body = req(base, "/api/v1/teacher/offline/snapshot", token=ctx["non_token"])
    assert non_status == 403, f"non-teacher offline snapshot boundary: {non_status} {non_body}"
    _set_offline_capability(ctx, False, phase="disabled-negative-gate")
    assert req(base, "/api/v1/teacher/offline/snapshot", token=ctx["teacher_token"])[0] == 409
    _set_offline_capability(ctx, True, phase="enabled-positive-gate")
    session = create_session(base, ctx)
    code, snap = req(base, "/api/v1/teacher/offline/snapshot?days=14", token=ctx["teacher_token"])
    assert code == 200, (code, snap)
    cls = next(
        x
        for x in snap["classes"]
        if x["classroom"]["course_offering_id"] == str(ctx["course_offering_id"])
    )
    ss = next(x for x in cls["sessions"] if x["session"]["id"] == session["id"])
    row = next(
        x
        for x in ss["attendance"]
        if x["student_section_assignment_id"] == str(ctx["student_section_assignment_id"])
    )
    base_state = {
        "attendance_record_id": row["attendance_record_id"],
        "attendance_code_id": row["attendance_code_id"],
        "minutes_late": row["minutes_late"],
        "note": row["note"],
    }
    opid = uuid4()
    op = {
        "operation_id": str(opid),
        "operation_type": "ATTENDANCE_MARK",
        "class_session_id": session["id"],
        "base": base_state,
        "desired": {
            "student_section_assignment_id": str(ctx["student_section_assignment_id"]),
            "attendance_code_id": str(ctx["attendance_code_id"]),
            "minutes_late": 0,
            "note": None,
        },
    }
    code, body = req(
        base,
        "/api/v1/teacher/offline/sync",
        token=ctx["teacher_token"],
        method="POST",
        payload={"operations": [op]},
    )
    assert code == 200
    assert body["results"][0]["status"] == "APPLIED"
    record = body["results"][0]["result_entity_id"]
    applied_state = body["results"][0]["server_state"]
    code, body = req(
        base,
        "/api/v1/teacher/offline/sync",
        token=ctx["teacher_token"],
        method="POST",
        payload={"operations": [op]},
    )
    assert body["results"][0]["status"] == "REPLAYED"
    bad = json.loads(json.dumps(op))
    bad["desired"]["minutes_late"] = 1
    assert (
        req(
            base,
            "/api/v1/teacher/offline/sync",
            token=ctx["teacher_token"],
            method="POST",
            payload={"operations": [bad]},
        )[1]["results"][0]["status"]
        == "IDEMPOTENCY_MISMATCH"
    )
    concurrent_a = json.loads(json.dumps(op))
    concurrent_a["operation_id"] = str(uuid4())
    concurrent_a["base"] = applied_state
    concurrent_a["desired"]["attendance_code_id"] = str(ctx["alt_attendance_code_id"])
    concurrent_a["desired"]["minutes_late"] = 3
    concurrent_b = json.loads(json.dumps(op))
    concurrent_b["operation_id"] = str(uuid4())
    concurrent_b["base"] = applied_state
    concurrent_b["desired"]["minutes_late"] = 7

    def send_concurrent(operation):
        return req(
            base,
            "/api/v1/teacher/offline/sync",
            token=ctx["teacher_token"],
            method="POST",
            payload={"operations": [operation]},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(send_concurrent, (concurrent_a, concurrent_b)))
    statuses = sorted(response[1]["results"][0]["status"] for response in responses)
    assert statuses == ["APPLIED", "CONFLICT"], statuses
    print("M20 concurrent target serialization: PASSED")
    conflict = json.loads(json.dumps(op))
    conflict["operation_id"] = str(uuid4())
    conflict["desired"]["attendance_code_id"] = str(ctx["alt_attendance_code_id"])
    assert (
        req(
            base,
            "/api/v1/teacher/offline/sync",
            token=ctx["teacher_token"],
            method="POST",
            payload={"operations": [conflict]},
        )[1]["results"][0]["status"]
        == "CONFLICT"
    )
    drain(base, ctx["admin_token"])
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM teacher_offline_receipts WHERE operation_id=%s", (opid,))
        assert cur.fetchone()[0] == 1
        cur.execute(
            "SELECT COUNT(*) FROM event_ledger WHERE event_type='teacher.attendance.synced' AND aggregate_id=%s AND correlation_id=%s",
            (record, opid),
        )
        assert cur.fetchone()[0] == 1
    print("M20 API scope + capability + idempotency + conflict + Event Ledger: PASSED")
    return session["id"], record


def direct_rls(ctx):
    with psycopg.connect(RUNTIME_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT set_config('app.organization_id',%s,false),set_config('app.institution_id',%s,false),set_config('app.user_id',%s,false)",
            (str(ctx["organization_id"]), str(ctx["institution_id"]), str(ctx["user_id"])),
        )
        cur.execute("SELECT COUNT(*) FROM teacher_offline_receipts")
        assert cur.fetchone()[0] >= 1
    with psycopg.connect(RUNTIME_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT set_config('app.organization_id',%s,false),set_config('app.institution_id',%s,false),set_config('app.user_id',%s,false)",
            (str(ctx["organization_id"]), str(ctx["institution_id"]), str(ctx["non_user_id"])),
        )
        cur.execute("SELECT COUNT(*) FROM teacher_offline_receipts")
        assert cur.fetchone()[0] == 0
    for sql in (
        "UPDATE teacher_offline_receipts SET status='APPLIED'",
        "DELETE FROM teacher_offline_receipts",
        "TRUNCATE teacher_offline_receipts",
    ):
        try:
            with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
                cur.execute(sql)
                conn.commit()
        except psycopg.Error as exc:
            assert "append-only" in str(exc)
        else:
            raise AssertionError(sql)
    print("M20 direct RLS + immutable receipt boundary: PASSED")


def browser(base, ctx, evidence):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=edge_path(), headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(base + "/app/", wait_until="networkidle")
        page.evaluate(
            "(t)=>sessionStorage.setItem('education_os_access_token',t)", ctx["teacher_token"]
        )
        page.goto(base + "/app/workspace/teacher", wait_until="networkidle")
        page.get_by_test_id("teacher-pwa-page").wait_for(timeout=20000)
        page.get_by_test_id("teacher-offline-prepare").click()
        page.wait_for_function(
            "()=>document.body.innerText.includes('Paquete docente actualizado')", timeout=20000
        )
        page.evaluate("()=>navigator.serviceWorker.ready.then(()=>true)")
        try:
            page.wait_for_function("()=>navigator.serviceWorker.controller!==null", timeout=8000)
        except Exception:
            page.reload(wait_until="networkidle")
            page.wait_for_function("()=>navigator.serviceWorker.controller!==null", timeout=15000)
        api_cache = page.evaluate(
            """async()=>{const urls=[];for(const name of await caches.keys()){const cache=await caches.open(name);for(const r of await cache.keys()){const p=new URL(r.url).pathname;if(p.startsWith('/api/'))urls.push(p);}}return urls;}"""
        )
        assert api_cache == [], api_cache
        context.set_offline(True)
        page.reload(wait_until="domcontentloaded")
        page.get_by_test_id("teacher-pwa-page").wait_for(timeout=15000)
        selects = page.locator("[data-testid^='attendance-select-']")
        assert selects.count() >= 1
        first = selects.first
        values = [
            x.get_attribute("value")
            for x in first.locator("option").all()
            if x.get_attribute("value")
        ]
        current = first.input_value()
        alternate = next(v for v in values if v != current)
        first.select_option(alternate)
        page.wait_for_function(
            "()=>document.querySelector('[data-testid=teacher-offline-pending]')?.textContent?.trim()==='1'",
            timeout=10000,
        )
        offline = evidence / "m20_teacher_pwa_offline_edge.png"
        page.screenshot(path=str(offline), full_page=True)
        context.set_offline(False)
        page.wait_for_function("()=>navigator.onLine===true", timeout=10000)
        page.wait_for_function(
            "()=>!document.querySelector('[data-testid=teacher-offline-sync]')?.disabled",
            timeout=10000,
        )
        page.get_by_test_id("teacher-offline-sync").click()
        page.wait_for_function(
            "()=>document.querySelector('[data-testid=teacher-offline-pending]')?.textContent?.trim()==='0'",
            timeout=20000,
        )
        synced = evidence / "m20_teacher_pwa_synced_edge.png"
        page.screenshot(path=str(synced), full_page=True)
        context.close()
        browser.close()
    print(f"M20 offline Edge screenshot={offline}")
    print(f"M20 synced Edge screenshot={synced}")
    print("M20 real Microsoft Edge offline reload + queued sync: PASSED")


def main():
    assert_schema()
    ctx = context()
    evidence = Path(
        os.getenv("M20_EVIDENCE_DIR", str(Path.home() / "Downloads" / "Education_OS_M20_Evidence"))
    )
    evidence.mkdir(parents=True, exist_ok=True)
    process, base, log = start_server(evidence)
    print(f"M20 actual HTTP server READY at {base}")
    print(f"M20 server log evidence={log}")
    try:
        session_id, record_id = api_acceptance(base, ctx)
        browser(base, ctx, evidence)
    finally:
        time.sleep(0.25)
        stop_process(process)
    direct_rls(ctx)
    report = {
        "milestone": "M20",
        "version": "0.20.0",
        "database_revision": "0019_m20",
        "class_session_id": session_id,
        "attendance_record_id": record_id,
        "result": "PASS",
    }
    path = evidence / "m20_offline_teacher_pwa.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"M20 evidence report={path}")
    print("M20 OFFLINE-FIRST TEACHER PWA v0.20.0: PASSED")


if __name__ == "__main__":
    main()
