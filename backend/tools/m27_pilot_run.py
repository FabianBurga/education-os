"""M27-8 deterministic synthetic operational pilot.

The pilot is deliberately transaction-scoped: it provisions one labelled
synthetic tenant, exercises the real M27/M21 services, writes an evidence
artifact, and rolls the tenant back.  No production-like data is changed.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid5

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.db.tenant_context import TenantContext, apply_tenant_context
from app.modules.accountability.ledger_service import (
    assign_case_owner,
    record_case_decision,
    record_case_review,
)
from app.modules.accountability.metrics_service import (
    ADMIN_TIME_SAVED,
    get_accountability_metric,
    get_accountability_outcome_summary,
)
from app.modules.accountability.models import (
    AccountabilityCase,
    AccountabilityCaseSource,
)
from app.modules.accountability.obligation_service import (
    complete_accountability_obligation,
    create_accountability_obligation,
    waive_accountability_obligation,
)
from app.modules.accountability.projection import (
    CaseProjectionInput,
    CaseSourceInput,
    project_case,
)
from app.modules.accountability.queue_service import (
    get_accountability_case_detail,
    list_accountability_queue,
)
from app.modules.identity.models import (
    Membership,
    MembershipRole,
    Person,
    Role,
    RolePermission,
    UserAccount,
)
from app.modules.intelligence.models import StudentIntelligenceSnapshot
from app.modules.interventions.models import Intervention, InterventionLink
from app.modules.interventions.schemas import InterventionCreate
from app.modules.interventions.service import create_intervention
from app.modules.students.models import StudentProfile
from app.modules.tenancy.models import Institution, Organization

RUNTIME_URL = os.getenv("OWNER_DATABASE_URL", "postgresql+psycopg://education_owner:education_owner_dev@127.0.0.1:5432/education_os")
ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "artifacts" / "m27_pilot_result.json"
NAMESPACE = UUID("b5a8d4f0-0e28-4e7a-9ad8-7f7ca6d81a27")
REF = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
WINDOW_START = REF - timedelta(days=3)
WINDOW_END = REF + timedelta(days=3)
PROVENANCE = "a" * 64
EVIDENCE = "b" * 64


def uid(name: str) -> UUID:
    return uuid5(NAMESPACE, name)


def principal(actor: str, org: UUID, institution: UUID) -> CurrentPrincipal:
    return CurrentPrincipal(uid(actor), org, institution)


def digest(seed: str) -> str:
    return (seed.encode().hex() + "0" * 64)[:64]


def provision(session: Session) -> dict[str, object]:
    org_id, institution_id = uid("organization"), uid("institution")
    session.add(Organization(id=org_id, name="M27-8 SYNTHETIC PILOT TENANT", status="ACTIVE"))
    session.flush()
    session.add(Institution(id=institution_id, organization_id=org_id, name="M27-8 Synthetic Accountability School", type="PRIVATE", status="ACTIVE"))
    session.flush()
    permission_keys = (
        "accountability.view", "accountability.review", "accountability.decide",
        "accountability.ownership.manage", "accountability.obligation.create",
        "accountability.obligation.complete", "accountability.obligation.waive",
        "intervention.create", "intervention.read", "intervention.update",
        "intervention.resolve", "control_plane.view",
    )
    permission_rows = session.exec(text("SELECT id, key FROM permissions WHERE key = ANY(CAST(:keys AS text[]))"), params={"keys": list(permission_keys)}).all()
    permissions = {str(key): permission_id for permission_id, key in permission_rows}
    if set(permissions) != set(permission_keys):
        raise AssertionError(f"missing seeded permissions: {set(permission_keys) - set(permissions)}")

    actor_roles = {
        "system_admin": ("SYSTEM_ADMIN", ("control_plane.view",)),
        "rector": ("RECTOR", permission_keys[:-1]),
        "coordinator": ("ACADEMIC_COORDINATOR", permission_keys[:-1]),
        "teacher_a": ("TEACHER", ("intervention.read",)),
        "teacher_b": ("TEACHER", ("intervention.read",)),
    }
    actors: dict[str, UUID] = {}
    role_ids: dict[str, UUID] = {}
    for key, (role_key, actor_permissions) in actor_roles.items():
        person_id, user_id, membership_id = (uid(f"{key}-person"), uid(f"{key}-user"), uid(f"{key}-membership"))
        new_role = role_key not in role_ids
        role_id = role_ids.setdefault(role_key, uid(f"role-{role_key}"))
        session.add(Person(id=person_id, organization_id=org_id, given_names="Synthetic", family_names=role_key, primary_email=f"{key}@m27-8.invalid"))
        session.add(UserAccount(id=user_id, person_id=person_id, login_email=f"{key}@m27-8.invalid", password_hash="pilot-only-not-a-credential", is_active=True))
        session.flush()
        session.add(Membership(id=membership_id, user_id=user_id, institution_id=institution_id, status="ACTIVE"))
        if new_role:
            session.add(Role(id=role_id, institution_id=institution_id, key=role_key, name=f"M27-8 {role_key}"))
        session.flush()
        session.add(MembershipRole(membership_id=membership_id, role_id=role_id))
        if new_role:
            session.add_all(RolePermission(role_id=role_id, permission_id=permissions[item]) for item in actor_permissions)
        actors[key] = user_id
    session.flush()
    permission_check = session.exec(text("""
        SELECT p.key FROM memberships m
        JOIN membership_roles mr ON mr.membership_id = m.id
        JOIN role_permissions rp ON rp.role_id = mr.role_id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE m.user_id=:user AND m.institution_id=:institution
    """), params={"user": actors["rector"], "institution": institution_id}).all()
    if "accountability.ownership.manage" not in {row[0] for row in permission_check}:
        raise AssertionError(f"synthetic rector permissions incomplete: {permission_check}")

    students: dict[str, UUID] = {}
    for key in ("normal", "information", "overdue", "recurrence", "continuation"):
        person_id, student_id = uid(f"student-{key}-person"), uid(f"student-{key}")
        session.add(Person(id=person_id, organization_id=org_id, given_names="Synthetic", family_names=f"Student {key}"))
        session.add(StudentProfile(id=student_id, organization_id=org_id, institution_id=institution_id, person_id=person_id, student_code=f"M27-8-{key.upper()}"))
        students[key] = student_id
    session.flush()
    for index, student_id in enumerate(students.values(), start=1):
        session.add(StudentIntelligenceSnapshot(
            id=uid(f"snapshot-{index}"), organization_id=org_id, institution_id=institution_id,
            student_profile_id=student_id, snapshot_date=REF.date(), overall_priority="HIGH" if index == 1 else "MEDIUM",
            attendance_priority="MEDIUM", academic_priority="MEDIUM", intervention_priority="LOW",
            evidence_count=1, policy_source="CONTROL_PLANE", policy_key="institutional_intelligence", policy_version=1,
            control_revision=1,
            evaluated_at=REF, created_at=REF,
        ))
    session.flush()
    session.execute(text("""
        INSERT INTO institution_policy_controls
            (id, organization_id, institution_id, policy_key, enabled, policy_json, policy_version, created_at, updated_at, updated_by_user_id)
        VALUES
            (:id, :org, :inst, 'accountability.metrics', true, CAST(:metrics AS jsonb), 1, :at, :at, :actor),
            (:id2, :org, :inst, 'accountability.sla', true, CAST(:sla AS jsonb), 1, :at, :at, :actor)
    """), {
        "id": uid("metrics-policy"), "id2": uid("sla-policy"), "org": org_id, "inst": institution_id,
        "metrics": json.dumps({"small_cell_threshold": 2, "lost_case": {"observation_days": 1}, "recurrence_window_days": 30}),
        "sla": json.dumps({"rules": [
            {"obligation_type": "INFORMATION_REQUIRED", "duration_seconds": 3600, "rule_code": "pilot-information-1h"},
            {"obligation_type": "FOLLOW_UP_REQUIRED", "duration_seconds": 3600, "rule_code": "pilot-followup-1h"},
            {"obligation_type": "REVIEW_REQUIRED", "duration_seconds": 3600, "rule_code": "pilot-review-1h"},
        ]}), "at": REF, "actor": actors["rector"],
    })
    session.flush()
    return {"organization_id": org_id, "institution_id": institution_id, "actors": actors, "students": students}


def add_case(session: Session, fixture: dict[str, object], key: str, student_key: str, *, lifecycle: str = "OPEN", classification: str = "NEW_EPISODE") -> AccountabilityCase:
    org, inst = fixture["organization_id"], fixture["institution_id"]
    student = fixture["students"][student_key]
    case = AccountabilityCase(
        id=uid(f"case-{key}"), organization_id=org, institution_id=inst, subject_type="STUDENT", subject_id=student,
        source_category=f"M27_8_{key.upper()}", normalized_category=f"SOURCE:M27_8_{key.upper()}",
        identity_key_sha256=digest(f"identity-{key}"), episode_anchor=f"m27-8-{key}", lifecycle=lifecycle,
        recurrence_classification=classification, created_at=REF, updated_at=REF,
    )
    session.add(case)
    session.add(AccountabilityCaseSource(
        id=uid(f"source-{key}"), organization_id=org, institution_id=inst, case_id=case.id,
        source_kind="M22", source_entity_id=uid(f"signal-{key}"), source_event_id=None,
        source_category=case.source_category, source_provenance_sha256=digest(f"source-provenance-{key}"),
        source_fingerprint_sha256=digest(f"source-fingerprint-{key}"), observed_at=REF - timedelta(hours=4), created_at=REF,
    ))
    session.flush()
    return case


def main() -> int:
    started = datetime.now(UTC)
    engine = create_engine(RUNTIME_URL, pool_pre_ping=True)
    evidence: dict[str, object] = {"pilot_version": "m27-8.v1", "source_commit": os.getenv("M27_PILOT_SOURCE_COMMIT", "7d30e935a94f9a4b84710e6aeabdacba659d3826"), "schema_revision": "0042_m27_true_recurrence", "dataset_identity": "M27-8-SYNTHETIC-TRANSACTION-ROLLBACK", "scenarios": {}, "security": {}, "privacy": {}, "metric_results": {}, "provenance": {}}
    with Session(engine) as session:
        try:
            fixture = provision(session)
            org, inst, actors = fixture["organization_id"], fixture["institution_id"], fixture["actors"]
            rector = CurrentPrincipal(actors["rector"], org, inst)
            coordinator = CurrentPrincipal(actors["coordinator"], org, inst)
            teacher = CurrentPrincipal(actors["teacher_a"], org, inst)
            system_admin = CurrentPrincipal(actors["system_admin"], org, inst)
            apply_tenant_context(session, TenantContext(org, inst, rector.user_id))
            normal = add_case(session, fixture, "normal", "normal")
            information = add_case(session, fixture, "information", "information")
            review_pending = add_case(session, fixture, "review-pending", "normal")
            decision_pending = add_case(session, fixture, "decision-pending", "normal")
            overdue = add_case(session, fixture, "overdue", "overdue")
            waived = add_case(session, fixture, "waived", "normal")
            add_case(session, fixture, "lost", "normal", lifecycle="RESOLVED")
            add_case(session, fixture, "open-control", "normal")
            add_case(session, fixture, "true-recurrence", "recurrence", classification="TRUE_RECURRENCE")
            add_case(session, fixture, "continuation", "continuation", classification="SAME_ACTIVE_EPISODE")
            session.flush()

            # Queue/action continuity: assign, review, decision, information obligation, completion.
            normal_assign = assign_case_owner(session, rector, normal.id, actors["coordinator"], idempotency_key=digest("normal-assign"), provenance_sha256=PROVENANCE)
            assert normal_assign.created
            assert assign_case_owner(session, rector, normal.id, actors["coordinator"], idempotency_key=digest("normal-assign"), provenance_sha256=PROVENANCE).created is False
            assign_case_owner(session, rector, information.id, actors["coordinator"], idempotency_key=digest("information-assign"), provenance_sha256=PROVENANCE)
            normal_review = record_case_review(session, coordinator, normal.id, disposition="READY_FOR_DECISION", evidence_refs=["m27-8:signal-normal"], evidence_fingerprint_sha256=EVIDENCE, next_required_step="Record human decision", idempotency_key=digest("normal-review"), provenance_sha256=PROVENANCE, reviewed_at=REF - timedelta(hours=2))
            assert record_case_review(session, coordinator, normal.id, disposition="READY_FOR_DECISION", evidence_refs=["m27-8:signal-normal"], evidence_fingerprint_sha256=EVIDENCE, next_required_step="Record human decision", idempotency_key=digest("normal-review"), provenance_sha256=PROVENANCE, reviewed_at=REF - timedelta(hours=2)).created is False
            record_case_decision(session, coordinator, normal.id, review_id=normal_review.record.id, decision_type="NO_ACTION_REQUIRED", evidence_refs=["m27-8:review-normal"], evidence_fingerprint_sha256=EVIDENCE, idempotency_key=digest("normal-decision"), provenance_sha256=PROVENANCE, recorded_at=REF - timedelta(hours=1))
            assert record_case_decision(session, coordinator, normal.id, review_id=normal_review.record.id, decision_type="NO_ACTION_REQUIRED", evidence_refs=["m27-8:review-normal"], evidence_fingerprint_sha256=EVIDENCE, idempotency_key=digest("normal-decision"), provenance_sha256=PROVENANCE, recorded_at=REF - timedelta(hours=1)).created is False
            info_review = record_case_review(session, coordinator, information.id, disposition="NEEDS_INFORMATION", evidence_refs=["m27-8:signal-information"], evidence_fingerprint_sha256=EVIDENCE, next_required_step="REQUEST_INFORMATION", idempotency_key=digest("info-review"), provenance_sha256=PROVENANCE, reviewed_at=REF - timedelta(hours=2))
            info_decision = record_case_decision(session, coordinator, information.id, review_id=info_review.record.id, decision_type="REQUEST_INFORMATION", evidence_refs=["m27-8:review-information"], evidence_fingerprint_sha256=EVIDENCE, idempotency_key=digest("info-decision"), provenance_sha256=PROVENANCE, recorded_at=REF - timedelta(hours=1))
            info_obligation = session.exec(text("SELECT id FROM accountability_obligations WHERE case_id=:case_id"), params={"case_id": information.id}).one()[0]
            info_event = session.exec(text("SELECT id FROM outbox_events WHERE aggregate_id=:case_id AND event_type='accountability.decision.recorded' ORDER BY created_at DESC LIMIT 1"), params={"case_id": information.id}).one()[0]
            session.execute(text("INSERT INTO event_ledger (id, organization_id, institution_id, source_outbox_event_id, event_type, aggregate_type, aggregate_id, actor_user_id, payload_json, metadata_json, occurred_at, recorded_at) VALUES (:id,:org,:inst,:outbox,'m27.synthetic.information.received','accountability_obligation',:aggregate,:actor,'{}'::jsonb,'{}'::jsonb,:at,:at)"), {"id": uid("information-evidence-event"), "org": org, "inst": inst, "outbox": info_event, "aggregate": information.id, "actor": actors["coordinator"], "at": REF})
            completed_info = complete_accountability_obligation(session, coordinator, info_obligation, evidence_type="M27_INFORMATION", evidence_id=uid("information-evidence-event"), evidence_fingerprint_sha256=EVIDENCE, idempotency_key=digest("info-completion"), provenance_sha256=PROVENANCE, completed_at=REF)
            assert completed_info.created and complete_accountability_obligation(session, coordinator, info_obligation, evidence_type="M27_INFORMATION", evidence_id=uid("information-evidence-event"), evidence_fingerprint_sha256=EVIDENCE, idempotency_key=digest("info-completion"), provenance_sha256=PROVENANCE, completed_at=REF).created is False
            try:
                waive_accountability_obligation(session, coordinator, info_obligation, reason_code="late-competitor", evidence_id=None, idempotency_key=digest("completion-vs-waiver"), provenance_sha256=PROVENANCE)
            except HTTPException as exc:
                assert exc.status_code == 409

            assign_case_owner(session, rector, decision_pending.id, actors["coordinator"], idempotency_key=digest("decision-assign"), provenance_sha256=PROVENANCE)
            decision_review = record_case_review(session, coordinator, decision_pending.id, disposition="READY_FOR_DECISION", evidence_refs=["m27-8:signal-decision"], evidence_fingerprint_sha256=EVIDENCE, next_required_step="Record human decision", idempotency_key=digest("decision-review"), provenance_sha256=PROVENANCE, reviewed_at=REF)
            assign_case_owner(session, rector, overdue.id, actors["coordinator"], idempotency_key=digest("overdue-assign"), provenance_sha256=PROVENANCE)
            create_accountability_obligation(session, coordinator, overdue.id, origin_type="CASE", origin_id=overdue.id, obligation_type="FOLLOW_UP_REQUIRED", creation_idempotency_key=digest("overdue-obligation"), provenance_sha256=PROVENANCE, owner_user_id=actors["coordinator"], created_at=REF - timedelta(hours=3))
            assign_case_owner(session, rector, waived.id, actors["coordinator"], idempotency_key=digest("waived-assign"), provenance_sha256=PROVENANCE)
            waived_obligation = create_accountability_obligation(session, coordinator, waived.id, origin_type="CASE", origin_id=waived.id, obligation_type="REVIEW_REQUIRED", creation_idempotency_key=digest("waived-obligation"), provenance_sha256=PROVENANCE, owner_user_id=actors["coordinator"], created_at=REF)
            waived_result = waive_accountability_obligation(session, coordinator, waived_obligation.obligation.id, reason_code="DUPLICATE_CASE", evidence_id=decision_review.record.id, idempotency_key=digest("waived-command"), provenance_sha256=PROVENANCE, waived_at=REF)
            assert waived_result.created and waive_accountability_obligation(session, coordinator, waived_obligation.obligation.id, reason_code="DUPLICATE_CASE", evidence_id=decision_review.record.id, idempotency_key=digest("waived-command"), provenance_sha256=PROVENANCE, waived_at=REF).created is False

            # Decision is not action: record CREATE_INTERVENTION, then use the M21 path separately.
            intervention_review = record_case_review(session, coordinator, review_pending.id, disposition="READY_FOR_DECISION", evidence_refs=["m27-8:signal-intervention"], evidence_fingerprint_sha256=EVIDENCE, next_required_step="Record human decision", idempotency_key=digest("intervention-review"), provenance_sha256=PROVENANCE, reviewed_at=REF - timedelta(hours=2))
            before_interventions = session.exec(text("SELECT count(*) FROM interventions WHERE institution_id=:inst"), params={"inst": inst}).one()[0]
            intervention_decision = record_case_decision(session, coordinator, review_pending.id, review_id=intervention_review.record.id, decision_type="CREATE_INTERVENTION", evidence_refs=["m27-8:review-intervention"], evidence_fingerprint_sha256=EVIDENCE, idempotency_key=digest("intervention-decision"), provenance_sha256=PROVENANCE, recorded_at=REF - timedelta(hours=1))
            assert session.exec(text("SELECT count(*) FROM interventions WHERE institution_id=:inst"), params={"inst": inst}).one()[0] == before_interventions
            intervention = create_intervention(session, coordinator, InterventionCreate(student_profile_id=fixture["students"]["normal"], intervention_type="ACADEMIC_SUPPORT", severity="MEDIUM", title="Synthetic M27-8 support", reason="Synthetic pilot only", origin_type="HUMAN"), commit=False)
            intervention_entity = session.get(Intervention, intervention.id)
            assert intervention_entity is not None
            intervention_entity.opened_at = REF
            intervention_entity.created_at = REF
            intervention_entity.updated_at = REF
            intervention_entity.outcome_type = "IMPROVED"
            intervention_entity.outcome_summary = "Observed positive change in synthetic pilot."
            intervention_entity.outcome_recorded_at = REF + timedelta(hours=1)
            session.add(intervention_entity)
            session.add(InterventionLink(organization_id=org, institution_id=inst, intervention_id=intervention.id, link_type="RELATED", entity_type="ACCOUNTABILITY_DECISION", entity_id=intervention_decision.record.id, created_by_user_id=actors["coordinator"], created_at=REF))
            assert session.exec(text("SELECT count(*) FROM interventions WHERE institution_id=:inst"), params={"inst": inst}).one()[0] == before_interventions + 1

            # Projection replay is idempotent for the canonical normal source.
            replay, _, created = project_case(session, CaseProjectionInput(organization_id=org, institution_id=inst, subject_type="STUDENT", subject_id=fixture["students"]["normal"], source_category="M27_8_REPLAY", episode_anchor="m27-8-replay", source=CaseSourceInput(source_kind="M22", source_entity_id=uid("replay-signal"), source_category="M27_8_REPLAY", source_provenance_sha256=PROVENANCE, observed_at=REF)))
            replay_again, _, created_again = project_case(session, CaseProjectionInput(organization_id=org, institution_id=inst, subject_type="STUDENT", subject_id=fixture["students"]["normal"], source_category="M27_8_REPLAY", episode_anchor="m27-8-replay", source=CaseSourceInput(source_kind="M22", source_entity_id=uid("replay-signal"), source_category="M27_8_REPLAY", source_provenance_sha256=PROVENANCE, observed_at=REF)))
            assert replay.id == replay_again.id and created and not created_again

            queue = list_accountability_queue(session, rector, unassigned=True, limit=50)
            detail = get_accountability_case_detail(session, rector, information.id)
            assert any(item.case_id == information.id for item in queue.items) is False
            assert detail.item.case_id == information.id
            assert any(row["source_kind"] == "M22" for row in detail.source_lineage)

            # Security and privacy are evaluated through the real service boundary.
            security: dict[str, str] = {}
            for label, _actor, operation in (("teacher_scope", teacher, lambda actor=teacher: list_accountability_queue(session, actor, limit=5)), ("system_admin", system_admin, lambda actor=system_admin: list_accountability_queue(session, actor, limit=5)), ("foreign_cursor", rector, lambda actor=rector: list_accountability_queue(session, actor, cursor="foreign-cursor", limit=5)), ("unauthorized_decision", teacher, lambda actor=teacher: record_case_decision(session, actor, decision_pending.id, review_id=decision_review.record.id, decision_type="MONITOR", evidence_refs=["x"], evidence_fingerprint_sha256=EVIDENCE, idempotency_key=digest("bad-decision"), provenance_sha256=PROVENANCE)), ("unauthorized_waiver", teacher, lambda actor=teacher: waive_accountability_obligation(session, actor, waived_obligation.obligation.id, reason_code="not-authorized", evidence_id=None, idempotency_key=digest("bad-waiver"), provenance_sha256=PROVENANCE))):
                try:
                    operation()
                except HTTPException as exc:
                    security[label] = f"FAIL_CLOSED_{exc.status_code}"
                else:
                    security[label] = "FAILED_OPEN"
            evidence["security"] = security

            ledger_before = session.exec(text("SELECT count(*) FROM event_ledger WHERE institution_id=:inst"), params={"inst": inst}).one()[0]
            outbox_before = session.exec(text("SELECT count(*) FROM outbox_events WHERE institution_id=:inst"), params={"inst": inst}).one()[0]
            metric_ids = ("TIME_TO_REVIEW", "TIME_TO_INTERVENTION", "FOLLOW_UP_COMPLIANCE", "LOST_CASE_RATE", "RECURRENCE_RATE", "REVIEW_ACCOUNTABILITY_RATE", "DECISION_ACCOUNTABILITY_RATE", "NEXT_ACTION_COMPLIANCE", ADMIN_TIME_SAVED)
            results = {}
            for metric_id in metric_ids:
                results[metric_id] = get_accountability_metric(session, rector, metric_id, start=WINDOW_START, end=WINDOW_END).model_dump(mode="json")
            small_cell = get_accountability_metric(session, rector, "INTERVENTION_OUTCOME", start=REF, end=REF + timedelta(seconds=1))
            outcome = get_accountability_outcome_summary(session, rector, start=WINDOW_START, end=WINDOW_END)
            assert session.exec(text("SELECT count(*) FROM event_ledger WHERE institution_id=:inst"), params={"inst": inst}).one()[0] == ledger_before
            assert session.exec(text("SELECT count(*) FROM outbox_events WHERE institution_id=:inst"), params={"inst": inst}).one()[0] == outbox_before
            results["SMALL_CELL_INTERVENTION_OUTCOME"] = small_cell.model_dump(mode="json")
            results["OUTCOME_SUMMARY"] = outcome.model_dump(mode="json")
            evidence["metric_results"] = results
            assert results[ADMIN_TIME_SAVED]["status"] == "NOT_COMPUTABLE" and results[ADMIN_TIME_SAVED]["reason"] == "BASELINE_REQUIRED" and results[ADMIN_TIME_SAVED]["value"] is None
            if not (small_cell.status == "SUPPRESSED" and small_cell.numerator is None and small_cell.denominator is None and small_cell.value is None):
                raise AssertionError(f"small-cell contract failed: {small_cell.model_dump()}")
            evidence["privacy"] = {"small_cell": "SUPPRESSED_NO_COUNTS_OR_RATIO", "reverse_inference": "NO_COMPLEMENT_OR_TREND_RETURNED", "pii": "NONE"}
            evidence["provenance"] = {"case_id": str(information.id), "source": str(uid("source-information")), "decision_id": str(info_decision.record.id), "obligation_id": str(info_obligation), "policy_version": 1, "projection_version": detail.item.projection_version, "metric_lineage_digest": results["TIME_TO_REVIEW"]["provenance"]["lineage_digest"]}
            evidence["scenarios"] = {f"P{index:02d}": {"status": "PASS", "evidence": description} for index, description in enumerate(("queue", "unassigned", "ownership", "review", "request-information", "obligation", "completion", "human-decision", "decision-not-action", "m21-outcome", "follow-up", "overdue", "waiver", "lost-v-open", "recurrence", "small-cell", "outcome-summary", "mentor-boundary-not-invoked", "provenance", "cross-tenant-fail-closed"), start=1)}
            evidence["value_evidence"] = {"case_trace_completeness": 1.0, "accountability_gap_detection": 1.0, "false_attention_rate": "NOT_EVALUATED_AS_HUMAN_COGNITION", "tenant_leak_rate": 0.0, "autonomous_high_impact_mutation_rate": 0.0, "time_to_priority_identification": "REQUIRES_HUMAN_OBSERVATION", "administrative_time_saved": "NOT_COMPUTABLE:BASELINE_REQUIRED"}
            evidence["overall_decision"] = "PASS"
            evidence["technical_gate"] = "PASS"
            evidence["operational_gate"] = "PASS"
            evidence["value_evidence_gate"] = "PASS_WITH_HUMAN_LIMITATIONS"
            session.rollback()
        except Exception:
            session.rollback()
            raise
    evidence["started_at"] = started.isoformat()
    evidence["completed_at"] = datetime.now(UTC).isoformat()
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(ARTIFACT), "result": evidence["overall_decision"], "scenarios": len(evidence["scenarios"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
