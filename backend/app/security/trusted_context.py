"""Narrow SEC-TC1 capability issuance client.

The issuer pool is separate from the normal education_app pool. Capability
values are returned only to the immediate caller and must never be logged.
"""

from __future__ import annotations

import hashlib
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import text

from app.api.access import GuardianPrincipal
from app.api.deps import CurrentPrincipal
from app.db.session import get_trusted_context_issuer_engine

PURPOSES = frozenset(
    {
        "M21_ACK_LINK", "M21_ACK_CORRECT", "M21_ACK_READ",
        "M27_ACK_LINK", "M27_ACK_CORRECT", "M27_ACK_READ",
        "M13_NOTICE_ACK",
    }
)

BATCH_PURPOSES = frozenset({"M21_ACK_BATCH_READ", "M27_ACK_BATCH_READ"})
MAX_BATCH_TARGETS = 25


def canonical_batch_target_digest(
    *,
    purpose: str,
    organization_id: UUID,
    institution_id: UUID,
    target_ids: list[UUID] | tuple[UUID, ...],
) -> str:
    """Return the stable tenant- and purpose-bound batch fingerprint."""
    if purpose not in BATCH_PURPOSES:
        raise ValueError("Unsupported SEC-TC1 batch purpose")
    if not target_ids or len(target_ids) > MAX_BATCH_TARGETS:
        raise ValueError("SEC-TC1 batch target set is outside its bound")
    if any(target_id is None for target_id in target_ids):
        raise ValueError("SEC-TC1 batch target set cannot contain null IDs")
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("SEC-TC1 batch target set cannot contain duplicate IDs")
    canonical = "|".join(
        (
            purpose,
            str(organization_id),
            str(institution_id),
            ",".join(str(target_id) for target_id in sorted(target_ids, key=str)),
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def batch_operation_key(
    *,
    principal: CurrentPrincipal,
    purpose: str,
    target_ids: list[UUID] | tuple[UUID, ...],
) -> UUID:
    """Return the stable idempotency key for one bounded read operation.

    The continuity worklist has no caller supplied mutation key. Its retry
    identity is therefore derived from the authenticated actor, tenant,
    purpose, and canonical target set. This makes equivalent retries converge
    without allowing a reordered target list to rotate the capability.
    """
    digest = canonical_batch_target_digest(
        purpose=purpose,
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        target_ids=target_ids,
    )
    return uuid5(
        NAMESPACE_URL,
        f"education-os:sec-tc1:{principal.user_id}:{purpose}:{digest}",
    )


def issue_capability(
    *,
    principal: CurrentPrincipal | GuardianPrincipal,
    purpose: str,
    receipt_id: UUID | None,
    target_id: UUID,
    operation_key: str,
    operation_fingerprint: str,
    related_link_id: UUID | None = None,
    replacement_target_id: UUID | None = None,
    reason_code: str | None = None,
    guardian_profile_id: UUID | None = None,
) -> str:
    if purpose not in PURPOSES:
        raise ValueError("Unsupported SEC-TC1 purpose")
    engine = get_trusted_context_issuer_engine()
    receipt_value = receipt_id
    if purpose == "M13_NOTICE_ACK":
        if not isinstance(principal, GuardianPrincipal) or guardian_profile_id is None:
            raise ValueError("M13 notice acknowledgement requires guardian principal context")
        receipt_value = None
    with engine.begin() as connection:
        token = connection.execute(
            text(
                """SELECT public.sec_tc1_issue_capability(
                    :purpose, :actor, :organization, :institution, :receipt,
                    :target, :guardian_profile, :related_link, :replacement_target, :reason,
                    :operation_key, :fingerprint)"""
            ),
            {
                "purpose": purpose,
                "actor": principal.user_id,
                "organization": principal.organization_id,
                "institution": principal.institution_id,
                "receipt": receipt_value,
                "target": target_id,
                "guardian_profile": guardian_profile_id,
                "related_link": related_link_id,
                "replacement_target": replacement_target_id,
                "reason": reason_code,
                "operation_key": operation_key,
                "fingerprint": operation_fingerprint,
            },
        ).scalar_one()
    return str(token)


def issue_batch_capability(
    *,
    principal: CurrentPrincipal,
    purpose: str,
    target_ids: list[UUID] | tuple[UUID, ...],
    operation_key: str,
    operation_fingerprint: str,
) -> str:
    """Issue a domain-specific, bounded target-set capability."""
    if purpose not in BATCH_PURPOSES:
        raise ValueError("Unsupported SEC-TC1 batch purpose")
    target_set_digest = canonical_batch_target_digest(
        purpose=purpose,
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        target_ids=target_ids,
    )
    engine = get_trusted_context_issuer_engine()
    with engine.begin() as connection:
        token = connection.execute(
            text(
                """SELECT public.sec_tc1_issue_batch_capability(
                    :purpose, :actor, :organization, :institution,
                    :target_set_digest, :operation_key, :fingerprint)"""
            ),
            {
                "purpose": purpose,
                "actor": principal.user_id,
                "organization": principal.organization_id,
                "institution": principal.institution_id,
                "target_set_digest": target_set_digest,
                "operation_key": operation_key,
                "fingerprint": operation_fingerprint,
            },
        ).scalar_one()
    return str(token)


def issue_guardian_notice_acknowledgement(
    *, guardian: GuardianPrincipal, notice_id: UUID, operation_key: str, operation_fingerprint: str
) -> str:
    return issue_capability(
        principal=guardian,
        purpose="M13_NOTICE_ACK",
        receipt_id=None,
        target_id=notice_id,
        operation_key=operation_key,
        operation_fingerprint=operation_fingerprint,
        guardian_profile_id=guardian.guardian_profile_id,
    )
