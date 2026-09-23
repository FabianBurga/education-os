from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.db.session import engine
from app.db.tenant_context import TenantContext, apply_tenant_context
from app.modules.accountability.ledger_service import (
    assign_case_owner,
    record_case_decision,
    record_case_review,
    transfer_case_owner,
    unassign_case_owner,
)
from app.modules.accountability.models import (
    AccountabilityCase,
)


def test_m27_review_decision_ownership_are_human_append_only_and_non_mutating():
    with Session(engine) as session:
        rows = session.exec(
            text(
                """
                SELECT DISTINCT m.user_id, i.organization_id, m.institution_id
                FROM memberships m
                JOIN institutions i ON i.id = m.institution_id
                JOIN membership_roles mr ON mr.membership_id = m.id
                JOIN role_permissions rp ON rp.role_id = mr.role_id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE m.status = 'ACTIVE' AND p.key = 'accountability.ownership.manage'
                ORDER BY m.user_id
                LIMIT 2
                """
            )
        ).all()
        if len(rows) < 2:
            return
        principal = CurrentPrincipal(UUID(str(rows[0][0])), UUID(str(rows[0][1])), UUID(str(rows[0][2])))
        second_owner = UUID(str(rows[1][0]))
        apply_tenant_context(session, TenantContext(principal.organization_id, principal.institution_id, principal.user_id))

        case = AccountabilityCase(
            organization_id=principal.organization_id,
            institution_id=principal.institution_id,
            subject_type="STUDENT",
            subject_id=uuid4(),
            source_category="TEST_REVIEW",
            normalized_category="SOURCE:TEST_REVIEW",
            identity_key_sha256="c" * 64,
            episode_anchor="m27-3-test",
        )
        session.add(case)
        session.flush()
        case_id = case.id
        provenance = "a" * 64
        evidence = "b" * 64

        assigned = assign_case_owner(session, principal, case_id, principal.user_id, idempotency_key="1" * 64, provenance_sha256=provenance)
        transferred = transfer_case_owner(session, principal, case_id, second_owner, idempotency_key="2" * 64, provenance_sha256=provenance)
        unassigned = unassign_case_owner(session, principal, case_id, idempotency_key="3" * 64, provenance_sha256=provenance)
        assert assigned.created and transferred.created and unassigned.created
        assert case.primary_owner_user_id is None
        assert case.owner_state == "UNASSIGNED"

        review = record_case_review(
            session, principal, case_id, disposition="READY_FOR_DECISION", evidence_refs=["ev_01"],
            evidence_fingerprint_sha256=evidence, next_required_step="Record human decision",
            idempotency_key="4" * 64, provenance_sha256=provenance,
        )
        intervention_count_before = session.exec(
            text("SELECT count(*) FROM interventions WHERE institution_id = CAST(:institution_id AS uuid)"),
            params={"institution_id": str(principal.institution_id)},
        ).one()[0]
        decision = record_case_decision(
            session, principal, case_id, review_id=review.record.id, decision_type="CREATE_INTERVENTION",
            evidence_refs=["ev_01"], evidence_fingerprint_sha256=evidence,
            idempotency_key="5" * 64, provenance_sha256=provenance,
        )
        assert review.created and decision.created
        assert decision.record.execution_required is True
        assert decision.record.decision_actor_user_id == principal.user_id
        assert review.record.reviewer_user_id == principal.user_id

        duplicate_review = record_case_review(
            session, principal, case_id, disposition="READY_FOR_DECISION", evidence_refs=["ev_01"],
            evidence_fingerprint_sha256=evidence, next_required_step="Record human decision",
            idempotency_key="4" * 64, provenance_sha256=provenance,
        )
        duplicate_decision = record_case_decision(
            session, principal, case_id, review_id=review.record.id, decision_type="CREATE_INTERVENTION",
            evidence_refs=["ev_01"], evidence_fingerprint_sha256=evidence,
            idempotency_key="5" * 64, provenance_sha256=provenance,
        )
        assert duplicate_review.created is False
        assert duplicate_decision.created is False
        assert len(session.exec(text("SELECT 1 FROM accountability_reviews WHERE case_id = CAST(:case_id AS uuid)"), params={"case_id": str(case_id)}).all()) == 1
        assert len(session.exec(text("SELECT 1 FROM accountability_decisions WHERE case_id = CAST(:case_id AS uuid)"), params={"case_id": str(case_id)}).all()) == 1
        assert session.exec(text("SELECT count(*) FROM accountability_ownership_events WHERE case_id = CAST(:case_id AS uuid)"), params={"case_id": str(case_id)}).one()[0] == 3
        event_types = {row[0] for row in session.exec(text("SELECT event_type FROM outbox_events WHERE aggregate_id = CAST(:case_id AS uuid)"), params={"case_id": str(case_id)}).all()}
        assert {"accountability.owner.assigned", "accountability.owner.transferred", "accountability.owner.unassigned", "accountability.review.completed", "accountability.decision.recorded"} <= event_types
        intervention_count_after = session.exec(
            text("SELECT count(*) FROM interventions WHERE institution_id = CAST(:institution_id AS uuid)"),
            params={"institution_id": str(principal.institution_id)},
        ).one()[0]
        assert intervention_count_after == intervention_count_before
        assert session.exec(text("SELECT count(*) FROM accountability_reviews WHERE case_id = CAST(:case_id AS uuid)"), params={"case_id": str(case_id)}).one()[0] == 1
        assert session.exec(text("SELECT count(*) FROM accountability_decisions WHERE case_id = CAST(:case_id AS uuid)"), params={"case_id": str(case_id)}).one()[0] == 1
        teacher_row = session.exec(
            text(
                """
                SELECT DISTINCT m.user_id
                FROM memberships m
                JOIN membership_roles mr ON mr.membership_id = m.id
                JOIN roles r ON r.id = mr.role_id
                WHERE m.institution_id = CAST(:institution_id AS uuid)
                  AND m.status = 'ACTIVE' AND r.key = 'TEACHER'
                LIMIT 1
                """
            ),
            params={"institution_id": str(principal.institution_id)},
        ).first()
        if teacher_row is not None:
            teacher = CurrentPrincipal(UUID(str(teacher_row[0])), principal.organization_id, principal.institution_id)
            apply_tenant_context(session, TenantContext(teacher.organization_id, teacher.institution_id, teacher.user_id))
            with pytest.raises(HTTPException) as denied:
                record_case_review(
                    session, teacher, case_id, disposition="READY_FOR_DECISION", evidence_refs=["ev_01"],
                    evidence_fingerprint_sha256=evidence, next_required_step="Record human decision",
                    idempotency_key="6" * 64, provenance_sha256=provenance,
                )
            assert denied.value.status_code == 403
        session.rollback()
