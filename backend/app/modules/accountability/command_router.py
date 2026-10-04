from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session
from app.modules.accountability.acknowledgement_evidence import (
    correct_obligation_acknowledgement,
    link_obligation_acknowledgement,
    read_obligation_acknowledgement,
)
from app.modules.accountability.acknowledgement_schemas import (
    AcknowledgementEvidenceCorrectionRequest,
    AcknowledgementEvidenceLinkRequest,
    AcknowledgementEvidenceMutationRead,
    AcknowledgementEvidenceRead,
)
from app.modules.accountability.command_schemas import (
    AccountabilityCommandRead,
    DecisionCommand,
    ObligationCompletionCommand,
    ObligationWaiverCommand,
    OwnerCommand,
    ReviewCommand,
)
from app.modules.accountability.ledger_service import (
    assign_case_owner,
    record_case_decision,
    record_case_review,
    transfer_case_owner,
    unassign_case_owner,
)
from app.modules.accountability.obligation_service import (
    complete_accountability_obligation,
    waive_accountability_obligation,
)

router = APIRouter(prefix="/accountability", tags=["accountability-commands"])
PrincipalDep = Annotated[CurrentPrincipal, Depends(get_current_principal)]
SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/obligations/{obligation_id}/acknowledgement-evidence", response_model=AcknowledgementEvidenceMutationRead)
def link_obligation_acknowledgement_api(
    obligation_id: UUID, payload: AcknowledgementEvidenceLinkRequest,
    principal: PrincipalDep, session: SessionDep,
) -> AcknowledgementEvidenceMutationRead:
    link_id = link_obligation_acknowledgement(session, principal, obligation_id=obligation_id, receipt_id=payload.receipt_id, idempotency_key=payload.idempotency_key)
    session.commit()
    return AcknowledgementEvidenceMutationRead(id=link_id)


@router.post("/obligations/{obligation_id}/acknowledgement-evidence/{link_id}/correction", response_model=AcknowledgementEvidenceMutationRead)
def correct_obligation_acknowledgement_api(
    obligation_id: UUID, link_id: UUID, payload: AcknowledgementEvidenceCorrectionRequest,
    principal: PrincipalDep, session: SessionDep,
) -> AcknowledgementEvidenceMutationRead:
    correction_id = correct_obligation_acknowledgement(session, principal, obligation_id=obligation_id, receipt_id=payload.receipt_id, link_id=link_id, reason_code=payload.reason_code, replacement_obligation_id=payload.replacement_obligation_id, idempotency_key=payload.idempotency_key)
    session.commit()
    return AcknowledgementEvidenceMutationRead(id=correction_id)


@router.get("/obligations/{obligation_id}/acknowledgement-evidence", response_model=list[AcknowledgementEvidenceRead])
def read_obligation_acknowledgement_api(
    obligation_id: UUID, receipt_id: UUID, idempotency_key: UUID,
    principal: PrincipalDep, session: SessionDep,
) -> list[AcknowledgementEvidenceRead]:
    rows = read_obligation_acknowledgement(session, principal, obligation_id=obligation_id, receipt_id=receipt_id, idempotency_key=idempotency_key)
    session.commit()
    return [AcknowledgementEvidenceRead.model_validate(row) for row in rows]


def _read(command: str, result: object, *, provenance_sha256: str) -> AccountabilityCommandRead:
    record = result.record  # type: ignore[attr-defined]
    return AccountabilityCommandRead(
        command=command,
        id=record.id,
        case_id=getattr(record, "case_id", None),
        created=result.created,  # type: ignore[attr-defined]
        decision_type=getattr(record, "decision_type", None),
        lifecycle=getattr(record, "lifecycle", None),
        owner_user_id=getattr(record, "new_owner_user_id", None)
        or getattr(record, "owner_user_id", None),
        review_id=getattr(record, "review_id", None),
        execution_required=getattr(record, "execution_required", None),
        provenance_sha256=provenance_sha256,
    )


@router.post("/cases/{case_id}/owner/assign", response_model=AccountabilityCommandRead)
def assign_owner(
    case_id: UUID, payload: OwnerCommand, principal: PrincipalDep, session: SessionDep
) -> AccountabilityCommandRead:
    if payload.owner_user_id is None:
        raise ValueError("owner_user_id is required for assignment")
    result = assign_case_owner(
        session,
        principal,
        case_id,
        payload.owner_user_id,
        idempotency_key=payload.idempotency_key,
        provenance_sha256=payload.provenance_sha256,
        reason_reference=payload.reason_reference,
    )
    session.commit()
    return _read("OWNER_ASSIGNED", result, provenance_sha256=payload.provenance_sha256)


@router.post("/cases/{case_id}/owner/transfer", response_model=AccountabilityCommandRead)
def transfer_owner(
    case_id: UUID, payload: OwnerCommand, principal: PrincipalDep, session: SessionDep
) -> AccountabilityCommandRead:
    if payload.owner_user_id is None:
        raise ValueError("owner_user_id is required for transfer")
    result = transfer_case_owner(
        session,
        principal,
        case_id,
        payload.owner_user_id,
        idempotency_key=payload.idempotency_key,
        provenance_sha256=payload.provenance_sha256,
        reason_reference=payload.reason_reference,
    )
    session.commit()
    return _read("OWNER_TRANSFERRED", result, provenance_sha256=payload.provenance_sha256)


@router.post("/cases/{case_id}/owner/unassign", response_model=AccountabilityCommandRead)
def unassign_owner(
    case_id: UUID, payload: OwnerCommand, principal: PrincipalDep, session: SessionDep
) -> AccountabilityCommandRead:
    result = unassign_case_owner(
        session,
        principal,
        case_id,
        idempotency_key=payload.idempotency_key,
        provenance_sha256=payload.provenance_sha256,
        reason_reference=payload.reason_reference,
    )
    session.commit()
    return _read("OWNER_UNASSIGNED", result, provenance_sha256=payload.provenance_sha256)


@router.post("/cases/{case_id}/review", response_model=AccountabilityCommandRead)
def review(
    case_id: UUID, payload: ReviewCommand, principal: PrincipalDep, session: SessionDep
) -> AccountabilityCommandRead:
    result = record_case_review(
        session,
        principal,
        case_id,
        disposition=payload.disposition,
        evidence_refs=payload.evidence_refs,
        evidence_fingerprint_sha256=payload.evidence_fingerprint_sha256,
        next_required_step=payload.next_required_step,
        idempotency_key=payload.idempotency_key,
        provenance_sha256=payload.provenance_sha256,
        note_reference=payload.note_reference,
    )
    session.commit()
    return _read("REVIEW_RECORDED", result, provenance_sha256=payload.provenance_sha256)


@router.post("/cases/{case_id}/decision", response_model=AccountabilityCommandRead)
def decision(
    case_id: UUID, payload: DecisionCommand, principal: PrincipalDep, session: SessionDep
) -> AccountabilityCommandRead:
    result = record_case_decision(
        session,
        principal,
        case_id,
        review_id=payload.review_id,
        decision_type=payload.decision_type,
        evidence_refs=payload.evidence_refs,
        evidence_fingerprint_sha256=payload.evidence_fingerprint_sha256,
        idempotency_key=payload.idempotency_key,
        provenance_sha256=payload.provenance_sha256,
        reason_reference=payload.reason_reference,
    )
    session.commit()
    return _read("DECISION_RECORDED", result, provenance_sha256=payload.provenance_sha256)


@router.post("/obligations/{obligation_id}/complete", response_model=AccountabilityCommandRead)
def complete_obligation(
    obligation_id: UUID,
    payload: ObligationCompletionCommand,
    principal: PrincipalDep,
    session: SessionDep,
) -> AccountabilityCommandRead:
    result = complete_accountability_obligation(
        session,
        principal,
        obligation_id,
        evidence_type=payload.evidence_type,
        evidence_id=payload.evidence_id,
        evidence_fingerprint_sha256=payload.evidence_fingerprint_sha256,
        idempotency_key=payload.idempotency_key,
        provenance_sha256=payload.provenance_sha256,
        completed_at=payload.completed_at,
    )
    session.commit()
    return _read("OBLIGATION_COMPLETED", result, provenance_sha256=payload.provenance_sha256)


@router.post("/obligations/{obligation_id}/waive", response_model=AccountabilityCommandRead)
def waive_obligation(
    obligation_id: UUID,
    payload: ObligationWaiverCommand,
    principal: PrincipalDep,
    session: SessionDep,
) -> AccountabilityCommandRead:
    result = waive_accountability_obligation(
        session,
        principal,
        obligation_id,
        reason_code=payload.reason_code,
        evidence_id=payload.evidence_id,
        idempotency_key=payload.idempotency_key,
        provenance_sha256=payload.provenance_sha256,
        waived_at=payload.waived_at,
    )
    session.commit()
    return _read("OBLIGATION_WAIVED", result, provenance_sha256=payload.provenance_sha256)
