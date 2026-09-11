from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
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
    "guardian.attendance.view",
    "guardian.console.access",
    "guardian.grades.view",
    "guardian.notices.acknowledge",
    "guardian.notices.view",
    "guardian.progress.view",
    "guardian.schedule.view",
    "guardian.students.view",
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http(
    base_url: str,
    path: str,
    token: str | None = None,
    method: str = "GET",
) -> tuple[int, object]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(
        f"{base_url}{path}",
        headers=headers,
        method=method,
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
                "/api/v1/guardian/dashboard",
            )
            if status == 200 and "Guardian Console" in str(body):
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


def _pick_two_students(cur) -> tuple[dict, dict]:
    cur.execute(
        """
        SELECT DISTINCT ON (sp.id)
            sp.id,
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
        """
    )
    groups: dict[UUID, list[dict]] = defaultdict(list)
    for row in cur.fetchall():
        groups[row[2]].append(
            {
                "student_profile_id": row[0],
                "organization_id": row[1],
                "institution_id": row[2],
                "student_name": row[3],
            }
        )

    for students in groups.values():
        if len(students) >= 2:
            return students[0], students[1]

    raise AssertionError(
        "M12 verifier requires two active students in one institution"
    )


def _create_guardian_identity(
    cur,
    *,
    organization_id: UUID,
    institution_id: UUID,
    suffix: str,
    with_role: bool,
) -> dict:
    person_id = uuid4()
    guardian_profile_id = uuid4()
    user_id = uuid4()
    membership_id = uuid4()
    login_email = (
        f"m12-guardian-{suffix.lower()}@education-os.internal"
    )

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
            "M12",
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
            f"M12-{suffix}",
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
            hash_password("M12-Guardian-Temporary-2026!"),
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
    if with_role:
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
        assert role is not None, "GUARDIAN role missing after M12 migration"
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
        "guardian_profile_id": guardian_profile_id,
        "user_id": user_id,
        "membership_id": membership_id,
        "login_email": login_email,
        "role_id": role_id,
    }


def bootstrap_guardian_context() -> dict:
    suffix = uuid4().hex[:8].upper()

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        student_a, student_b = _pick_two_students(cur)
        organization_id = student_a["organization_id"]
        institution_id = student_a["institution_id"]

        guardian = _create_guardian_identity(
            cur,
            organization_id=organization_id,
            institution_id=institution_id,
            suffix=suffix,
            with_role=True,
        )
        roleless = _create_guardian_identity(
            cur,
            organization_id=organization_id,
            institution_id=institution_id,
            suffix=f"NO{suffix[:6]}",
            with_role=False,
        )

        grant_id = uuid4()
        cur.execute(
            """
            INSERT INTO guardian_student_portal_access (
                id, organization_id, institution_id,
                guardian_profile_id, student_profile_id,
                access_level, status, granted_at, revoked_at
            )
            VALUES (
                %s, %s, %s, %s, %s,
                'STANDARD', 'ACTIVE', NOW(), NULL
            )
            """,
            (
                grant_id,
                organization_id,
                institution_id,
                guardian["guardian_profile_id"],
                student_a["student_profile_id"],
            ),
        )

        general_notice_id = uuid4()
        api_notice_id = uuid4()
        browser_notice_id = uuid4()
        hidden_notice_id = uuid4()

        notices = (
            (
                general_notice_id,
                None,
                "ANNOUNCEMENT",
                f"M12 general notice {suffix}",
                f"M12 general visibility {suffix}",
                False,
            ),
            (
                api_notice_id,
                student_a["student_profile_id"],
                "ACADEMIC",
                f"M12 API acknowledgement {suffix}",
                f"M12 API acknowledgement body {suffix}",
                True,
            ),
            (
                browser_notice_id,
                student_a["student_profile_id"],
                "ACADEMIC",
                f"M12 browser acknowledgement {suffix}",
                f"M12 browser acknowledgement body {suffix}",
                True,
            ),
            (
                hidden_notice_id,
                student_b["student_profile_id"],
                "ACADEMIC",
                f"M12 hidden notice {suffix}",
                f"M12 isolation control {suffix}",
                True,
            ),
        )

        for (
            notice_id,
            student_profile_id,
            notice_type,
            title,
            body,
            requires_ack,
        ) in notices:
            cur.execute(
                """
                INSERT INTO family_notices (
                    id, organization_id, institution_id,
                    student_profile_id, notice_type, title, body,
                    requires_acknowledgement, status, published_at,
                    created_by_user_id, created_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, 'PUBLISHED', NOW(), NULL, NOW()
                )
                """,
                (
                    notice_id,
                    organization_id,
                    institution_id,
                    student_profile_id,
                    notice_type,
                    title,
                    body,
                    requires_ack,
                ),
            )

        conn.commit()

    return {
        "suffix": suffix,
        "organization_id": organization_id,
        "institution_id": institution_id,
        "student_a": student_a,
        "student_b": student_b,
        "grant_id": grant_id,
        "guardian": guardian,
        "roleless": roleless,
        "general_notice_id": general_notice_id,
        "api_notice_id": api_notice_id,
        "browser_notice_id": browser_notice_id,
        "hidden_notice_id": hidden_notice_id,
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
              AND key = 'GUARDIAN'
            """,
            (ctx["institution_id"],),
        )
        assert cur.fetchone()[0] == 1

        cur.execute(
            """
            SELECT COUNT(*)
            FROM membership_roles
            WHERE membership_id = %s
            """,
            (ctx["roleless"]["membership_id"],),
        )
        assert cur.fetchone()[0] == 0

        cur.execute("SELECT version_num FROM alembic_version")
        assert cur.fetchone() == ("0014_m12",)

    print("M12 role / permission catalog + non-auto-assignment: PASSED")


def verify_http_and_scope(
    base_url: str,
    token: str,
    roleless_token: str,
    ctx: dict,
) -> None:
    status, body = _http(base_url, "/api/v1/guardian/me", roleless_token)
    assert status == 403, (status, body)
    print("M12 roleless guardian negative RBAC boundary: PASSED")

    status, me = _http(base_url, "/api/v1/guardian/me", token)
    assert status == 200, (status, me)
    assert me["linked_students"] == 1

    status, students = _http(base_url, "/api/v1/guardian/students", token)
    assert status == 200, (status, students)
    ids = {item["student_profile_id"] for item in students}
    assert str(ctx["student_a"]["student_profile_id"]) in ids
    assert str(ctx["student_b"]["student_profile_id"]) not in ids

    student_id = ctx["student_a"]["student_profile_id"]
    for suffix in (
        "summary",
        "classes",
        "schedule",
        "attendance",
        "grades",
        "pending",
        "progress",
    ):
        status, body = _http(
            base_url,
            f"/api/v1/guardian/students/{student_id}/{suffix}",
            token,
        )
        assert status == 200, (suffix, status, body)

    hidden_id = ctx["student_b"]["student_profile_id"]
    status, body = _http(
        base_url,
        f"/api/v1/guardian/students/{hidden_id}/summary",
        token,
    )
    assert status == 404, (status, body)
    print("M12 active-grant student isolation: PASSED")

    status, notices = _http(base_url, "/api/v1/guardian/notices", token)
    assert status == 200, (status, notices)
    notice_ids = {item["notice_id"] for item in notices}
    assert str(ctx["general_notice_id"]) in notice_ids
    assert str(ctx["api_notice_id"]) in notice_ids
    assert str(ctx["browser_notice_id"]) in notice_ids
    assert str(ctx["hidden_notice_id"]) not in notice_ids
    print("M12 notice visibility isolation: PASSED")

    status, body = _http(
        base_url,
        f"/api/v1/guardian/notices/{ctx['api_notice_id']}/acknowledge",
        token,
        method="POST",
    )
    assert status == 200, (status, body)
    assert body["notice_id"] == str(ctx["api_notice_id"])

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT acknowledged_at
            FROM family_notice_receipts
            WHERE family_notice_id = %s
              AND guardian_profile_id = %s
            """,
            (
                ctx["api_notice_id"],
                ctx["guardian"]["guardian_profile_id"],
            ),
        )
        receipt = cur.fetchone()
        assert receipt is not None and receipt[0] is not None
    print("M12 notice acknowledgement persistence: PASSED")

    # M6 compatibility stays alive and keeps the same guardian grant scope.
    status, legacy_me = _http(
        base_url,
        "/api/v1/family-portal/me",
        token,
    )
    assert status == 200, (status, legacy_me)

    status, legacy_children = _http(
        base_url,
        "/api/v1/family-portal/children",
        token,
    )
    assert status == 200, (status, legacy_children)
    legacy_ids = {
        item["student_profile_id"]
        for item in legacy_children
    }
    assert str(ctx["student_a"]["student_profile_id"]) in legacy_ids
    assert str(ctx["student_b"]["student_profile_id"]) not in legacy_ids
    print("M6 Family Portal compatibility + scope: PASSED")

    denied_paths = (
        "/api/v1/teacher/summary",
        "/api/v1/student/me",
        "/api/v1/coordination/summary",
        "/api/v1/operations/security-baseline",
    )
    for path in denied_paths:
        status, body = _http(base_url, path, token)
        assert status == 403, f"{path}: {status} {body}"
    print("M12 non-guardian elevated/staff boundaries: PASSED")


def verify_real_browser(base_url: str, token: str, ctx: dict) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright Python package is required for M12 browser acceptance"
        ) from exc

    evidence_dir = Path(
        os.getenv(
            "M12_EVIDENCE_DIR",
            str(BACKEND_ROOT / ".m12-evidence"),
        )
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    screenshot = evidence_dir / "m12_guardian_dashboard.png"

    edge = _edge_path()
    print(f"M12 browser executable={edge}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=edge,
        )
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(
                f"{base_url}/api/v1/guardian/dashboard",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            page.locator("#guardian-token").fill(token)
            page.locator("#guardian-connect").click()
            page.wait_for_function(
                """() => {
                    const el = document.querySelector('#guardian-status');
                    return el && el.textContent.includes(
                        'Guardian Console actualizado.'
                    );
                }""",
                timeout=30000,
            )

            student_a = ctx["student_a"]
            student_b = ctx["student_b"]
            sidebar = page.locator("#guardian-students-list").inner_text()
            assert student_a["student_name"] in sidebar
            assert student_b["student_name"] not in sidebar

            page.locator("#guardian-tab-notices").click()
            notices_panel = page.locator("#guardian-notices-panel")
            assert notices_panel.is_visible()
            assert (
                f"M12 browser acknowledgement {ctx['suffix']}"
                in notices_panel.inner_text()
            )
            assert (
                f"M12 hidden notice {ctx['suffix']}"
                not in notices_panel.inner_text()
            )

            ack_selector = (
                f'[data-ack-notice="{ctx["browser_notice_id"]}"]'
            )
            page.locator(ack_selector).click()
            page.wait_for_function(
                """() => {
                    const el = document.querySelector('#guardian-status');
                    return el && el.textContent.includes('Aviso confirmado.');
                }""",
                timeout=30000,
            )
            page.wait_for_timeout(250)
            assert page.locator(ack_selector).count() == 0

            page.screenshot(path=str(screenshot), full_page=True)
        finally:
            browser.close()

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT acknowledged_at
            FROM family_notice_receipts
            WHERE family_notice_id = %s
              AND guardian_profile_id = %s
            """,
            (
                ctx["browser_notice_id"],
                ctx["guardian"]["guardian_profile_id"],
            ),
        )
        receipt = cur.fetchone()
        assert receipt is not None and receipt[0] is not None

    print(f"M12 browser screenshot={screenshot}")
    print("M12 REAL BROWSER ACCEPTANCE: PASSED")


def main() -> None:
    ctx = bootstrap_guardian_context()

    token = create_access_token(
        user_id=UUID(str(ctx["guardian"]["user_id"])),
        organization_id=UUID(str(ctx["organization_id"])),
        institution_id=UUID(str(ctx["institution_id"])),
    )
    roleless_token = create_access_token(
        user_id=UUID(str(ctx["roleless"]["user_id"])),
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
        print(f"M12 actual HTTP server READY at {base_url}")
        verify_http_and_scope(
            base_url,
            token,
            roleless_token,
            ctx,
        )
        verify_real_browser(base_url, token, ctx)
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    print(f"M12 verifier login={ctx['guardian']['login_email']}")
    print("M12 Guardian Console verifier: PASSED")


if __name__ == "__main__":
    main()
