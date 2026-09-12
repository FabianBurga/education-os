from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
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
    "finance.capability.manage",
    "finance.charges.manage",
    "finance.concepts.manage",
    "finance.console.access",
    "finance.payments.manage",
    "finance.reversals.manage",
    "finance.statements.view",
    "finance.summary.view",
)

FINANCE_TABLES = (
    "billing_accounts",
    "billing_allocations",
    "billing_charges",
    "billing_concepts",
    "billing_payments",
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
            status, body = _http(base_url, "/api/v1/finance/dashboard")
            if status == 200 and "Finance / Billing Core" in str(body):
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


def pick_student_context() -> dict:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
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
            WHERE sp.status = 'ACTIVE'
            ORDER BY sp.id, e.created_at DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        assert row is not None, "M14 verifier requires one active enrolled student"
        return {
            "student_profile_id": row[0],
            "organization_id": row[1],
            "institution_id": row[2],
            "student_name": row[3],
        }


def verify_migration_catalog(ctx: dict) -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        assert cur.fetchone() == ("0016_m14",)

        cur.execute(
            """
            SELECT key
            FROM permissions
            WHERE key LIKE 'finance.%'
            ORDER BY key
            """
        )
        assert tuple(row[0] for row in cur.fetchall()) == EXPECTED_PERMISSIONS

        cur.execute("SELECT COUNT(*) FROM institutions")
        institution_count = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM roles
            WHERE key = 'FINANCE_MANAGER'
            """
        )
        assert int(cur.fetchone()[0]) == institution_count

        cur.execute(
            """
            SELECT COUNT(*)
            FROM membership_roles mr
            JOIN roles r ON r.id = mr.role_id
            WHERE r.key = 'FINANCE_MANAGER'
            """
        )
        assert int(cur.fetchone()[0]) == 0

        cur.execute(
            """
            SELECT COUNT(*)
            FROM institution_capabilities
            WHERE capability_key = 'finance.billing'
            """
        )
        assert int(cur.fetchone()[0]) == institution_count

        cur.execute(
            """
            SELECT COUNT(*)
            FROM institutions i
            JOIN institution_capabilities ic
              ON ic.institution_id = i.id
             AND ic.capability_key = 'finance.billing'
            WHERE ic.enabled <> (
                i.type IN ('PRIVATE','FISCOMISIONAL')
            )
            """
        )
        assert int(cur.fetchone()[0]) == 0

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
            (list(FINANCE_TABLES),),
        )
        rows = cur.fetchall()
        assert len(rows) == len(FINANCE_TABLES)
        for _table, rls, force_rls, owner in rows:
            assert rls is True
            assert force_rls is True
            assert owner != "education_app"

        cur.execute(
            """
            SELECT r.key, COUNT(DISTINCT p.key)
            FROM roles r
            JOIN role_permissions rp ON rp.role_id = r.id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE r.institution_id = %s
              AND r.key IN ('SYSTEM_ADMIN','RECTOR','FINANCE_MANAGER')
              AND p.key LIKE 'finance.%%'
            GROUP BY r.key
            ORDER BY r.key
            """,
            (ctx["institution_id"],),
        )
        grant_counts = {row[0]: int(row[1]) for row in cur.fetchall()}
        assert grant_counts == {
            "FINANCE_MANAGER": 7,
            "RECTOR": 3,
            "SYSTEM_ADMIN": 8,
        }

    print("M14 role / permission / capability-default / RLS catalog: PASSED")


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
    login_email = f"m14-{suffix.lower()}@education-os.internal"

    cur.execute(
        """
        INSERT INTO persons (
            id, organization_id, given_names, family_names,
            primary_email, created_at
        )
        VALUES (%s, %s, 'M14', %s, %s, NOW())
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
            f"M14-{suffix}",
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
            hash_password("M14-Finance-Temporary-2026!"),
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


def bootstrap_actors(ctx: dict) -> dict:
    suffix = uuid4().hex[:8].upper()
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        admin = _create_staff_identity(
            cur,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            suffix=f"ADMIN-{suffix}",
            role_key="SYSTEM_ADMIN",
        )
        finance = _create_staff_identity(
            cur,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            suffix=f"FIN-{suffix}",
            role_key="FINANCE_MANAGER",
        )
        roleless = _create_staff_identity(
            cur,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            suffix=f"NONE-{suffix}",
            role_key=None,
        )
        conn.commit()

    return {
        "admin": admin,
        "finance": finance,
        "roleless": roleless,
        "suffix": suffix,
    }


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def verify_http_accounting(
    base_url: str,
    admin_token: str,
    finance_token: str,
    roleless_token: str,
    ctx: dict,
    actors: dict,
) -> dict:
    status, body = _http(base_url, "/api/v1/finance/dashboard")
    assert status == 200 and "Finance / Billing Core" in str(body)

    status, body = _http(
        base_url,
        "/api/v1/finance/capability",
        roleless_token,
    )
    assert status == 403, f"roleless capability: {status} {body}"

    status, capability = _http(
        base_url,
        "/api/v1/finance/capability",
        finance_token,
    )
    assert status == 200 and isinstance(capability, dict), capability

    status, disabled = _http(
        base_url,
        "/api/v1/finance/capability",
        admin_token,
        method="PUT",
        payload={"enabled": False},
    )
    assert status == 200 and disabled["enabled"] is False, disabled

    status, body = _http(
        base_url,
        "/api/v1/finance/summary",
        finance_token,
    )
    assert status == 403, f"disabled capability should block finance: {status} {body}"
    print("M14 disabled-capability negative gate: PASSED")

    status, enabled = _http(
        base_url,
        "/api/v1/finance/capability",
        admin_token,
        method="PUT",
        payload={"enabled": True},
    )
    assert status == 200 and enabled["enabled"] is True, enabled

    status, summary = _http(
        base_url,
        "/api/v1/finance/summary",
        finance_token,
    )
    assert status == 200, summary

    concept_code = f"M14-{actors['suffix']}"
    status, concept = _http(
        base_url,
        "/api/v1/finance/concepts",
        finance_token,
        method="POST",
        payload={
            "code": concept_code,
            "name": "M14 Verification Tuition",
            "description": "Synthetic billing concept for M14 acceptance.",
            "default_amount": "100.00",
        },
    )
    assert status == 201, concept

    due_on = (date.today() + timedelta(days=30)).isoformat()
    status, charge = _http(
        base_url,
        "/api/v1/finance/charges",
        finance_token,
        method="POST",
        payload={
            "student_profile_id": str(ctx["student_profile_id"]),
            "billing_concept_id": concept["id"],
            "description": "M14 verification charge",
            "amount": "100.00",
            "due_on": due_on,
        },
    )
    assert status == 201, charge
    assert _money(charge["amount"]) == Decimal("100.00")
    assert charge["status"] == "OPEN"

    paid_at = datetime.now(UTC).isoformat()
    status, payment_1 = _http(
        base_url,
        "/api/v1/finance/payments",
        finance_token,
        method="POST",
        payload={
            "student_profile_id": str(ctx["student_profile_id"]),
            "amount": "40.00",
            "payment_method": "BANK_TRANSFER",
            "reference": f"M14-P1-{actors['suffix']}",
            "paid_at": paid_at,
            "allocations": [
                {
                    "billing_charge_id": charge["id"],
                    "amount": "40.00",
                }
            ],
        },
    )
    assert status == 201, payment_1
    assert payment_1["status"] == "POSTED"

    status, statement = _http(
        base_url,
        f"/api/v1/finance/statements/{ctx['student_profile_id']}",
        finance_token,
    )
    assert status == 200, statement
    first_charge = next(
        item for item in statement["charges"] if item["id"] == charge["id"]
    )
    assert first_charge["status"] == "PARTIAL"
    assert _money(first_charge["balance"]) == Decimal("60.00")
    print("M14 charge + partial payment allocation: PASSED")

    status, payment_2 = _http(
        base_url,
        "/api/v1/finance/payments",
        finance_token,
        method="POST",
        payload={
            "student_profile_id": str(ctx["student_profile_id"]),
            "amount": "60.00",
            "payment_method": "CASH",
            "reference": f"M14-P2-{actors['suffix']}",
            "paid_at": datetime.now(UTC).isoformat(),
            "allocations": [
                {
                    "billing_charge_id": charge["id"],
                    "amount": "60.00",
                }
            ],
        },
    )
    assert status == 201, payment_2

    status, statement = _http(
        base_url,
        f"/api/v1/finance/statements/{ctx['student_profile_id']}",
        finance_token,
    )
    assert status == 200, statement
    first_charge = next(
        item for item in statement["charges"] if item["id"] == charge["id"]
    )
    assert first_charge["status"] == "PAID"
    assert _money(first_charge["balance"]) == Decimal("0.00")

    status, voided_payment = _http(
        base_url,
        f"/api/v1/finance/payments/{payment_2['id']}/void",
        finance_token,
        method="POST",
        payload={"reason": "M14 acceptance reversal"},
    )
    assert status == 200, voided_payment
    assert voided_payment["status"] == "VOID"

    status, statement = _http(
        base_url,
        f"/api/v1/finance/statements/{ctx['student_profile_id']}",
        finance_token,
    )
    assert status == 200, statement
    first_charge = next(
        item for item in statement["charges"] if item["id"] == charge["id"]
    )
    assert first_charge["status"] == "PARTIAL"
    assert _money(first_charge["balance"]) == Decimal("60.00")
    print("M14 payment void + charge status recalculation: PASSED")

    status, body = _http(
        base_url,
        f"/api/v1/finance/charges/{charge['id']}/void",
        finance_token,
        method="POST",
        payload={"reason": "Should be blocked due to posted allocation"},
    )
    assert status == 409, f"paid charge void should be blocked: {status} {body}"

    status, charge_2 = _http(
        base_url,
        "/api/v1/finance/charges",
        finance_token,
        method="POST",
        payload={
            "student_profile_id": str(ctx["student_profile_id"]),
            "billing_concept_id": concept["id"],
            "description": "M14 voidable verification charge",
            "amount": "25.00",
            "due_on": due_on,
        },
    )
    assert status == 201, charge_2

    status, voided_charge = _http(
        base_url,
        f"/api/v1/finance/charges/{charge_2['id']}/void",
        finance_token,
        method="POST",
        payload={"reason": "Synthetic M14 void acceptance"},
    )
    assert status == 200, voided_charge
    assert voided_charge["status"] == "VOID"
    print("M14 protected charge/payment reversal lifecycle: PASSED")

    status, statement = _http(
        base_url,
        f"/api/v1/finance/statements/{ctx['student_profile_id']}",
        finance_token,
    )
    assert status == 200, statement
    summary = statement["summary"]
    assert _money(summary["total_billed"]) == Decimal("100.00")
    assert _money(summary["total_paid"]) == Decimal("40.00")
    assert _money(summary["outstanding_balance"]) == Decimal("60.00")
    print("M14 student statement reconciliation: PASSED")

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        expected_events = (
            "FINANCE_CAPABILITY_CHANGED",
            "BILLING_CHARGE_CREATED",
            "BILLING_PAYMENT_POSTED",
            "BILLING_PAYMENT_VOIDED",
            "BILLING_CHARGE_VOIDED",
        )
        for event_type in expected_events:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM outbox_events
                WHERE institution_id = %s
                  AND event_type = %s
                """,
                (ctx["institution_id"], event_type),
            )
            assert int(cur.fetchone()[0]) >= 1, event_type

        expected_audits = (
            "FINANCE_CAPABILITY_CHANGED",
            "BILLING_CONCEPT_CREATED",
            "BILLING_CHARGE_CREATED",
            "BILLING_PAYMENT_POSTED",
            "BILLING_PAYMENT_VOIDED",
            "BILLING_CHARGE_VOIDED",
        )
        for action in expected_audits:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM audit_logs
                WHERE institution_id = %s
                  AND action = %s
                """,
                (ctx["institution_id"], action),
            )
            assert int(cur.fetchone()[0]) >= 1, action

    print("M14 audit + transactional outbox: PASSED")
    return {
        "concept_code": concept_code,
        "charge_id": charge["id"],
        "payment_id": payment_1["id"],
    }


def verify_real_browser(
    base_url: str,
    finance_token: str,
    evidence: dict,
) -> None:
    from playwright.sync_api import sync_playwright

    evidence_dir = Path(
        os.getenv(
            "M14_EVIDENCE_DIR",
            str(Path.home() / "Downloads" / "Education_OS_M14_Evidence"),
        )
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    screenshot = evidence_dir / "m14_finance_billing_edge.png"

    edge = _edge_path()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=edge,
            headless=True,
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.goto(
            f"{base_url}/api/v1/finance/dashboard",
            wait_until="domcontentloaded",
        )
        page.fill("#token", finance_token)
        page.click("button:has-text('Conectar')")
        page.wait_for_function(
            """
            () => document.getElementById('status')?.textContent
                ?.includes('Finance/Billing actualizado.')
            """,
            timeout=15000,
        )
        page.wait_for_function(
            f"""
            () => document.body.innerText.includes(
                {json.dumps(evidence["concept_code"])}
            )
            """,
            timeout=10000,
        )
        page.screenshot(path=str(screenshot), full_page=True)
        browser.close()

    assert screenshot.exists() and screenshot.stat().st_size > 0
    print(f"M14 browser screenshot={screenshot}")
    print("M14 REAL BROWSER ACCEPTANCE: PASSED")


def main() -> None:
    ctx = pick_student_context()
    verify_migration_catalog(ctx)
    actors = bootstrap_actors(ctx)

    admin_token = create_access_token(
        user_id=UUID(str(actors["admin"]["user_id"])),
        organization_id=UUID(str(ctx["organization_id"])),
        institution_id=UUID(str(ctx["institution_id"])),
    )
    finance_token = create_access_token(
        user_id=UUID(str(actors["finance"]["user_id"])),
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
        print(f"M14 actual HTTP server READY at {base_url}")
        evidence = verify_http_accounting(
            base_url,
            admin_token,
            finance_token,
            roleless_token,
            ctx,
            actors,
        )
        verify_real_browser(
            base_url,
            finance_token,
            evidence,
        )
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    print(
        "M14 Finance / Billing Core verifier: PASSED | "
        f"finance={actors['finance']['login_email']}"
    )


if __name__ == "__main__":
    main()
