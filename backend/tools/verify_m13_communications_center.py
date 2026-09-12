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
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.security import create_access_token, hash_password  # noqa: E402

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)

EXPECTED_PERMISSIONS = (
    "communications.console.access",
    "communications.delivery.view",
    "communications.messages.manage",
    "communications.messages.view",
    "communications.publish",
    "communications.templates.manage",
)
M13_TABLES = (
    "communication_templates",
    "communications",
    "communication_targets",
    "communication_recipients",
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http(
    base_url: str,
    path: str,
    token: str | None = None,
    *,
    method: str = "GET",
    payload: object | None = None,
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
            status, body = _http(base_url, "/api/v1/communications/dashboard")
            if status == 200 and "Communications Center" in str(body):
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


def _pick_student(cur) -> dict:
    cur.execute(
        """
        SELECT DISTINCT ON (sp.id)
            sp.id,
            sp.person_id,
            sp.organization_id,
            sp.institution_id,
            trim(concat_ws(' ', p.given_names, p.family_names))
        FROM student_profiles sp
        JOIN persons p ON p.id = sp.person_id
        JOIN enrollments e
          ON e.student_profile_id = sp.id
         AND e.status = 'ACTIVE'
        JOIN student_section_assignments ssa
          ON ssa.enrollment_id = e.id
         AND ssa.status = 'ACTIVE'
        WHERE sp.status = 'ACTIVE'
        ORDER BY sp.id, e.created_at DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    assert row is not None, "M13 verifier requires one active enrolled student"
    return {
        "student_profile_id": row[0],
        "person_id": row[1],
        "organization_id": row[2],
        "institution_id": row[3],
        "student_name": row[4],
    }


def _create_staff_identity(
    cur,
    *,
    organization_id: UUID,
    institution_id: UUID,
    suffix: str,
    role_key: str | None,
) -> dict:
    person_id = uuid4()
    staff_profile_id = uuid4()
    user_id = uuid4()
    membership_id = uuid4()
    login_email = f"m13-staff-{suffix.lower()}@education-os.internal"

    cur.execute(
        """
        INSERT INTO persons (
            id, organization_id, given_names, family_names,
            primary_email, created_at
        )
        VALUES (%s, %s, %s, %s, %s, NOW())
        """,
        (
            person_id,
            organization_id,
            "M13",
            f"Communications {suffix}",
            login_email,
        ),
    )
    cur.execute(
        """
        INSERT INTO staff_profiles (
            id, organization_id, institution_id, person_id,
            staff_code, status, created_at
        )
        VALUES (%s, %s, %s, %s, %s, 'ACTIVE', NOW())
        """,
        (
            staff_profile_id,
            organization_id,
            institution_id,
            person_id,
            f"M13-{suffix}",
        ),
    )
    cur.execute(
        """
        INSERT INTO user_accounts (
            id, person_id, login_email, password_hash,
            is_active, created_at
        )
        VALUES (%s, %s, %s, %s, true, NOW())
        """,
        (
            user_id,
            person_id,
            login_email,
            hash_password("M13-Communications-Temporary-2026!"),
        ),
    )
    cur.execute(
        """
        INSERT INTO memberships (
            id, user_id, institution_id, status, created_at
        )
        VALUES (%s, %s, %s, 'ACTIVE', NOW())
        """,
        (membership_id, user_id, institution_id),
    )

    role_id = None
    if role_key:
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
        assert role is not None, f"{role_key} role missing"
        role_id = role[0]
        cur.execute(
            """
            INSERT INTO membership_roles (membership_id, role_id)
            VALUES (%s, %s)
            """,
            (membership_id, role_id),
        )

    return {
        "person_id": person_id,
        "staff_profile_id": staff_profile_id,
        "user_id": user_id,
        "membership_id": membership_id,
        "role_id": role_id,
        "login_email": login_email,
    }


def _create_guardian_identity(
    cur,
    *,
    organization_id: UUID,
    institution_id: UUID,
    student_profile_id: UUID,
    suffix: str,
) -> dict:
    person_id = uuid4()
    guardian_profile_id = uuid4()
    user_id = uuid4()
    membership_id = uuid4()
    grant_id = uuid4()
    login_email = f"m13-guardian-{suffix.lower()}@education-os.internal"

    cur.execute(
        """
        INSERT INTO persons (
            id, organization_id, given_names, family_names,
            primary_email, created_at
        )
        VALUES (%s, %s, 'M13', %s, %s, NOW())
        """,
        (
            person_id,
            organization_id,
            f"Guardian {suffix}",
            login_email,
        ),
    )
    cur.execute(
        """
        INSERT INTO guardian_profiles (
            id, organization_id, institution_id, person_id,
            guardian_code, status, created_at
        )
        VALUES (%s, %s, %s, %s, %s, 'ACTIVE', NOW())
        """,
        (
            guardian_profile_id,
            organization_id,
            institution_id,
            person_id,
            f"M13-G-{suffix}",
        ),
    )
    cur.execute(
        """
        INSERT INTO user_accounts (
            id, person_id, login_email, password_hash,
            is_active, created_at
        )
        VALUES (%s, %s, %s, %s, true, NOW())
        """,
        (
            user_id,
            person_id,
            login_email,
            hash_password("M13-Guardian-Temporary-2026!"),
        ),
    )
    cur.execute(
        """
        INSERT INTO memberships (
            id, user_id, institution_id, status, created_at
        )
        VALUES (%s, %s, %s, 'ACTIVE', NOW())
        """,
        (membership_id, user_id, institution_id),
    )

    cur.execute(
        """
        SELECT id
        FROM roles
        WHERE institution_id = %s
          AND key = 'GUARDIAN'
        """,
        (institution_id,),
    )
    role = cur.fetchone()
    assert role is not None, "GUARDIAN role missing"
    cur.execute(
        """
        INSERT INTO membership_roles (membership_id, role_id)
        VALUES (%s, %s)
        """,
        (membership_id, role[0]),
    )

    cur.execute(
        """
        INSERT INTO guardian_student_portal_access (
            id, organization_id, institution_id,
            guardian_profile_id, student_profile_id,
            access_level, status, granted_at, revoked_at
        )
        VALUES (%s, %s, %s, %s, %s, 'STANDARD', 'ACTIVE', NOW(), NULL)
        """,
        (
            grant_id,
            organization_id,
            institution_id,
            guardian_profile_id,
            student_profile_id,
        ),
    )

    return {
        "person_id": person_id,
        "guardian_profile_id": guardian_profile_id,
        "user_id": user_id,
        "membership_id": membership_id,
        "grant_id": grant_id,
        "login_email": login_email,
    }



def _create_family_household(
    cur,
    *,
    organization_id: UUID,
    institution_id: UUID,
    student_person_id: UUID,
    suffix: str,
) -> UUID:
    family_id = uuid4()
    family_member_id = uuid4()
    cur.execute(
        """
        INSERT INTO family_households (
            id, organization_id, institution_id,
            name, status, created_at
        )
        VALUES (%s, %s, %s, %s, 'ACTIVE', NOW())
        """,
        (
            family_id,
            organization_id,
            institution_id,
            f"M13 Verification Family {suffix}",
        ),
    )
    cur.execute(
        """
        INSERT INTO family_members (
            id, organization_id, institution_id,
            family_id, person_id, member_role,
            relationship_label, created_at
        )
        VALUES (%s, %s, %s, %s, %s, 'STUDENT', 'Student', NOW())
        """,
        (
            family_member_id,
            organization_id,
            institution_id,
            family_id,
            student_person_id,
        ),
    )
    return family_id


def bootstrap_context() -> dict:
    suffix = uuid4().hex[:8].upper()

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        student = _pick_student(cur)
        organization_id = student["organization_id"]
        institution_id = student["institution_id"]

        sender = _create_staff_identity(
            cur,
            organization_id=organization_id,
            institution_id=institution_id,
            suffix=suffix,
            role_key="ACADEMIC_COORDINATOR",
        )
        roleless = _create_staff_identity(
            cur,
            organization_id=organization_id,
            institution_id=institution_id,
            suffix=f"NO{suffix[:6]}",
            role_key=None,
        )
        guardian = _create_guardian_identity(
            cur,
            organization_id=organization_id,
            institution_id=institution_id,
            student_profile_id=student["student_profile_id"],
            suffix=suffix,
        )
        family_id = _create_family_household(
            cur,
            organization_id=organization_id,
            institution_id=institution_id,
            student_person_id=student["person_id"],
            suffix=suffix,
        )
        conn.commit()

    return {
        "suffix": suffix,
        "organization_id": organization_id,
        "institution_id": institution_id,
        "student": student,
        "sender": sender,
        "roleless": roleless,
        "guardian": guardian,
        "family_id": family_id,
    }


def verify_database_catalog(ctx: dict) -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        assert cur.fetchone() == ("0015_m13",)

        cur.execute(
            """
            SELECT key
            FROM permissions
            WHERE key LIKE 'communications.%'
            ORDER BY key
            """
        )
        assert tuple(row[0] for row in cur.fetchall()) == EXPECTED_PERMISSIONS

        cur.execute(
            """
            SELECT r.key, COUNT(DISTINCT p.key)
            FROM roles r
            JOIN role_permissions rp ON rp.role_id = r.id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE r.institution_id = %s
              AND r.key IN ('SYSTEM_ADMIN','RECTOR','ACADEMIC_COORDINATOR')
              AND p.key LIKE 'communications.%%'
            GROUP BY r.key
            ORDER BY r.key
            """,
            (ctx["institution_id"],),
        )
        grants = {row[0]: int(row[1]) for row in cur.fetchall()}
        assert grants == {
            "ACADEMIC_COORDINATOR": 6,
            "RECTOR": 6,
            "SYSTEM_ADMIN": 6,
        }

        cur.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, r.rolname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_roles r ON r.oid = c.relowner
            WHERE n.nspname = 'public'
              AND c.relname = ANY(%s)
            ORDER BY c.relname
            """,
            (list(M13_TABLES),),
        )
        rows = cur.fetchall()
        assert len(rows) == len(M13_TABLES)
        for _table, rls, force_rls, owner in rows:
            assert rls is True
            assert force_rls is True
            assert owner != "education_app"

        cur.execute(
            """
            SELECT COUNT(*)
            FROM membership_roles mr
            WHERE mr.membership_id = %s
            """,
            (ctx["roleless"]["membership_id"],),
        )
        assert int(cur.fetchone()[0]) == 0

    print("M13 role / permission / RLS catalog: PASSED")


def verify_http_and_delivery(
    base_url: str,
    sender_token: str,
    roleless_token: str,
    guardian_token: str,
    ctx: dict,
) -> dict:
    status, body = _http(base_url, "/api/v1/communications/dashboard")
    assert status == 200 and "Communications Center" in str(body)

    status, body = _http(
        base_url,
        "/api/v1/communications/summary",
        roleless_token,
    )
    assert status == 403, f"roleless: {status} {body}"
    print("M13 roleless-staff negative RBAC boundary: PASSED")

    status, body = _http(
        base_url,
        "/api/v1/communications/summary",
        guardian_token,
    )
    assert status == 403, f"guardian: {status} {body}"
    print("M13 guardian negative staff boundary: PASSED")

    status, summary = _http(
        base_url,
        "/api/v1/communications/summary",
        sender_token,
    )
    assert status == 200, summary

    template_payload = {
        "name": f"M13 Verification {ctx['suffix']}",
        "title_template": "Recordatorio institucional",
        "body_template": "Mensaje institucional verificable para familias.",
        "notice_type": "REMINDER",
        "requires_acknowledgement": True,
    }
    status, template = _http(
        base_url,
        "/api/v1/communications/templates",
        sender_token,
        method="POST",
        payload=template_payload,
    )
    assert status == 201, template

    title = f"M13 Family Communication {ctx['suffix']}"
    message_payload = {
        "template_id": template["id"],
        "title": title,
        "body": "Comunicación M13 de verificación end-to-end.",
        "notice_type": "ANNOUNCEMENT",
        "requires_acknowledgement": True,
    }
    status, message = _http(
        base_url,
        "/api/v1/communications/messages",
        sender_token,
        method="POST",
        payload=message_payload,
    )
    assert status == 201, message
    communication_id = message["id"]

    status, targets = _http(
        base_url,
        f"/api/v1/communications/messages/{communication_id}/targets",
        sender_token,
        method="PUT",
        payload={
            "targets": [
                {
                    "target_type": "FAMILY",
                    "target_id": str(ctx["family_id"]),
                },
                {
                    "target_type": "STUDENT",
                    "target_id": str(ctx["student"]["student_profile_id"]),
                },
            ]
        },
    )
    assert status == 200 and len(targets) == 2, targets
    assert {item["target_type"] for item in targets} == {"FAMILY", "STUDENT"}

    status, preview = _http(
        base_url,
        f"/api/v1/communications/messages/{communication_id}/preview",
        sender_token,
    )
    assert status == 200, preview
    assert preview["target_count"] == 2
    assert preview["target_students"] == 1
    assert preview["reachable_students"] == 1
    assert preview["guardian_recipients"] >= 1
    print("M13 FAMILY + STUDENT target union/dedupe + preview: PASSED")

    status, published = _http(
        base_url,
        f"/api/v1/communications/messages/{communication_id}/publish",
        sender_token,
        method="POST",
    )
    assert status == 200, published
    assert published["students_reached"] == 1
    assert published["family_notices_created"] == 1
    assert published["guardian_recipients"] >= 1
    print("M13 publish + legacy FamilyNotice projection: PASSED")

    status, notices = _http(
        base_url,
        "/api/v1/guardian/notices",
        guardian_token,
    )
    assert status == 200, notices
    matching = [item for item in notices if item["title"] == title]
    assert len(matching) == 1, matching
    family_notice_id = matching[0]["notice_id"]
    print("M13 -> M12 Guardian Console visibility: PASSED")

    status, ack = _http(
        base_url,
        f"/api/v1/guardian/notices/{family_notice_id}/acknowledge",
        guardian_token,
        method="POST",
    )
    assert status == 200, ack

    status, delivery = _http(
        base_url,
        f"/api/v1/communications/messages/{communication_id}/delivery",
        sender_token,
    )
    assert status == 200, delivery
    assert delivery["recipients_total"] >= 1
    own = [
        item
        for item in delivery["recipients"]
        if item["guardian_profile_id"]
        == str(ctx["guardian"]["guardian_profile_id"])
    ]
    assert len(own) == 1
    assert own[0]["status"] == "ACKNOWLEDGED"
    assert delivery["acknowledged"] >= 1
    print("M13 read / acknowledgement delivery telemetry: PASSED")

    protected_negative_paths = (
        "/api/v1/admin/summary",
        "/api/v1/teacher/summary",
        "/api/v1/student/me",
        "/api/v1/coordination/summary",
        "/api/v1/operations/security-baseline",
    )
    for path in protected_negative_paths:
        status, body = _http(base_url, path, guardian_token)
        assert status == 403, f"{path}: {status} {body}"
    print("M13 guardian elevated/staff boundaries: PASSED")

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM audit_logs
            WHERE entity_id = %s
              AND action = 'COMMUNICATION_PUBLISHED'
            """,
            (UUID(communication_id),),
        )
        assert int(cur.fetchone()[0]) == 1

        cur.execute(
            """
            SELECT COUNT(*)
            FROM communication_recipients
            WHERE communication_id = %s
              AND family_notice_id = %s
            """,
            (UUID(communication_id), UUID(family_notice_id)),
        )
        assert int(cur.fetchone()[0]) >= 1

        cur.execute(
            """
            SELECT COUNT(*)
            FROM outbox_events
            WHERE aggregate_id = %s
              AND aggregate_type = 'communication'
              AND event_type = 'COMMUNICATION_PUBLISHED'
            """,
            (UUID(communication_id),),
        )
        assert int(cur.fetchone()[0]) == 1

    print("M13 audit + outbox + recipient persistence: PASSED")
    return {
        "communication_id": communication_id,
        "title": title,
        "family_notice_id": family_notice_id,
    }


def verify_real_browser(
    base_url: str,
    sender_token: str,
    published: dict,
) -> None:
    from playwright.sync_api import sync_playwright

    evidence_dir = Path(
        os.getenv(
            "M13_EVIDENCE_DIR",
            str(Path.home() / "Downloads" / "Education_OS_M13_Evidence"),
        )
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    screenshot = evidence_dir / "m13_communications_center_edge.png"

    edge = _edge_path()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=edge,
            headless=True,
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(
            f"{base_url}/api/v1/communications/dashboard",
            wait_until="domcontentloaded",
        )
        page.fill("#token", sender_token)
        page.click("button:has-text('Conectar')")
        page.wait_for_function(
            """
            () => document.getElementById('status')?.textContent
                ?.includes('Communications Center actualizado.')
            """,
            timeout=15000,
        )
        page.wait_for_function(
            f"""
            () => document.body.innerText.includes(
                {json.dumps(published["title"])}
            )
            """,
            timeout=10000,
        )
        page.screenshot(path=str(screenshot), full_page=True)
        browser.close()

    assert screenshot.exists() and screenshot.stat().st_size > 0
    print(f"M13 browser screenshot={screenshot}")
    print("M13 REAL BROWSER ACCEPTANCE: PASSED")


def main() -> None:
    ctx = bootstrap_context()

    sender_token = create_access_token(
        user_id=UUID(str(ctx["sender"]["user_id"])),
        organization_id=UUID(str(ctx["organization_id"])),
        institution_id=UUID(str(ctx["institution_id"])),
    )
    roleless_token = create_access_token(
        user_id=UUID(str(ctx["roleless"]["user_id"])),
        organization_id=UUID(str(ctx["organization_id"])),
        institution_id=UUID(str(ctx["institution_id"])),
    )
    guardian_token = create_access_token(
        user_id=UUID(str(ctx["guardian"]["user_id"])),
        organization_id=UUID(str(ctx["organization_id"])),
        institution_id=UUID(str(ctx["institution_id"])),
    )

    verify_database_catalog(ctx)

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
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
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_server(base_url, process)
        print(f"M13 actual HTTP server READY at {base_url}")
        published = verify_http_and_delivery(
            base_url,
            sender_token,
            roleless_token,
            guardian_token,
            ctx,
        )
        verify_real_browser(
            base_url,
            sender_token,
            published,
        )
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    print(
        "M13 Communications Center verifier: PASSED | "
        f"sender={ctx['sender']['login_email']}"
    )


if __name__ == "__main__":
    main()
