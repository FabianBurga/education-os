from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.core.config import settings
from app.db.session import engine
from app.db.tenant_context import TenantContext, apply_tenant_context
from app.modules.accountability.models import AccountabilityCase
from app.modules.accountability.queue_service import (
    get_accountability_case_detail,
    list_accountability_queue,
)


def _owner_engine():
    if not settings.OWNER_DATABASE_URL:
        pytest.skip("OWNER_DATABASE_URL is required for queue integration")
    return create_engine(settings.OWNER_DATABASE_URL, pool_pre_ping=True)


def _queue_principal(owner_engine):
    with owner_engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT DISTINCT m.user_id, i.organization_id, m.institution_id
                FROM memberships m
                JOIN institutions i ON i.id = m.institution_id
                JOIN membership_roles mr ON mr.membership_id = m.id
                JOIN role_permissions rp ON rp.role_id = mr.role_id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE m.status = 'ACTIVE' AND p.key = 'accountability.view'
                ORDER BY m.user_id
                LIMIT 1
                """
            )
        ).first()
    if row is None:
        pytest.skip("No accountability queue principal")
    return CurrentPrincipal(UUID(str(row[0])), UUID(str(row[1])), UUID(str(row[2])))


def test_queue_is_deterministic_read_only_and_preserves_lineage():
    owner_engine = _owner_engine()
    principal = _queue_principal(owner_engine)
    with Session(engine) as session:
        apply_tenant_context(session, TenantContext(principal.organization_id, principal.institution_id, principal.user_id))
        case = AccountabilityCase(
            organization_id=principal.organization_id,
            institution_id=principal.institution_id,
            subject_type="STUDENT",
            subject_id=uuid4(),
            source_category="TEST_QUEUE",
            normalized_category="SOURCE:TEST_QUEUE",
            identity_key_sha256=uuid4().hex + uuid4().hex,
            episode_anchor="queue-test",
            owner_state="UNASSIGNED",
        )
        session.add(case)
        session.flush()
        before = session.exec(
            text("SELECT count(*) FROM outbox_events WHERE institution_id=CAST(:institution_id AS uuid)"),
            params={"institution_id": str(principal.institution_id)},
        ).one()[0]
        page = list_accountability_queue(session, principal, limit=1)
        assert page.items
        item = next(item for item in page.items if item.case_id == case.id)
        assert "UNASSIGNED" in item.attention_reasons
        assert item.next_required_step == "ASSIGN_OWNER"
        assert item.identity_key_sha256 == case.identity_key_sha256
        assert page.next_cursor is None or isinstance(page.next_cursor, str)
        detail = get_accountability_case_detail(session, principal, case.id)
        assert detail.item.case_id == case.id
        after = session.exec(
            text("SELECT count(*) FROM outbox_events WHERE institution_id=CAST(:institution_id AS uuid)"),
            params={"institution_id": str(principal.institution_id)},
        ).one()[0]
        assert before == after
