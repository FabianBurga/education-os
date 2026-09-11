import os
from uuid import uuid4

from sqlalchemy import text
from sqlmodel import Session, create_engine

from app.db.tenant_context import TenantContext, apply_tenant_context

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://education_app:education_app_dev@localhost:5432/education_os",
)


def test_transaction_local_tenant_context_reapplies_after_commit() -> None:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    ctx = TenantContext(
        organization_id=uuid4(),
        institution_id=uuid4(),
        user_id=uuid4(),
    )
    with Session(engine) as session:
        apply_tenant_context(session, ctx)
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
    assert after == (
        str(ctx.organization_id),
        str(ctx.institution_id),
        str(ctx.user_id),
    )
