from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.copilot.access import (
    require_copilot_action_approve,
    require_copilot_use,
)
from app.modules.copilot.action_schemas import ActionProposalRead
from app.modules.interventions.schemas import InterventionCreate
from app.modules.interventions.service import create_intervention

ACTION_TYPE_CREATE_INTERVENTION = "CREATE_INTERVENTION"
ACTION_STATUSES = {
    "PROPOSED",
    "APPROVED",
    "REJECTED",
    "EXECUTED",
    "FAILED",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _payload_sha256(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        _canonical_json(payload).encode("utf-8")
    ).hexdigest()


def _row_to_read(row: object) -> ActionProposalRead:
    mapping = row
    payload = mapping["payload_json"]
    citations = mapping["evidence_citations_json"]
    result_ref = mapping["result_ref_json"]

    return ActionProposalRead(
        id=mapping["id"],
        run_id=mapping["run_id"],
        action_type=mapping["action_type"],
        target_student_profile_id=mapping["target_student_profile_id"],
        payload=dict(payload),
        rationale=mapping["rationale_text"],
        evidence_citations=[str(value) for value in citations],
        proposed_by_user_id=mapping["proposed_by_user_id"],
        created_at=mapping["created_at"],
        status=mapping["event_type"],
        last_event_at=mapping["event_created_at"],
        decision_by_user_id=(
            None
            if mapping["event_type"] == "PROPOSED"
            else mapping["event_actor_user_id"]
        ),
        decision_note=mapping["reason_text"],
        result_ref=None if result_ref is None else dict(result_ref),
        failure_code=mapping["failure_code"],
    )


def _proposal_read_query() -> str:
    return """
        SELECT
            p.id,
            p.run_id,
            p.proposed_by_user_id,
            p.action_type,
            p.target_student_profile_id,
            p.payload_json,
            p.rationale_text,
            p.evidence_citations_json,
            p.created_at,
            latest.event_type,
            latest.actor_user_id AS event_actor_user_id,
            latest.reason_text,
            latest.result_ref_json,
            latest.failure_code,
            latest.created_at AS event_created_at
        FROM copilot_action_proposals p
        JOIN LATERAL (
            SELECT
                e.event_type,
                e.actor_user_id,
                e.reason_text,
                e.result_ref_json,
                e.failure_code,
                e.created_at
            FROM copilot_action_proposal_events e
            WHERE e.proposal_id = p.id
            ORDER BY e.created_at DESC, e.id DESC
            LIMIT 1
        ) latest ON TRUE
    """


def _get_visible_proposal(
    session: Session,
    principal: CurrentPrincipal,
    proposal_id: UUID,
) -> dict[str, object]:
    row = session.exec(
        text(
            """
            SELECT
                p.id,
                p.run_id,
                p.proposed_by_user_id,
                p.action_type,
                p.target_student_profile_id,
                p.payload_json,
                p.rationale_text,
                p.evidence_citations_json,
                p.created_at
            FROM copilot_action_proposals p
            WHERE p.id = CAST(:proposal_id AS uuid)
              AND p.organization_id = CAST(:organization_id AS uuid)
              AND p.institution_id = CAST(:institution_id AS uuid)
            """
        ),
        params={
            "proposal_id": str(proposal_id),
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
        },
    ).mappings().first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Action proposal not found",
        )
    return dict(row)


def _lock_proposal_lifecycle(session: Session, proposal_id: UUID) -> None:
    session.exec(
        text(
            """
            SELECT pg_advisory_xact_lock(
                hashtextextended(CAST(:proposal_id AS text), 0)
            )
            """
        ),
        params={"proposal_id": str(proposal_id)},
    )


def _latest_event_type(session: Session, proposal_id: UUID) -> str:
    event_type = session.exec(
        text(
            """
            SELECT event_type
            FROM copilot_action_proposal_events
            WHERE proposal_id = CAST(:proposal_id AS uuid)
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ),
        params={"proposal_id": str(proposal_id)},
    ).scalar_one_or_none()

    if event_type is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Action proposal has no lifecycle event",
        )
    return str(event_type)


def _insert_event(
    session: Session,
    principal: CurrentPrincipal,
    *,
    proposal_id: UUID,
    event_type: str,
    reason_text: str | None = None,
    result_ref: dict[str, object] | None = None,
    failure_code: str | None = None,
) -> None:
    if event_type not in ACTION_STATUSES:
        raise ValueError("Unsupported action proposal event")

    session.exec(
        text(
            """
            INSERT INTO copilot_action_proposal_events (
                id,
                organization_id,
                institution_id,
                proposal_id,
                event_type,
                actor_user_id,
                reason_text,
                result_ref_json,
                failure_code,
                created_at
            )
            VALUES (
                CAST(:id AS uuid),
                CAST(:organization_id AS uuid),
                CAST(:institution_id AS uuid),
                CAST(:proposal_id AS uuid),
                :event_type,
                CAST(:actor_user_id AS uuid),
                :reason_text,
                CAST(:result_ref_json AS jsonb),
                :failure_code,
                :created_at
            )
            """
        ),
        params={
            "id": str(uuid4()),
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
            "proposal_id": str(proposal_id),
            "event_type": event_type,
            "actor_user_id": str(principal.user_id),
            "reason_text": reason_text,
            "result_ref_json": (
                None if result_ref is None else _canonical_json(result_ref)
            ),
            "failure_code": failure_code,
            "created_at": utcnow(),
        },
    )


def _read_action_proposal(
    session: Session,
    principal: CurrentPrincipal,
    proposal_id: UUID,
) -> ActionProposalRead:
    row = session.exec(
        text(
            _proposal_read_query()
            + """
            WHERE p.id = CAST(:proposal_id AS uuid)
              AND p.organization_id = CAST(:organization_id AS uuid)
              AND p.institution_id = CAST(:institution_id AS uuid)
            LIMIT 1
            """
        ),
        params={
            "proposal_id": str(proposal_id),
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
        },
    ).mappings().first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Action proposal not found",
        )
    return _row_to_read(row)


def list_action_proposals(
    session: Session,
    principal: CurrentPrincipal,
    *,
    limit: int = 50,
) -> list[ActionProposalRead]:
    require_copilot_use(session, principal)

    rows = session.exec(
        text(
            _proposal_read_query()
            + """
            WHERE p.organization_id = CAST(:organization_id AS uuid)
              AND p.institution_id = CAST(:institution_id AS uuid)
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT :limit
            """
        ),
        params={
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
            "limit": max(1, min(limit, 100)),
        },
    ).mappings().all()

    return [_row_to_read(row) for row in rows]


def create_action_proposal_internal(
    session: Session,
    principal: CurrentPrincipal,
    *,
    run_id: UUID,
    action_type: str,
    payload: dict[str, object],
    rationale: str,
    evidence_citations: list[str],
    commit: bool = True,
) -> ActionProposalRead:
    require_copilot_use(session, principal)

    if action_type != ACTION_TYPE_CREATE_INTERVENTION:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported governed action type",
        )
    if not rationale.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Action proposal rationale is required",
        )

    parsed = InterventionCreate.model_validate(payload)
    canonical_payload = parsed.model_dump(mode="json")
    if parsed.origin_type != "SYSTEM_SUGGESTION":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Governed intervention proposals require SYSTEM_SUGGESTION origin",
        )

    run = session.exec(
        text(
            """
            SELECT
                cr.target_student_profile_id,
                cao.evidence_assessment,
                cao.citations_json
            FROM copilot_runs cr
            JOIN copilot_advisory_outputs cao
              ON cao.run_id = cr.id
             AND cao.organization_id = cr.organization_id
             AND cao.institution_id = cr.institution_id
            WHERE cr.id = CAST(:run_id AS uuid)
              AND cr.organization_id = CAST(:organization_id AS uuid)
              AND cr.institution_id = CAST(:institution_id AS uuid)
              AND cr.actor_user_id = CAST(:actor_user_id AS uuid)
            LIMIT 1
            """
        ),
        params={
            "run_id": str(run_id),
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
            "actor_user_id": str(principal.user_id),
        },
    ).mappings().first()

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Copilot run not found in proposal scope",
        )
    if str(run["evidence_assessment"]) != "SUFFICIENT":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Action proposal requires sufficient governed evidence",
        )

    target_student_profile_id = run["target_student_profile_id"]
    if target_student_profile_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Action proposal requires a student-targeted run",
        )
    if target_student_profile_id != parsed.student_profile_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Action proposal cannot widen student scope",
        )

    output_citations = {str(value) for value in (run["citations_json"] or [])}
    proposal_citations = {str(value) for value in evidence_citations}
    if (
        not proposal_citations
        or not proposal_citations.issubset(output_citations)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Action proposal citations must be backed by advisory evidence",
        )

    proposal_id = uuid4()
    now = utcnow()

    session.exec(
        text(
            """
            INSERT INTO copilot_action_proposals (
                id,
                organization_id,
                institution_id,
                run_id,
                proposed_by_user_id,
                action_type,
                target_student_profile_id,
                payload_json,
                payload_sha256,
                rationale_text,
                evidence_citations_json,
                created_at
            )
            VALUES (
                CAST(:id AS uuid),
                CAST(:organization_id AS uuid),
                CAST(:institution_id AS uuid),
                CAST(:run_id AS uuid),
                CAST(:proposed_by_user_id AS uuid),
                :action_type,
                CAST(:target_student_profile_id AS uuid),
                CAST(:payload_json AS jsonb),
                :payload_sha256,
                :rationale_text,
                CAST(:evidence_citations_json AS jsonb),
                :created_at
            )
            """
        ),
        params={
            "id": str(proposal_id),
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
            "run_id": str(run_id),
            "proposed_by_user_id": str(principal.user_id),
            "action_type": action_type,
            "target_student_profile_id": str(parsed.student_profile_id),
            "payload_json": _canonical_json(canonical_payload),
            "payload_sha256": _payload_sha256(canonical_payload),
            "rationale_text": rationale.strip(),
            "evidence_citations_json": _canonical_json(sorted(proposal_citations)),
            "created_at": now,
        },
    )

    _insert_event(
        session,
        principal,
        proposal_id=proposal_id,
        event_type="PROPOSED",
        reason_text=rationale.strip(),
    )

    if commit:
        session.commit()
    else:
        session.flush()

    return _read_action_proposal(session, principal, proposal_id)


def approve_action_proposal(
    session: Session,
    principal: CurrentPrincipal,
    *,
    proposal_id: UUID,
    note: str | None = None,
) -> ActionProposalRead:
    require_copilot_action_approve(session, principal)

    proposal = _get_visible_proposal(
        session,
        principal,
        proposal_id,
    )
    _lock_proposal_lifecycle(session, proposal_id)
    latest = _latest_event_type(session, proposal_id)
    if latest != "PROPOSED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Action proposal cannot be approved from {latest}",
        )

    _insert_event(
        session,
        principal,
        proposal_id=proposal_id,
        event_type="APPROVED",
        reason_text=None if note is None else note.strip() or None,
    )
    session.commit()

    try:
        if proposal["action_type"] != ACTION_TYPE_CREATE_INTERVENTION:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Unsupported governed action type",
            )
        payload = InterventionCreate.model_validate(proposal["payload_json"])
        result = create_intervention(
            session,
            principal,
            payload,
            commit=False,
        )
        _insert_event(
            session,
            principal,
            proposal_id=proposal_id,
            event_type="EXECUTED",
            result_ref={"intervention_id": str(result.id)},
        )
        session.commit()
    except HTTPException as exc:
        session.rollback()
        _insert_event(
            session,
            principal,
            proposal_id=proposal_id,
            event_type="FAILED",
            reason_text="Authoritative domain service rejected execution",
            failure_code=f"DOMAIN_HTTP_{exc.status_code}",
        )
        session.commit()
    except Exception:
        session.rollback()
        _insert_event(
            session,
            principal,
            proposal_id=proposal_id,
            event_type="FAILED",
            reason_text="Authoritative domain execution failed",
            failure_code="DOMAIN_EXECUTION_FAILED",
        )
        session.commit()

    return _read_action_proposal(session, principal, proposal_id)


def reject_action_proposal(
    session: Session,
    principal: CurrentPrincipal,
    *,
    proposal_id: UUID,
    reason: str,
) -> ActionProposalRead:
    require_copilot_action_approve(session, principal)

    _get_visible_proposal(
        session,
        principal,
        proposal_id,
    )
    _lock_proposal_lifecycle(session, proposal_id)
    latest = _latest_event_type(session, proposal_id)
    if latest != "PROPOSED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Action proposal cannot be rejected from {latest}",
        )

    _insert_event(
        session,
        principal,
        proposal_id=proposal_id,
        event_type="REJECTED",
        reason_text=reason.strip(),
    )
    session.commit()

    return _read_action_proposal(session, principal, proposal_id)
