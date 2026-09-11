import os
from uuid import uuid4

import psycopg
from sqlalchemy import create_engine, text
from sqlmodel import Session

from app.modules.intelligence.service import rector_overview

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)
APP_SA_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://education_app:education_app_dev@localhost:5432/education_os",
)


def _apply_rls_context(session: Session, organization_id, institution_id) -> None:
    session.exec(
        text("SELECT set_config('app.organization_id', :organization_id, true)").bindparams(
            organization_id=str(organization_id)
        )
    )
    session.exec(
        text("SELECT set_config('app.institution_id', :institution_id, true)").bindparams(
            institution_id=str(institution_id)
        )
    )


def test_rector_overview_empty_tenant_returns_zero_safe_contract() -> None:
    org_id, inst_id = uuid4(), uuid4()

    try:
        with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO organizations(id,name,status,created_at) VALUES(%s,%s,'ACTIVE',now())",
                (org_id, "M4 Empty Org"),
            )
            cur.execute(
                """
                INSERT INTO institutions(id,organization_id,name,type,status,created_at)
                VALUES(%s,%s,%s,'PRIVATE','ACTIVE',now())
                """,
                (inst_id, org_id, "M4 Empty Institution"),
            )

        engine = create_engine(APP_SA_URL)
        with Session(engine) as session:
            _apply_rls_context(session, org_id, inst_id)
            overview = rector_overview(session)

        assert overview.active_students == 0
        assert overview.active_sections == 0
        assert overview.attendance_rate is None
        assert overview.absence_rate is None
        assert overview.late_rate is None
        assert overview.academic_average_percent is None
        assert overview.missing_grade_entries == 0
        assert overview.open_signals == 0
    finally:
        with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM institutions WHERE id = %s", (inst_id,))
            cur.execute("DELETE FROM organizations WHERE id = %s", (org_id,))
