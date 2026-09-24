import json
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.core.config import settings
from app.db.session import engine
from app.db.tenant_context import TenantContext, apply_tenant_context
from app.modules.accountability.ledger_service import record_case_decision, record_case_review
from app.modules.accountability.models import AccountabilityCase, AccountabilityObligation
from app.modules.accountability.obligation_service import (
    complete_accountability_obligation,
    create_accountability_obligation,
    evaluate_obligation_compliance,
    is_obligation_overdue,
    materialize_obligation_from_decision,
    transfer_obligation_owner,
    waive_accountability_obligation,
)


def _owner_engine():
    if not settings.OWNER_DATABASE_URL:
        pytest.skip("OWNER_DATABASE_URL is required for policy fixture")
    return create_engine(settings.OWNER_DATABASE_URL, pool_pre_ping=True)


def test_m27_information_obligation_lifecycle_sla_security_and_no_m21_mutation():
    owner_engine = _owner_engine()
    with Session(engine) as session:
        with owner_engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT DISTINCT m.user_id, i.organization_id, m.institution_id
                    FROM memberships m
                    JOIN institutions i ON i.id = m.institution_id
                    JOIN membership_roles mr ON mr.membership_id = m.id
                    JOIN role_permissions rp ON rp.role_id = mr.role_id
                    JOIN permissions p ON p.id = rp.permission_id
                    WHERE m.status = 'ACTIVE' AND p.key = 'accountability.decide'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM role_permissions rp_view
                          JOIN permissions p_view ON p_view.id = rp_view.permission_id
                          WHERE rp_view.role_id = mr.role_id
                            AND p_view.key = 'control_plane.view'
                      )
                    ORDER BY m.user_id
                    LIMIT 1
                    """
                )
            ).first()
        if rows is None:
            pytest.skip("No M27 decision-capable principal")
        principal = CurrentPrincipal(UUID(str(rows[0])), UUID(str(rows[1])), UUID(str(rows[2])))
        apply_tenant_context(session, TenantContext(principal.organization_id, principal.institution_id, principal.user_id))
        policy_before = None
        with owner_engine.begin() as connection:
            policy_before = connection.execute(
                text("SELECT enabled, policy_json, policy_version, updated_by_user_id FROM institution_policy_controls WHERE organization_id=:org AND institution_id=:inst AND policy_key='accountability.sla'"),
                {"org": str(principal.organization_id), "inst": str(principal.institution_id)},
            ).first()
            connection.execute(
                text(
                    """
                    INSERT INTO institution_policy_controls (id, organization_id, institution_id, policy_key, enabled, policy_json, policy_version, created_at, updated_at)
                    VALUES (:id, :org, :inst, 'accountability.sla', true, CAST(:policy AS jsonb), 1, now(), now())
                    ON CONFLICT (institution_id, policy_key) DO UPDATE SET enabled=true, policy_json=EXCLUDED.policy_json, policy_version=institution_policy_controls.policy_version + 1, updated_at=now()
                    """
                ),
                {"id": str(uuid4()), "org": str(principal.organization_id), "inst": str(principal.institution_id), "policy": '{"rules":[{"obligation_type":"INFORMATION_REQUIRED","duration_seconds":60,"rule_code":"information-60s"}]}'},
            )
        try:
            case = AccountabilityCase(
                organization_id=principal.organization_id,
                institution_id=principal.institution_id,
                subject_type="STUDENT",
                subject_id=uuid4(),
                source_category="TEST_OBLIGATION",
                normalized_category="SOURCE:TEST_OBLIGATION",
                identity_key_sha256="d" * 64,
                episode_anchor="m27-4-test",
                primary_owner_user_id=principal.user_id,
                owner_state="ASSIGNED",
            )
            session.add(case)
            session.flush()
            evidence = "e" * 64
            provenance = "f" * 64
            review = record_case_review(
                session, principal, case.id, disposition="NEEDS_INFORMATION", evidence_refs=["source:evidence"],
                evidence_fingerprint_sha256=evidence, next_required_step="REQUEST_INFORMATION",
                idempotency_key="1" * 64, provenance_sha256=provenance,
            )
            before = session.exec(text("SELECT count(*) FROM interventions WHERE institution_id=CAST(:inst AS uuid)"), params={"inst": str(principal.institution_id)}).one()[0]
            decision = record_case_decision(
                session, principal, case.id, review_id=review.record.id, decision_type="REQUEST_INFORMATION",
                evidence_refs=["source:evidence"], evidence_fingerprint_sha256=evidence,
                idempotency_key="2" * 64, provenance_sha256=provenance,
            )
            obligation = session.exec(select(AccountabilityObligation).where(AccountabilityObligation.case_id == case.id)).one()
            assert decision.created and obligation.origin_id == decision.record.id
            assert obligation.obligation_type == "INFORMATION_REQUIRED"
            assert obligation.owner_user_id == principal.user_id
            assert obligation.due_at is not None and obligation.sla_status == "RESOLVED"
            assert obligation.next_required_step == "HUMAN_REVIEW_REQUIRED"
            assert session.exec(text("SELECT count(*) FROM accountability_obligations WHERE case_id=CAST(:case_id AS uuid)"), params={"case_id": str(case.id)}).one()[0] == 1
            duplicate = materialize_obligation_from_decision(session, principal, decision.record.id, provenance_sha256=provenance)
            assert duplicate.created is False
            assert session.exec(text("SELECT count(*) FROM interventions WHERE institution_id=CAST(:inst AS uuid)"), params={"inst": str(principal.institution_id)}).one()[0] == before
            assert evaluate_obligation_compliance(obligation, now=obligation.due_at - timedelta(seconds=1)).status == "PENDING"
            assert evaluate_obligation_compliance(obligation, now=obligation.due_at).status == "PENDING"
            assert evaluate_obligation_compliance(obligation, now=obligation.due_at + timedelta(seconds=1)).status == "NON_COMPLIANT"
            assert is_obligation_overdue(obligation, now=obligation.due_at + timedelta(seconds=1))
            transferred_away = transfer_obligation_owner(
                session, principal, obligation.id, None, idempotency_key="3" * 64, provenance_sha256=provenance,
            )
            transferred_back = transfer_obligation_owner(
                session, principal, obligation.id, principal.user_id, idempotency_key="4" * 64, provenance_sha256=provenance,
            )
            assert transferred_away.created and transferred_back.created and obligation.owner_user_id == principal.user_id
            completed = complete_accountability_obligation(
                session, principal, obligation.id, evidence_type="M27_HUMAN_REVIEW", evidence_id=review.record.id,
                evidence_fingerprint_sha256=evidence, idempotency_key="5" * 64, provenance_sha256=provenance,
                completed_at=obligation.due_at,
            )
            assert completed.created and evaluate_obligation_compliance(obligation, now=obligation.due_at).status == "COMPLIANT"
            duplicate_completion = complete_accountability_obligation(
                session, principal, obligation.id, evidence_type="M27_HUMAN_REVIEW", evidence_id=review.record.id,
                evidence_fingerprint_sha256=evidence, idempotency_key="5" * 64, provenance_sha256=provenance,
            )
            assert duplicate_completion.created is False
            with pytest.raises(HTTPException) as completed_waiver:
                waive_accountability_obligation(session, principal, obligation.id, reason_code="not-needed", evidence_id=review.record.id, idempotency_key="6" * 64, provenance_sha256=provenance)
            assert completed_waiver.value.status_code == 409
            waiver_target = create_accountability_obligation(
                session, principal, case.id, origin_type="REVIEW", origin_id=review.record.id,
                obligation_type="REVIEW_REQUIRED", creation_idempotency_key="7" * 64, provenance_sha256=provenance,
            )
            waived = waive_accountability_obligation(
                session, principal, waiver_target.obligation.id, reason_code="not-needed",
                evidence_id=review.record.id, idempotency_key="8" * 64, provenance_sha256=provenance,
            )
            assert waived.created and evaluate_obligation_compliance(waiver_target.obligation).status == "EXEMPT"
            duplicate_waiver = waive_accountability_obligation(
                session, principal, waiver_target.obligation.id, reason_code="not-needed",
                evidence_id=review.record.id, idempotency_key="8" * 64, provenance_sha256=provenance,
            )
            assert duplicate_waiver.created is False
            with pytest.raises(HTTPException) as waived_completion:
                complete_accountability_obligation(
                    session, principal, waiver_target.obligation.id, evidence_type="M27_HUMAN_REVIEW",
                    evidence_id=review.record.id, evidence_fingerprint_sha256=evidence,
                    idempotency_key="9" * 64, provenance_sha256=provenance,
                )
            assert waived_completion.value.status_code == 409
            session.rollback()
        finally:
            with owner_engine.begin() as connection:
                if policy_before is None:
                    connection.execute(text("DELETE FROM institution_policy_controls WHERE organization_id=:org AND institution_id=:inst AND policy_key='accountability.sla'"), {"org": str(principal.organization_id), "inst": str(principal.institution_id)})
                else:
                    connection.execute(
                        text("UPDATE institution_policy_controls SET enabled=:enabled, policy_json=CAST(:policy AS jsonb), policy_version=:version, updated_by_user_id=:user, updated_at=now() WHERE organization_id=:org AND institution_id=:inst AND policy_key='accountability.sla'"),
                        {"enabled": policy_before[0], "policy": json.dumps(policy_before[1]), "version": policy_before[2], "user": policy_before[3], "org": str(principal.organization_id), "inst": str(principal.institution_id)},
                    )
            owner_engine.dispose()
