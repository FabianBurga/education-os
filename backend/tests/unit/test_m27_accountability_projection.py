from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, select

from app.modules.accountability.models import AccountabilityCase, AccountabilityCaseSource
from app.modules.accountability.projection import CaseProjectionInput, CaseSourceInput, project_case


def test_projection_creates_one_case_and_one_source_on_replay():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine, tables=[AccountabilityCase.__table__, AccountabilityCaseSource.__table__])
    organization_id, institution_id, subject_id = uuid4(), uuid4(), uuid4()
    source = CaseSourceInput(
        source_kind="M22",
        source_entity_id=uuid4(),
        source_category="ATTENDANCE_RISK",
        source_provenance_sha256="a" * 64,
        observed_at=datetime.now(UTC),
    )
    value = CaseProjectionInput(
        organization_id=organization_id,
        institution_id=institution_id,
        subject_type="STUDENT",
        subject_id=subject_id,
        source_category="ATTENDANCE_RISK",
        episode_anchor="2026-S1",
        source=source,
    )
    with Session(engine) as session:
        first, first_decision, first_inserted = project_case(session, value)
        session.commit()
        second, second_decision, second_inserted = project_case(session, value)
        session.commit()
        assert first.id == second.id
        assert first_decision.identity_key_sha256 == second_decision.identity_key_sha256
        assert first_inserted is True
        assert second_inserted is False
        assert len(session.exec(select(AccountabilityCase)).all()) == 1
        assert len(session.exec(select(AccountabilityCaseSource)).all()) == 1
