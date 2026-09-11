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
    "student.attendance.view",
    "student.classes.view",
    "student.console.access",
    "student.grades.view",
    "student.notices.view",
    "student.profile.view",
    "student.progress.view",
    "student.schedule.view",
)


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
        with urllib.request.urlopen(request, timeout=10) as response:
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
                "uvicorn exited early with code "
                f"{process.returncode}: {output}"
            )
        try:
            status, body = _http(
                base_url,
                "/api/v1/student/dashboard",
            )
            if status == 200 and "Student Console" in str(body):
                return
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"HTTP server not ready: {last_error}")


def _edge_path() -> str:
    candidates = (
        Path(
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        ),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    raise RuntimeError("Microsoft Edge executable not found")


def bootstrap_student_context() -> dict:
    suffix = uuid4().hex[:8].upper()

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                sp.id,
                sp.person_id,
                sp.organization_id,
                sp.institution_id,
                p.given_names,
                p.family_names,
                e.id,
                e.academic_period_id,
                ssa.id,
                ssa.section_id,
                co.id
            FROM student_profiles sp
            JOIN persons p ON p.id = sp.person_id
            JOIN enrollments e
              ON e.student_profile_id = sp.id
             AND e.status = 'ACTIVE'
            JOIN student_section_assignments ssa
              ON ssa.enrollment_id = e.id
             AND ssa.status = 'ACTIVE'
            JOIN course_offerings co
              ON co.section_id = ssa.section_id
             AND co.academic_period_id = ssa.academic_period_id
             AND co.status = 'ACTIVE'
            WHERE sp.status = 'ACTIVE'
              AND NOT EXISTS (
                  SELECT 1
                  FROM user_accounts ua
                  WHERE ua.person_id = sp.person_id
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM staff_profiles st
                  WHERE st.person_id = sp.person_id
                    AND st.institution_id = sp.institution_id
                    AND st.status = 'ACTIVE'
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM guardian_profiles gp
                  WHERE gp.person_id = sp.person_id
                    AND gp.institution_id = sp.institution_id
                    AND gp.status = 'ACTIVE'
              )
            ORDER BY sp.created_at, co.created_at
            LIMIT 1
            """
        )
        row = cur.fetchone()
        assert row is not None, (
            "M11 verifier requires one active student with enrollment, "
            "section, course and no existing user/staff/guardian identity"
        )
        (
            student_profile_id,
            person_id,
            organization_id,
            institution_id,
            given_names,
            family_names,
            enrollment_id,
            academic_period_id,
            student_section_assignment_id,
            section_id,
            course_offering_id,
        ) = row

        cur.execute(
            """
            SELECT id
            FROM roles
            WHERE institution_id = %s
              AND key = 'STUDENT'
            """,
            (institution_id,),
        )
        role = cur.fetchone()
        assert role is not None, "STUDENT role missing after M11 migration"
        student_role_id = role[0]

        user_id = uuid4()
        membership_id = uuid4()
        login_email = (
            f"m11-student-{suffix.lower()}@education-os.internal"
        )

        cur.execute(
            """
            INSERT INTO user_accounts (
                id, person_id, login_email, password_hash, is_active, created_at
            )
            VALUES (%s, %s, %s, %s, true, NOW())
            """,
            (
                user_id,
                person_id,
                login_email,
                hash_password("M11-Student-Temporary-2026!"),
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
            INSERT INTO membership_roles (membership_id, role_id)
            VALUES (%s, %s)
            """,
            (membership_id, student_role_id),
        )

        own_notice_id = uuid4()
        cur.execute(
            """
            INSERT INTO family_notices (
                id, organization_id, institution_id, student_profile_id,
                notice_type, title, body, requires_acknowledgement,
                status, published_at, created_by_user_id, created_at
            )
            VALUES (
                %s, %s, %s, %s,
                'ACADEMIC', %s, %s, false,
                'PUBLISHED', NOW(), NULL, NOW()
            )
            """,
            (
                own_notice_id,
                organization_id,
                institution_id,
                student_profile_id,
                f"M11 personal notice {suffix}",
                f"M11 own-student RLS verification {suffix}",
            ),
        )

        cur.execute(
            """
            SELECT sp.id
            FROM student_profiles sp
            WHERE sp.institution_id = %s
              AND sp.status = 'ACTIVE'
              AND sp.id <> %s
            ORDER BY sp.created_at
            LIMIT 1
            """,
            (institution_id, student_profile_id),
        )
        other = cur.fetchone()
        other_notice_id = None
        if other is not None:
            other_notice_id = uuid4()
            cur.execute(
                """
                INSERT INTO family_notices (
                    id, organization_id, institution_id, student_profile_id,
                    notice_type, title, body, requires_acknowledgement,
                    status, published_at, created_by_user_id, created_at
                )
                VALUES (
                    %s, %s, %s, %s,
                    'ACADEMIC', %s, %s, false,
                    'PUBLISHED', NOW(), NULL, NOW()
                )
                """,
                (
                    other_notice_id,
                    organization_id,
                    institution_id,
                    other[0],
                    f"M11 other-student notice {suffix}",
                    f"M11 isolation control {suffix}",
                ),
            )

        general_notice_id = uuid4()
        cur.execute(
            """
            INSERT INTO family_notices (
                id, organization_id, institution_id, student_profile_id,
                notice_type, title, body, requires_acknowledgement,
                status, published_at, created_by_user_id, created_at
            )
            VALUES (
                %s, %s, %s, NULL,
                'ANNOUNCEMENT', %s, %s, false,
                'PUBLISHED', NOW(), NULL, NOW()
            )
            """,
            (
                general_notice_id,
                organization_id,
                institution_id,
                f"M11 general notice {suffix}",
                f"M11 general visibility verification {suffix}",
            ),
        )

        conn.commit()

    return {
        "suffix": suffix,
        "student_profile_id": student_profile_id,
        "person_id": person_id,
        "organization_id": organization_id,
        "institution_id": institution_id,
        "given_names": given_names,
        "family_names": family_names,
        "student_name": f"{given_names} {family_names}".strip(),
        "enrollment_id": enrollment_id,
        "academic_period_id": academic_period_id,
        "student_section_assignment_id": student_section_assignment_id,
        "section_id": section_id,
        "course_offering_id": course_offering_id,
        "user_id": user_id,
        "membership_id": membership_id,
        "login_email": login_email,
        "own_notice_id": own_notice_id,
        "other_notice_id": other_notice_id,
        "general_notice_id": general_notice_id,
    }


def verify_database_catalog(ctx: dict) -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT key
            FROM permissions
            WHERE key = ANY(%s)
            ORDER BY key
            """,
            (list(EXPECTED_PERMISSIONS),),
        )
        keys = tuple(row[0] for row in cur.fetchall())
        assert keys == EXPECTED_PERMISSIONS, keys

        cur.execute(
            """
            SELECT COUNT(*)
            FROM roles
            WHERE institution_id = %s
              AND key = 'STUDENT'
            """,
            (ctx["institution_id"],),
        )
        assert cur.fetchone()[0] == 1

        cur.execute(
            """
            SELECT qual
            FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = 'family_notices'
              AND policyname = 'family_notices_select'
            """
        )
        policy = cur.fetchone()
        assert policy is not None
        policy_text = str(policy[0])
        assert "student_profiles" in policy_text
        assert "guardian_student_portal_access" in policy_text
        assert "staff_profiles" in policy_text

        cur.execute(
            "SELECT version_num FROM alembic_version"
        )
        assert cur.fetchone() == ("0013_m11",)

    print("M11 role / permission / RLS catalog: PASSED")


def verify_http_and_scope(base_url: str, token: str, ctx: dict) -> None:
    expected_paths = (
        "/api/v1/student/me",
        "/api/v1/student/summary",
        "/api/v1/student/classes",
        "/api/v1/student/schedule",
        "/api/v1/student/attendance",
        "/api/v1/student/grades",
        "/api/v1/student/pending",
        "/api/v1/student/progress",
        "/api/v1/student/notices",
    )
    bodies = {}
    for path in expected_paths:
        status, body = _http(base_url, path, token)
        assert status == 200, f"{path}: {status} {body}"
        bodies[path] = body

    profile = bodies["/api/v1/student/me"]
    assert profile["student_profile_id"] == str(ctx["student_profile_id"])
    assert profile["student_name"] == ctx["student_name"]

    classes = bodies["/api/v1/student/classes"]
    assert any(
        item["course_offering_id"] == str(ctx["course_offering_id"])
        for item in classes
    )

    notices = bodies["/api/v1/student/notices"]
    notice_ids = {item["notice_id"] for item in notices}
    assert str(ctx["own_notice_id"]) in notice_ids
    assert str(ctx["general_notice_id"]) in notice_ids
    if ctx["other_notice_id"] is not None:
        assert str(ctx["other_notice_id"]) not in notice_ids

    print("M11 own-student API scope + notice isolation: PASSED")

    denied_paths = (
        "/api/v1/students",
        "/api/v1/academics/sections",
        "/api/v1/attendance/codes",
        "/api/v1/grades/assessments",
        "/api/v1/automation/cases",
        "/api/v1/operations/security-baseline",
        "/api/v1/admin/summary",
        "/api/v1/coordination/summary",
        "/api/v1/teacher/summary",
        "/api/v1/family-portal/me",
    )
    for path in denied_paths:
        status, body = _http(base_url, path, token)
        assert status == 403, f"boundary {path}: {status} {body}"

    print("M11 non-student/elevated negative boundaries: PASSED")


def verify_real_browser(base_url: str, token: str, ctx: dict) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright Python package is required for M11 browser acceptance"
        ) from exc

    evidence_dir = Path(
        os.getenv(
            "M11_EVIDENCE_DIR",
            str(BACKEND_ROOT / ".m11-evidence"),
        )
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    screenshot = evidence_dir / "m11_student_dashboard.png"

    edge = _edge_path()
    print(f"M11 browser executable={edge}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=edge,
        )
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(
                f"{base_url}/api/v1/student/dashboard",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            page.locator("#student-token").fill(token)
            page.locator("#student-connect").click()
            page.wait_for_function(
                """() => {
                    const el = document.querySelector('#student-status');
                    return el && el.textContent.includes(
                        'Student Console actualizado.'
                    );
                }""",
                timeout=30000,
            )

            profile_name = page.locator("#student-profile-name").inner_text()
            assert profile_name.strip() == ctx["student_name"]

            page.locator("#tab-classes-btn").click()
            classes_panel = page.locator("#student-classes-panel")
            assert classes_panel.is_visible()

            page.locator("#tab-notices-btn").click()
            notices_panel = page.locator("#student-notices-panel")
            assert notices_panel.is_visible()
            assert (
                f"M11 personal notice {ctx['suffix']}"
                in notices_panel.inner_text()
            )
            assert (
                f"M11 other-student notice {ctx['suffix']}"
                not in notices_panel.inner_text()
            )

            page.screenshot(path=str(screenshot), full_page=True)
        finally:
            browser.close()

    print(f"M11 browser screenshot={screenshot}")
    print("M11 REAL BROWSER ACCEPTANCE: PASSED")


def main() -> None:
    ctx = bootstrap_student_context()
    token = create_access_token(
        user_id=UUID(str(ctx["user_id"])),
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
        print(f"M11 actual HTTP server READY at {base_url}")
        verify_http_and_scope(base_url, token, ctx)
        verify_real_browser(base_url, token, ctx)
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    print(f"M11 verifier login={ctx['login_email']}")
    print("M11 Student Console verifier: PASSED")


if __name__ == "__main__":
    main()
