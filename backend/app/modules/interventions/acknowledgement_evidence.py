"""M21-owned acknowledgement evidence commands and bounded reads."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.security.trusted_context import issue_capability


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def link_followup_acknowledgement(
    session: Session, principal: CurrentPrincipal, *, followup_id: UUID,
    receipt_id: UUID, idempotency_key: UUID,
) -> UUID:
    operation = _digest({"actor": principal.user_id, "key": idempotency_key, "purpose": "M21_ACK_LINK"})
    capability = issue_capability(
        principal=principal, purpose="M21_ACK_LINK", receipt_id=receipt_id,
        target_id=followup_id, operation_key=operation,
        operation_fingerprint=_digest({"receipt": receipt_id, "followup": followup_id}),
    )
    link_id = session.execute(text("SELECT public.m21_link_acknowledgement_evidence(:capability)"), {"capability": capability}).scalar_one()
    session.commit()
    return link_id


def correct_followup_acknowledgement(
    session: Session, principal: CurrentPrincipal, *, followup_id: UUID,
    receipt_id: UUID, link_id: UUID, reason_code: str,
    replacement_followup_id: UUID | None, idempotency_key: UUID,
) -> UUID:
    operation = _digest({"actor": principal.user_id, "key": idempotency_key, "purpose": "M21_ACK_CORRECT"})
    capability = issue_capability(
        principal=principal, purpose="M21_ACK_CORRECT", receipt_id=receipt_id,
        target_id=followup_id, related_link_id=link_id,
        replacement_target_id=replacement_followup_id, reason_code=reason_code,
        operation_key=operation,
        operation_fingerprint=_digest({"receipt": receipt_id, "followup": followup_id, "link": link_id, "replacement": replacement_followup_id, "reason": reason_code}),
    )
    correction_id = session.execute(text("SELECT public.m21_correct_acknowledgement_evidence(:capability)"), {"capability": capability}).scalar_one()
    session.commit()
    return correction_id


def read_followup_acknowledgement(
    session: Session, principal: CurrentPrincipal, *, followup_id: UUID,
    receipt_id: UUID, idempotency_key: UUID,
) -> list[dict[str, object]]:
    operation = _digest({"actor": principal.user_id, "key": idempotency_key, "purpose": "M21_ACK_READ"})
    capability = issue_capability(
        principal=principal, purpose="M21_ACK_READ", receipt_id=receipt_id,
        target_id=followup_id, operation_key=operation,
        operation_fingerprint=_digest({"receipt": receipt_id, "followup": followup_id}),
    )
    rows = session.execute(text("SELECT * FROM public.m21_read_acknowledgement_evidence(:capability)"), {"capability": capability}).mappings().all()
    session.commit()
    return [dict(row) for row in rows]
