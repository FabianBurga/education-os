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
        assert row is not None, "M15 verifier requires one active institution"
        return {
            "organization_id": row[0],
            "institution_id": row[1],
            "institution_name": row[2],
            "institution_type": row[3],
        }


def _create_staff_actor(
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
    login_email = f"m15-{suffix.lower()}@education-os.internal"

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
        VALUES (%s, %s, 'M15', %s, %s, NOW())
        """,
        (
            person_id,
            organization_id,
            suffix,
            login_email,
        ),
    )
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
            staff_profile_id,
            organization_id,
            institution_id,
            person_id,
            f"M15-{suffix}",
        ),
    )
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
            hash_password("M15-Unified-Frontend-Temporary-2026!"),
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
        assert role is not None, f"{role_key} role not found"
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


def _bootstrap_actors(ctx: dict) -> dict:
    suffix = uuid4().hex[:8].upper()
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        admin = _create_staff_actor(
            cur,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            suffix=f"ADMIN-{suffix}",
            role_key="SYSTEM_ADMIN",
        )
        roleless = _create_staff_actor(
            cur,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            suffix=f"NONE-{suffix}",
            role_key=None,
        )
        conn.commit()

    return {
        "admin": admin,
        "roleless": roleless,
    }


def _assert_frontend_build() -> None:
    index = FRONTEND_DIST / "index.html"
    assert index.is_file(), (
        "frontend/dist/index.html missing; run npm run build before M15 verifier"
    )
    assets = FRONTEND_DIST / "assets"
    assert assets.is_dir(), "frontend/dist/assets missing"
    assert any(assets.iterdir()), "frontend/dist/assets is empty"
    print("M15 frontend build artifact: PASSED")


def _verify_http(
    base_url: str,
    admin_token: str,
    roleless_token: str,
    ctx: dict,
) -> None:
    status, body = _http(base_url, "/api/v1/ui/bootstrap")
    assert status == 401, f"unauthenticated bootstrap: {status} {body}"

    status, roleless = _http(
        base_url,
        "/api/v1/ui/bootstrap",
        roleless_token,
    )
    assert status == 200 and isinstance(roleless, dict), roleless
    assert roleless["roles"] == []
    assert roleless["permissions"] == []
    assert roleless["profiles"]["staff"] is True
    print("M15 authenticated roleless shell context: PASSED")

    status, bootstrap = _http(
        base_url,
        "/api/v1/ui/bootstrap",
        admin_token,
    )
    assert status == 200 and isinstance(bootstrap, dict), bootstrap
    assert bootstrap["tenant"]["institution_id"] == str(ctx["institution_id"])
    assert bootstrap["tenant"]["institution_name"] == ctx["institution_name"]
    assert "SYSTEM_ADMIN" in bootstrap["roles"]
    assert "admin.console.access" in bootstrap["permissions"]
    assert "communications.console.access" in bootstrap["permissions"]
    assert "finance.console.access" in bootstrap["permissions"]
    assert bootstrap["profiles"]["staff"] is True
    assert "finance.billing" in bootstrap["capabilities"]
    print("M15 unified identity/roles/permissions/capabilities bootstrap: PASSED")

    status, campuses = _http(
        base_url,
        "/api/v1/campuses",
        admin_token,
    )
    assert status == 200 and isinstance(campuses, list), campuses
    assert len(campuses) >= 1
    print("M15 RLS-protected campus resource through unified session: PASSED")

    status, app_html = _http(base_url, "/app/")
    assert status == 200 and "<div id=\"root\"></div>" in str(app_html)

    status, deep_link = _http(
        base_url,
        "/app/workspace/administration",
    )
    assert status == 200 and "<div id=\"root\"></div>" in str(deep_link)
    print("M15 integrated SPA root + deep-link fallback: PASSED")


def _verify_real_browser(
    base_url: str,
    admin_token: str,
    ctx: dict,
) -> None:
    from playwright.sync_api import sync_playwright

    evidence_dir = Path(
        os.getenv(
            "M15_EVIDENCE_DIR",
            str(Path.home() / "Downloads" / "Education_OS_M15_Evidence"),
        )
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    screenshot = evidence_dir / "m15_unified_frontend_edge.png"

    edge = _edge_path()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=edge,
            headless=True,
        )
        page = browser.new_page(
            viewport={"width": 1500, "height": 1050},
        )
        page.goto(
            f"{base_url}/app/",
            wait_until="domcontentloaded",
        )

        page.get_by_test_id("unified-token-input").fill(admin_token)
        page.get_by_test_id("unified-enter-button").click()

        home = page.get_by_test_id("unified-home")
        home.wait_for(timeout=15000)
        home.get_by_text(ctx["institution_name"], exact=True).wait_for()

        administration_link = home.locator(
            'a[href="/app/workspace/administration"]'
        )
        communications_link = home.locator(
            'a[href="/app/workspace/communications"]'
        )
        finance_link = home.locator(
            'a[href="/app/workspace/finance"]'
        )

        administration_link.wait_for()
        communications_link.wait_for()
        finance_link.wait_for()
        home.get_by_text("Campus visibles por RLS", exact=True).wait_for()

        administration_link.click()
        workspace = page.get_by_test_id("workspace-administration")
        workspace.wait_for(timeout=10000)
        workspace.get_by_text(
            "Vista unificada de Administración",
            exact=True,
        ).wait_for()

        page.screenshot(path=str(screenshot), full_page=True)
        browser.close()

    assert screenshot.is_file()
    assert screenshot.stat().st_size > 0
    print(f"M15 browser screenshot={screenshot}")
    print("M15 REAL MICROSOFT EDGE ACCEPTANCE: PASSED")


def main() -> None:
    _assert_frontend_build()

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        assert cur.fetchone() == ("0016_m14",)

    ctx = _pick_tenant()
    actors = _bootstrap_actors(ctx)

    admin_token = create_access_token(
        user_id=UUID(str(actors["admin"]["user_id"])),
        organization_id=UUID(str(ctx["organization_id"])),
        institution_id=UUID(str(ctx["institution_id"])),
    )
    roleless_token = create_access_token(
        user_id=UUID(str(actors["roleless"]["user_id"])),
        organization_id=UUID(str(ctx["organization_id"])),
        institution_id=UUID(str(ctx["institution_id"])),
    )

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

    try:
        _wait_server(base_url, process)
        print(f"M15 actual HTTP server READY at {base_url}")
        _verify_http(
            base_url,
            admin_token,
            roleless_token,
            ctx,
        )
        _verify_real_browser(
            base_url,
            admin_token,
            ctx,
        )
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    print(
        "M15 Unified Frontend Foundation verifier: PASSED | "
        f"admin={actors['admin']['login_email']}"
    )


if __name__ == "__main__":
    main()
