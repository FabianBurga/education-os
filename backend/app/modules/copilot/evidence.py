from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.copilot.access import require_copilot_use
from app.modules.intelligence.access import require_intelligence_manager_read
from app.modules.intelligence.decision_surfaces import intelligence_overview
from app.modules.m21_access import require_student_scope


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    reference_key: str
    evidence_type: str
    source_module: str
    source_entity_type: str
    source_entity_id: UUID | None
    source_version: str | None
    freshness_status: str
    content: dict[str, object]
    scope: dict[str, object]
    evidence_sha256: str


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    intent: str
    items: tuple[EvidenceItem, ...]
    manifest_sha256: str


def canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def freshness_from_snapshot(snapshot_date: date) -> str:
    age_days = max(0, (date.today() - snapshot_date).days)
    if age_days == 0:
        return "CURRENT"
    if age_days == 1:
        return "DELAYED"
    return "STALE"


def _item(
    *,
    reference_key: str,
    evidence_type: str,
    source_module: str,
    source_entity_type: str,
    source_entity_id: UUID | None,
    source_version: str | None,
    freshness_status: str,
    content: dict[str, object],
    scope: dict[str, object],
) -> EvidenceItem:
    digest = canonical_hash(
        {
            "reference_key": reference_key,
            "evidence_type": evidence_type,
            "source_module": source_module,
            "source_entity_type": source_entity_type,
            "source_entity_id": source_entity_id,
            "source_version": source_version,
            "freshness_status": freshness_status,
            "content": content,
            "scope": scope,
        }
    )
    return EvidenceItem(
        reference_key=reference_key,
        evidence_type=evidence_type,
        source_module=source_module,
        source_entity_type=source_entity_type,
        source_entity_id=source_entity_id,
        source_version=source_version,
        freshness_status=freshness_status,
        content=content,
        scope=scope,
        evidence_sha256=digest,
    )


def _bundle(intent: str, items: list[EvidenceItem]) -> EvidenceBundle:
    manifest = canonical_hash(
        {
            "intent": intent,
            "items": [
                {
                    "reference_key": item.reference_key,
                    "evidence_sha256": item.evidence_sha256,
                }
                for item in items
            ],
        }
    )
    return EvidenceBundle(
        intent=intent,
        items=tuple(items),
        manifest_sha256=manifest,
    )


def assemble_institution_risk_evidence(
    session: Session,
    principal: CurrentPrincipal,
) -> EvidenceBundle:
    require_copilot_use(session, principal)
    require_intelligence_manager_read(session, principal)

    overview = intelligence_overview(session, principal)
    content = overview.model_dump(mode="json")
    snapshot_date = overview.snapshot_date
    source_version = (
        f"rules={overview.rule_set_version};"
        f"projection={overview.projection_version};"
        f"policy={overview.policy_source}:{overview.policy_version}"
    )
    item = _item(
        reference_key=(
            "m22:institution-overview:"
            f"{principal.institution_id}:{snapshot_date.isoformat()}"
        ),
        evidence_type="M22_INSTITUTION_OVERVIEW",
        source_module="intelligence",
        source_entity_type="institution_intelligence_daily",
        source_entity_id=None,
        source_version=source_version,
        freshness_status=freshness_from_snapshot(snapshot_date),
        content=content,
        scope={
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
        },
    )
    return _bundle("INSTITUTION_RISK_SUMMARY", [item])


def assemble_student_support_evidence(
    session: Session,
    principal: CurrentPrincipal,
    *,
    student_profile_id: UUID,
) -> EvidenceBundle:
    require_copilot_use(session, principal)
    require_student_scope(
        session,
        principal,
        student_profile_id,
        permission_key="intelligence.read",
    )

    row = session.exec(
        text(
            """
            SELECT
                id,
                academic_period_id,
                snapshot_date,
                overall_priority,
                attendance_priority,
                academic_priority,
                intervention_priority,
                evidence_count,
                rule_set_version,
                projection_version,
                policy_source,
                policy_version,
                control_revision
            FROM student_intelligence_snapshots
            WHERE organization_id = CAST(:organization_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND student_profile_id = CAST(:student_profile_id AS uuid)
            ORDER BY snapshot_date DESC, created_at DESC, id DESC
            LIMIT 1
            """
        ),
        params={
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
            "student_profile_id": str(student_profile_id),
        },
    ).first()

    if row is None:
        return _bundle("STUDENT_SUPPORT_SUMMARY", [])

    content: dict[str, object] = {
        "student_profile_id": str(student_profile_id),
        "academic_period_id": str(row[1]) if row[1] else None,
        "snapshot_date": row[2].isoformat(),
        "overall_priority": str(row[3]),
        "attendance_priority": str(row[4]),
        "academic_priority": str(row[5]),
        "intervention_priority": str(row[6]),
        "evidence_count": int(row[7]),
        "control_revision": int(row[12]) if row[12] is not None else None,
    }
    source_version = (
        f"rules={int(row[8])};projection={int(row[9])};"
        f"policy={str(row[10])}:{int(row[11])}"
    )
    item = _item(
        reference_key=f"m22:student-priority:{row[0]}",
        evidence_type="M22_STUDENT_PRIORITY",
        source_module="intelligence",
        source_entity_type="student_intelligence_snapshots",
        source_entity_id=row[0],
        source_version=source_version,
        freshness_status=freshness_from_snapshot(row[2]),
        content=content,
        scope={
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
            "student_profile_id": str(student_profile_id),
        },
    )
    return _bundle("STUDENT_SUPPORT_SUMMARY", [item])


def assemble_governed_evidence(
    session: Session,
    principal: CurrentPrincipal,
    *,
    intent: str,
    target_student_profile_id: UUID | None = None,
) -> EvidenceBundle:
    if intent == "INSTITUTION_RISK_SUMMARY":
        return assemble_institution_risk_evidence(session, principal)
    if intent == "STUDENT_SUPPORT_SUMMARY":
        if target_student_profile_id is None:
            raise ValueError("student target required")
        return assemble_student_support_evidence(
            session,
            principal,
            student_profile_id=target_student_profile_id,
        )
    raise ValueError(f"unsupported M23-2 foundation intent: {intent}")
