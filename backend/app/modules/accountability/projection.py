from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Session, select

from app.modules.accountability.identity import (
    IDENTITY_VERSION,
    CaseIdentityDecision,
    IdentityCandidate,
    resolve_identity,
)
from app.modules.accountability.models import AccountabilityCase, AccountabilityCaseSource


@dataclass(frozen=True, slots=True)
class CaseSourceInput:
    source_kind: str
    source_entity_id: UUID
    source_category: str
    source_provenance_sha256: str
    observed_at: datetime
    source_event_id: UUID | None = None
    source_event_version: int = 1


@dataclass(frozen=True, slots=True)
class CaseProjectionInput:
    organization_id: UUID
    institution_id: UUID
    subject_type: str
    subject_id: UUID
    source_category: str
    episode_anchor: str
    source: CaseSourceInput
    reopen_allowed: bool = False
    category_mapping: dict[str, str] | None = None


def _sha256(value: dict[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def source_fingerprint(source: CaseSourceInput) -> str:
    return _sha256(
        {
            "source_kind": source.source_kind,
            "source_entity_id": str(source.source_entity_id),
            "source_event_id": str(source.source_event_id) if source.source_event_id else None,
            "source_event_version": source.source_event_version,
            "source_provenance_sha256": source.source_provenance_sha256,
        }
    )


def _candidates(session: Session, value: CaseProjectionInput) -> tuple[IdentityCandidate, ...]:
    rows = session.exec(
        select(AccountabilityCase).where(
            AccountabilityCase.organization_id == value.organization_id,
            AccountabilityCase.institution_id == value.institution_id,
            AccountabilityCase.subject_type == value.subject_type,
            AccountabilityCase.subject_id == value.subject_id,
        )
    ).all()
    return tuple(
        IdentityCandidate(
            case_id=row.id,
            subject_type=row.subject_type,
            subject_id=row.subject_id,
            normalized_category=row.normalized_category,
            episode_anchor=row.episode_anchor,
            lifecycle=row.lifecycle,
            resolved_at=None,
            related_case_id=row.related_case_id,
        )
        for row in rows
    )


def project_case(session: Session, value: CaseProjectionInput) -> tuple[AccountabilityCase, CaseIdentityDecision, bool]:
    """Create or replay one case and attach one canonical source idempotently."""
    if value.organization_id.int == 0 or value.institution_id.int == 0:
        raise ValueError("tenant identifiers are required")
    if not re.fullmatch(r"[0-9a-f]{64}", value.source.source_provenance_sha256):
        raise ValueError("source provenance must be a SHA-256 hex digest")

    decision = resolve_identity(
        organization_id=value.organization_id,
        institution_id=value.institution_id,
        subject_type=value.subject_type,
        subject_id=value.subject_id,
        source_category=value.source_category,
        episode_anchor=value.episode_anchor,
        candidates=_candidates(session, value),
        reopen_allowed=value.reopen_allowed,
        category_mapping=value.category_mapping,
    )
    case = session.exec(
        select(AccountabilityCase).where(
            AccountabilityCase.institution_id == value.institution_id,
            AccountabilityCase.identity_version == IDENTITY_VERSION,
            AccountabilityCase.identity_key_sha256 == decision.identity_key_sha256,
        )
    ).first()
    if case is None:
        now = datetime.now(UTC)
        lifecycle = "REOPENED" if decision.classification == "REOPENED_CASE" else "OPEN"
        case = AccountabilityCase(
            organization_id=value.organization_id,
            institution_id=value.institution_id,
            subject_type=value.subject_type,
            subject_id=value.subject_id,
            source_category=value.source_category,
            normalized_category=decision.normalized_category,
            category_mapping_version=1,
            identity_version=IDENTITY_VERSION,
            identity_key_sha256=decision.identity_key_sha256,
            episode_anchor=value.episode_anchor,
            lifecycle=lifecycle,
            recurrence_classification=decision.classification,
            related_case_id=decision.related_case_id,
            created_at=now,
            updated_at=now,
        )
        session.add(case)
        session.flush()

    fingerprint = source_fingerprint(value.source)
    existing_source = session.exec(
        select(AccountabilityCaseSource).where(
            AccountabilityCaseSource.institution_id == value.institution_id,
            AccountabilityCaseSource.source_fingerprint_sha256 == fingerprint,
        )
    ).first()
    if existing_source is not None:
        if existing_source.case_id != case.id:
            raise ValueError("source fingerprint is already linked to another case")
        return case, decision, False

    session.add(
        AccountabilityCaseSource(
            organization_id=value.organization_id,
            institution_id=value.institution_id,
            case_id=case.id,
            source_kind=value.source.source_kind,
            source_entity_id=value.source.source_entity_id,
            source_event_id=value.source.source_event_id,
            source_event_version=value.source.source_event_version,
            source_category=value.source_category,
            source_provenance_sha256=value.source.source_provenance_sha256,
            source_fingerprint_sha256=fingerprint,
            observed_at=value.source.observed_at,
        )
    )
    case.projection_version += 1
    case.updated_at = datetime.now(UTC)
    session.add(case)
    return case, decision, True
