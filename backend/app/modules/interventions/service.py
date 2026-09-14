from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.events.service import enqueue_canonical_event
from app.modules.interventions.models import Intervention
from app.modules.interventions.schemas import (
    InterventionAssign,
    InterventionCancel,
    InterventionClose,
    InterventionCreate,
    InterventionResolve,
    InterventionTransition,
)

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "OPEN": frozenset({"IN_PROGRESS"}),
    "IN_PROGRESS": frozenset({"MONITORING"}),
    "MONITORING": frozenset({"IN_PROGRESS"}),
    "RESOLVED": frozenset({"IN_PROGRESS", "MONITORING"}),
    "CLOSED": frozenset(),
    "CANCELLED": frozenset(),
}

_TERMINAL_STATES = {"CLOSED", "CANCELLED"}


def utcnow() -> datetime:
    return datetime.now(UTC)


def _require_permission(
    session: Session,
    principal: CurrentPrincipal,
    permission_key: str,
) -> None:
    row = session.exec(
        text(
            """
            SELECT 1
            FROM memberships m
            JOIN membership_roles mr ON mr.membership_id = m.id
            JOIN role_permissions rp ON rp.role_id = mr.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE m.user_id = CAST(:user_id AS uuid)
              AND m.institution_id = CAST(:institution_id AS uuid)
              AND m.status = 'ACTIVE'
              AND p.key IN (:permission_key, 'intervention.admin')
            LIMIT 1
            """
        ),
        params={
            "user_id": str(principal.user_id),
            "institution_id": str(principal.institution_id),
            "permission_key": permission_key,
        },
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {permission_key}",
        )


def _get_intervention(
    session: Session,
    principal: CurrentPrincipal,
    intervention_id: UUID,
) -> Intervention:
    entity = session.get(Intervention, intervention_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intervention not found in authorized scope",
        )
    if (
        entity.organization_id != principal.organization_id
        or entity.institution_id != principal.institution_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intervention not found in authorized scope",
        )
    return entity


def _assert_student_in_tenant(
    session: Session,
    principal: CurrentPrincipal,
    student_profile_id: UUID,
) -> None:
    row = session.exec(
        text(
            """
            SELECT 1
            FROM student_profiles
            WHERE id = CAST(:student_profile_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
            """
        ),
        params={
            "student_profile_id": str(student_profile_id),
            "institution_id": str(principal.institution_id),
        },
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found in current institution",
        )


def _assert_optional_context_in_tenant(
    session: Session,
    principal: CurrentPrincipal,
    *,
    academic_period_id: UUID | None,
    section_id: UUID | None,
) -> None:
    if academic_period_id is not None:
        row = session.exec(
            text(
                """
                SELECT 1
                FROM academic_periods
                WHERE id = CAST(:id AS uuid)
                  AND institution_id = CAST(:institution_id AS uuid)
                """
            ),
            params={
                "id": str(academic_period_id),
                "institution_id": str(principal.institution_id),
            },
        ).first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Academic period not found in current institution",
            )

    if section_id is not None:
        row = session.exec(
            text(
                """
                SELECT 1
                FROM sections
                WHERE id = CAST(:id AS uuid)
                  AND institution_id = CAST(:institution_id AS uuid)
                """
            ),
            params={
                "id": str(section_id),
                "institution_id": str(principal.institution_id),
            },
        ).first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Section not found in current institution",
            )


def _assert_assignee(
    session: Session,
    principal: CurrentPrincipal,
    assigned_user_id: UUID | None,
) -> None:
    if assigned_user_id is None:
        return

    row = session.exec(
        text(
            """
            SELECT 1
            FROM memberships
            WHERE user_id = CAST(:user_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND status = 'ACTIVE'
            """
        ),
        params={
            "user_id": str(assigned_user_id),
            "institution_id": str(principal.institution_id),
        },
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assigned user must have an active membership in this institution",
        )


def _safe_event_payload(entity: Intervention) -> dict[str, object]:
    return {
        "student_profile_id": str(entity.student_profile_id),
        "intervention_id": str(entity.id),
        "intervention_type": entity.intervention_type,
        "status": entity.status,
        "severity": entity.severity,
        "sensitivity": entity.sensitivity,
        "origin_type": entity.origin_type,
        "assigned_role_code": entity.assigned_role_code,
        "assigned_user_id": (
            str(entity.assigned_user_id) if entity.assigned_user_id else None
        ),
        "academic_period_id": (
            str(entity.academic_period_id) if entity.academic_period_id else None
        ),
        "section_id": str(entity.section_id) if entity.section_id else None,
        "target_at": entity.target_at.isoformat() if entity.target_at else None,
        "outcome_type": entity.outcome_type,
    }


def _emit(
    session: Session,
    principal: CurrentPrincipal,
    entity: Intervention,
    event_type: str,
    *,
    extra: dict[str, object] | None = None,
) -> None:
    payload = _safe_event_payload(entity)
    if extra:
        payload.update(extra)

    enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type=event_type,
        event_version=1,
        aggregate_type="intervention",
        aggregate_id=entity.id,
        actor_user_id=principal.user_id,
        payload=payload,
        metadata={"human_authorized": True},
    )


def _validate_transition(current: str, target: str) -> None:
    if current in _TERMINAL_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Intervention in terminal state {current} cannot transition",
        )
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid intervention transition: {current} -> {target}",
        )


def create_intervention(
    session: Session,
    principal: CurrentPrincipal,
    payload: InterventionCreate,
) -> Intervention:
    _require_permission(session, principal, "intervention.create")
    _assert_student_in_tenant(session, principal, payload.student_profile_id)
    _assert_optional_context_in_tenant(
        session,
        principal,
        academic_period_id=payload.academic_period_id,
        section_id=payload.section_id,
    )
    _assert_assignee(session, principal, payload.assigned_user_id)

    now = utcnow()
    entity = Intervention(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        student_profile_id=payload.student_profile_id,
        academic_period_id=payload.academic_period_id,
        section_id=payload.section_id,
        intervention_type=payload.intervention_type,
        severity=payload.severity,
        status="OPEN",
        sensitivity=payload.sensitivity,
        title=payload.title,
        reason=payload.reason,
        objective=payload.objective,
        origin_type=payload.origin_type,
        opened_by_user_id=principal.user_id,
        assigned_role_code=payload.assigned_role_code,
        assigned_user_id=payload.assigned_user_id,
        opened_at=now,
        target_at=payload.target_at,
        created_at=now,
        updated_at=now,
    )
    session.add(entity)
    _emit(session, principal, entity, "student.intervention.opened")
    session.commit()
    session.refresh(entity)
    return entity


def assign_intervention(
    session: Session,
    principal: CurrentPrincipal,
    intervention_id: UUID,
    payload: InterventionAssign,
) -> Intervention:
    _require_permission(session, principal, "intervention.assign")
    entity = _get_intervention(session, principal, intervention_id)
    if entity.status in _TERMINAL_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot assign intervention in terminal state {entity.status}",
        )
    _assert_assignee(session, principal, payload.assigned_user_id)

    entity.assigned_role_code = payload.assigned_role_code
    entity.assigned_user_id = payload.assigned_user_id
    entity.target_at = payload.target_at
    entity.updated_at = utcnow()
    session.add(entity)
    _emit(session, principal, entity, "student.intervention.assigned")
    session.commit()
    session.refresh(entity)
    return entity


def transition_intervention(
    session: Session,
    principal: CurrentPrincipal,
    intervention_id: UUID,
    payload: InterventionTransition,
) -> Intervention:
    _require_permission(session, principal, "intervention.update")
    entity = _get_intervention(session, principal, intervention_id)
    previous_status = entity.status
    _validate_transition(previous_status, payload.status)

    entity.status = payload.status
    if previous_status == "RESOLVED":
        entity.resolved_at = None
        entity.outcome_type = None
        entity.outcome_summary = None
        entity.outcome_recorded_at = None
        entity.outcome_recorded_by_user_id = None
    entity.updated_at = utcnow()
    session.add(entity)
    _emit(
        session,
        principal,
        entity,
        "student.intervention.status_changed",
        extra={"previous_status": previous_status},
    )
    session.commit()
    session.refresh(entity)
    return entity


def resolve_intervention(
    session: Session,
    principal: CurrentPrincipal,
    intervention_id: UUID,
    payload: InterventionResolve,
) -> Intervention:
    _require_permission(session, principal, "intervention.resolve")
    entity = _get_intervention(session, principal, intervention_id)
    if entity.status not in {"IN_PROGRESS", "MONITORING"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot resolve intervention from state {entity.status}",
        )

    now = utcnow()
    previous_status = entity.status
    entity.status = "RESOLVED"
    entity.resolved_at = now
    entity.outcome_type = payload.outcome_type
    entity.outcome_summary = payload.outcome_summary
    entity.outcome_recorded_at = now
    entity.outcome_recorded_by_user_id = principal.user_id
    entity.updated_at = now
    session.add(entity)
    _emit(
        session,
        principal,
        entity,
        "student.intervention.resolved",
        extra={"previous_status": previous_status},
    )
    session.commit()
    session.refresh(entity)
    return entity


def close_intervention(
    session: Session,
    principal: CurrentPrincipal,
    intervention_id: UUID,
    payload: InterventionClose,
) -> Intervention:
    _require_permission(session, principal, "intervention.close")
    entity = _get_intervention(session, principal, intervention_id)
    if entity.status != "RESOLVED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only RESOLVED interventions may be closed",
        )

    now = utcnow()
    entity.status = "CLOSED"
    entity.closed_at = now
    entity.outcome_type = payload.outcome_type
    entity.outcome_summary = payload.outcome_summary
    entity.outcome_recorded_at = now
    entity.outcome_recorded_by_user_id = principal.user_id
    entity.updated_at = now
    session.add(entity)
    _emit(
        session,
        principal,
        entity,
        "student.intervention.closed",
        extra={"previous_status": "RESOLVED"},
    )
    session.commit()
    session.refresh(entity)
    return entity


def cancel_intervention(
    session: Session,
    principal: CurrentPrincipal,
    intervention_id: UUID,
    payload: InterventionCancel,
) -> Intervention:
    _require_permission(session, principal, "intervention.update")
    entity = _get_intervention(session, principal, intervention_id)
    if entity.status in _TERMINAL_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel intervention in terminal state {entity.status}",
        )

    previous_status = entity.status
    entity.status = "CANCELLED"
    entity.updated_at = utcnow()
    session.add(entity)
    _emit(
        session,
        principal,
        entity,
        "student.intervention.cancelled",
        extra={
            "previous_status": previous_status,
            "cancellation_reason_recorded": True,
        },
    )
    session.commit()
    session.refresh(entity)
    return entity