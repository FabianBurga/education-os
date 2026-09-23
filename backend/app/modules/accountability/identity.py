from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

IDENTITY_VERSION = 1
CATEGORY_MAPPING_VERSION = 1


@dataclass(frozen=True, slots=True)
class IdentityCandidate:
    case_id: UUID
    subject_type: str
    subject_id: UUID
    normalized_category: str
    episode_anchor: str
    lifecycle: str
    resolved_at: datetime | None = None
    related_case_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CaseIdentityDecision:
    identity_key_sha256: str
    normalized_category: str
    classification: str
    related_case_id: UUID | None
    rule_code: str


def normalize_category(
    source_category: str,
    mapping: dict[str, str] | None = None,
) -> str:
    """Return a transparent projection mapping, never a semantic guess."""
    source = source_category.strip()
    if not source:
        raise ValueError("source_category is required")
    mapped = (mapping or {}).get(source)
    return mapped.strip() if mapped and mapped.strip() else f"SOURCE:{source}"


def identity_key_sha256(
    *,
    organization_id: UUID,
    institution_id: UUID,
    subject_type: str,
    subject_id: UUID,
    normalized_category: str,
    episode_anchor: str,
    identity_version: int = IDENTITY_VERSION,
) -> str:
    if identity_version < 1:
        raise ValueError("identity_version must be >= 1")
    material = {
        "identity_version": identity_version,
        "organization_id": str(organization_id),
        "institution_id": str(institution_id),
        "subject_type": subject_type.strip(),
        "subject_id": str(subject_id),
        "normalized_category": normalized_category.strip(),
        "episode_anchor": episode_anchor.strip(),
    }
    if not material["subject_type"] or not material["normalized_category"] or not material["episode_anchor"]:
        raise ValueError("identity components must be non-empty")
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def resolve_identity(
    *,
    organization_id: UUID,
    institution_id: UUID,
    subject_type: str,
    subject_id: UUID,
    source_category: str,
    episode_anchor: str,
    candidates: tuple[IdentityCandidate, ...] = (),
    reopen_allowed: bool = False,
    category_mapping: dict[str, str] | None = None,
) -> CaseIdentityDecision:
    normalized = normalize_category(source_category, category_mapping)
    key = identity_key_sha256(
        organization_id=organization_id,
        institution_id=institution_id,
        subject_type=subject_type,
        subject_id=subject_id,
        normalized_category=normalized,
        episode_anchor=episode_anchor,
    )
    same_episode = [
        candidate
        for candidate in candidates
        if candidate.subject_type == subject_type
        and candidate.subject_id == subject_id
        and candidate.normalized_category == normalized
        and candidate.episode_anchor == episode_anchor
    ]
    if any(candidate.lifecycle in {"OPEN", "REOPENED"} for candidate in same_episode):
        return CaseIdentityDecision(key, normalized, "SAME_ACTIVE_EPISODE", None, "ACTIVE_MATCH")
    if reopen_allowed and any(candidate.lifecycle == "RESOLVED" for candidate in same_episode):
        resolved = next(candidate for candidate in same_episode if candidate.lifecycle == "RESOLVED")
        return CaseIdentityDecision(key, normalized, "REOPENED_CASE", resolved.case_id, "RESOLVED_WITHIN_REOPEN_POLICY")
    related = next(
        (
            candidate
            for candidate in reversed(candidates)
            if candidate.subject_type == subject_type
            and candidate.subject_id == subject_id
            and candidate.normalized_category == normalized
        ),
        None,
    )
    if related is not None:
        return CaseIdentityDecision(key, normalized, "NEW_RELATED_EPISODE", related.case_id, "NO_ACTIVE_OR_REOPEN_MATCH")
    if any(
        candidate.subject_type == subject_type and candidate.subject_id == subject_id
        for candidate in candidates
    ):
        return CaseIdentityDecision(key, normalized, "NEW_CATEGORY_CASE", None, "CATEGORY_BOUNDARY")
    return CaseIdentityDecision(key, normalized, "NEW_EPISODE", None, "NO_PRIOR_CASE")
