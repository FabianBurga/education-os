from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session, create_engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.security import create_access_token  # noqa: E402
from app.db.tenant_context import TenantContext, apply_tenant_context  # noqa: E402

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://education_app:education_app_dev@localhost:5432/education_os",
)
OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)
RUNTIME_URL = os.getenv(
    "DATABASE_URL_PG",
    "postgresql://education_app:education_app_dev@localhost:5432/education_os",
)


def find_staff_context():
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT ua.id, i.organization_id, sp.institution_id
            FROM staff_profiles sp
            JOIN persons p ON p.id = sp.person_id
            JOIN user_accounts ua ON ua.person_id = p.id
            JOIN institutions i ON i.id = sp.institution_id
            WHERE sp.status='ACTIVE' AND ua.is_active=true
            ORDER BY sp.created_at
            LIMIT 1
            """
        )
        row = cur.fetchone()
    assert row is not None, "active staff user not found"
    return row


def main() -> None:
    with psycopg.connect(RUNTIME_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        assert cur.fetchone() == ("0009_rc5",)
    print("Runtime Alembic revision access: PASSED")

    user_id, org_id, inst_id = find_staff_context()
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    with Session(engine) as session:
        apply_tenant_context(
            session,
            TenantContext(
                organization_id=org_id,
                institution_id=inst_id,
                user_id=user_id,
            ),
        )
        before = session.exec(
            text(
                """
                SELECT current_setting('app.organization_id', true),
                       current_setting('app.institution_id', true),
                       current_setting('app.user_id', true)
                """
            )
        ).first()
        session.commit()
        after = session.exec(
            text(
                """
                SELECT current_setting('app.organization_id', true),
                       current_setting('app.institution_id', true),
                       current_setting('app.user_id', true)
                """
            )
        ).first()
    assert before == after
    print("Transaction-local RLS auto-restore after COMMIT: PASSED")

    token = create_access_token(
        user_id=user_id,
        organization_id=org_id,
        institution_id=inst_id,
    )
    from app.main import app

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    paths = (
        "/api/v1/me",
        "/api/v1/campuses",
        "/api/v1/operations/security-baseline",
        "/api/v1/operations/pilot/data-summary",
        "/api/v1/intelligence/rector/overview",
        "/api/v1/intelligence/rector/dashboard",
    )
    for path in paths:
        response = client.get(path, headers=headers)
        assert response.status_code == 200, (
            f"{path}: {response.status_code} {response.text[:500]}"
        )
    print(f"Staff HTTP boundary smoke: PASSED ({len(paths)}/{len(paths)})")
    print("RC5 systemic hardening verifier: PASSED")


if __name__ == "__main__":
    main()
