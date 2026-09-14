from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.events.service import enqueue_canonical_event
from app.modules.interventions.institutional_views import (
    action_read_for_principal,
    followup_read_for_principal,
    intervention_read_for_principal,
)
from app.modules.interventions.models import (
    Intervention,
    InterventionAction,
    InterventionFollowUp,
)
from app.modules.interventions.schemas import (
    InterventionActionAssign,
    InterventionActionComplete,
    InterventionActionCreate,
    InterventionActionTransition,
    InterventionAssign,
    InterventionCancel,
    InterventionClose,
    InterventionCreate,
    InterventionFollowUpCreate,
    InterventionResolve,
    InterventionTransition,
)
from app.modules.m21_access import require_student_scope

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "OPEN": frozenset({"IN_PROGRESS"}),
    "IN_PROGRESS": frozenset({"MONITORING"}),
    "MONITORING": frozenset({"IN_PROGRESS"}),
    "RESOLVED": frozenset({"IN_PROGRESS", "MONITORING"}),
    "CLOSED": frozenset(),
    "CANCELLED": frozenset(),
}

_TERMINAL_STATES = {"CLOSED", "CANCELLED"}

_ACTION_TRANSITIONS: dict[str, frozenset[str]] = {
    "OPEN": frozenset({"ACKNOWLEDGED", "IN_PROGRESS", "CANCELLED"}),
    "ACKNOWLEDGED": frozenset({"IN_PROGRESS", "CANCELLED"}),
    "IN_PROGRESS": frozenset({"CANCELLED"}),
    "COMPLETED": frozenset(),
    "CANCELLED": frozenset(),
    "OVERDUE": frozenset({"ACKNOWLEDGED", "IN_PROGRESS", "CANCELLED"}),
}

_ACTION_TERMINAL_STATES = {"COMPLETED", "CANCELLED"}


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


def _assert_no_active_actions(
    session: Session,
    intervention_id: UUID,
    *,
    operation: str,
) -> None:
    row = session.exec(
        text(
            """
            SELECT COUNT(*)
            FROM intervention_actions
            WHERE intervention_id = CAST(:intervention_id AS uuid)
              AND status IN ('OPEN','ACKNOWLEDGED','IN_PROGRESS','OVERDUE')
            """
        ),
        params={"intervention_id": str(intervention_id)},
    ).one()
    active_count = int(row[0])
    if active_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot {operation} intervention while "
                f"{active_count} active action(s) remain"
            ),
        )


def _assert_close_outcome_consistent(
    entity: Intervention,
    payload: InterventionClose,
) -> None:
    if (
        entity.outcome_type is None
        or entity.outcome_summary is None
        or entity.outcome_recorded_at is None
        or entity.outcome_recorded_by_user_id is None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RESOLVED intervention is missing a recorded outcome",
        )

    if (
        payload.outcome_type != entity.outcome_type
        or payload.outcome_summary != entity.outcome_summary
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Close outcome must match the outcome recorded "
                "when the intervention was resolved"
            ),
        )


def get_intervention(
    session: Session,
    principal: CurrentPrincipal,
    intervention_id: UUID,
) -> Intervention:
    _require_permission(session, principal, "intervention.read")
    entity = _get_intervention(session, principal, intervention_id)
    require_student_scope(
        session,
        principal,
        entity.student_profile_id,
        permission_key="intervention.read",
    )
    return intervention_read_for_principal(
        session,
        principal,
        entity,
    )


def list_student_interventions(
    session: Session,
    principal: CurrentPrincipal,
    *,
    student_profile_id: UUID,
    limit: int = 50,
    status_filter: str | None = None,
    sensitivity_filter: str | None = None,
) -> list[Intervention]:
    _require_permission(session, principal, "intervention.read")
    require_student_scope(
        session,
        principal,
        student_profile_id,
        permission_key="intervention.read",
    )
    statement = (
        select(Intervention)
        .where(Intervention.student_profile_id == student_profile_id)
        .order_by(Intervention.opened_at.desc(), Intervention.id.desc())
        .limit(max(1, min(limit, 100)))
    )
    if status_filter is not None:
        statement = statement.where(Intervention.status == status_filter)
    if sensitivity_filter is not None:
        statement = statement.where(Intervention.sensitivity == sensitivity_filter)
    entities = list(session.exec(statement).all())
    return [
        intervention_read_for_principal(session, principal, entity)
        for entity in entities
    ]


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
    event_type = "student.intervention.status_changed"
    if previous_status == "RESOLVED":
        entity.resolved_at = None
        entity.closed_at = None
        entity.outcome_type = None
        entity.outcome_summary = None
        entity.outcome_recorded_at = None
        entity.outcome_recorded_by_user_id = None
        event_type = "student.intervention.reopened"
    entity.updated_at = utcnow()
    session.add(entity)
    _emit(
        session,
        principal,
        entity,
        event_type,
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

    _assert_no_active_actions(
        session,
        entity.id,
        operation="resolve",
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

    _assert_no_active_actions(
        session,
        entity.id,
        operation="close",
    )
    _assert_close_outcome_consistent(entity, payload)

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


def _ensure_intervention_operational(entity: Intervention) -> None:
    if entity.status in _TERMINAL_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Intervention in terminal state {entity.status} "
                "cannot receive actions or follow-ups"
            ),
        )


def _get_action(
    session: Session,
    principal: CurrentPrincipal,
    action_id: UUID,
) -> InterventionAction:
    action = session.get(InterventionAction, action_id)
    if action is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intervention action not found in authorized scope",
        )
    if (
        action.organization_id != principal.organization_id
        or action.institution_id != principal.institution_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intervention action not found in authorized scope",
        )
    return action


def _parent_for_action(
    session: Session,
    principal: CurrentPrincipal,
    action: InterventionAction,
) -> Intervention:
    return _get_intervention(session, principal, action.intervention_id)


def _safe_action_event_payload(
    parent: Intervention,
    action: InterventionAction,
) -> dict[str, object]:
    return {
        "student_profile_id": str(parent.student_profile_id),
        "intervention_id": str(parent.id),
        "action_id": str(action.id),
        "action_type": action.action_type,
        "status": action.status,
        "sensitivity": parent.sensitivity,
        "severity": parent.severity,
        "assigned_role_code": action.assigned_role_code,
        "assigned_user_id": (
            str(action.assigned_user_id) if action.assigned_user_id else None
        ),
        "due_at": action.due_at.isoformat() if action.due_at else None,
    }


def _emit_action_event(
    session: Session,
    principal: CurrentPrincipal,
    parent: Intervention,
    action: InterventionAction,
    event_type: str,
    *,
    extra: dict[str, object] | None = None,
) -> None:
    payload = _safe_action_event_payload(parent, action)
    if extra:
        payload.update(extra)

    enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type=event_type,
        event_version=1,
        aggregate_type="intervention_action",
        aggregate_id=action.id,
        actor_user_id=principal.user_id,
        payload=payload,
        metadata={"human_authorized": True},
    )


def _emit_followup_event(
    session: Session,
    principal: CurrentPrincipal,
    parent: Intervention,
    followup: InterventionFollowUp,
) -> None:
    enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type="student.intervention.followup_recorded",
        event_version=1,
        aggregate_type="intervention_followup",
        aggregate_id=followup.id,
        actor_user_id=principal.user_id,
        payload={
            "student_profile_id": str(parent.student_profile_id),
            "intervention_id": str(parent.id),
            "followup_id": str(followup.id),
            "followup_type": followup.followup_type,
            "sensitivity": followup.sensitivity,
            "severity": parent.severity,
            "observed_at": followup.observed_at.isoformat(),
        },
        metadata={"human_authorized": True},
    )


def _validate_action_transition(current: str, target: str) -> None:
    if current in _ACTION_TERMINAL_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Action in terminal state {current} cannot transition",
        )
    allowed = _ACTION_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid action transition: {current} -> {target}",
        )


def create_intervention_action(
    session: Session,
    principal: CurrentPrincipal,
    intervention_id: UUID,
    payload: InterventionActionCreate,
) -> InterventionAction:
    _require_permission(session, principal, "intervention.action.manage")
    parent = _get_intervention(session, principal, intervention_id)
    _ensure_intervention_operational(parent)
    _assert_assignee(session, principal, payload.assigned_user_id)

    now = utcnow()
    action = InterventionAction(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        intervention_id=parent.id,
        action_type=payload.action_type,
        title=payload.title,
        description=payload.description,
        status="OPEN",
        assigned_role_code=payload.assigned_role_code,
        assigned_user_id=payload.assigned_user_id,
        due_at=payload.due_at,
        created_by_user_id=principal.user_id,
        created_at=now,
        updated_at=now,
    )
    session.add(action)
    _emit_action_event(
        session,
        principal,
        parent,
        action,
        "student.intervention.action_created",
    )
    session.commit()
    session.refresh(action)
    return action


def assign_intervention_action(
    session: Session,
    principal: CurrentPrincipal,
    action_id: UUID,
    payload: InterventionActionAssign,
) -> InterventionAction:
    _require_permission(session, principal, "intervention.action.manage")
    action = _get_action(session, principal, action_id)
    parent = _parent_for_action(session, principal, action)
    _ensure_intervention_operational(parent)
    if action.status in _ACTION_TERMINAL_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot assign action in terminal state {action.status}",
        )
    _assert_assignee(session, principal, payload.assigned_user_id)

    action.assigned_role_code = payload.assigned_role_code
    action.assigned_user_id = payload.assigned_user_id
    action.due_at = payload.due_at
    action.updated_at = utcnow()
    session.add(action)
    _emit_action_event(
        session,
        principal,
        parent,
        action,
        "student.intervention.action_assigned",
    )
    session.commit()
    session.refresh(action)
    return action


def transition_intervention_action(
    session: Session,
    principal: CurrentPrincipal,
    action_id: UUID,
    payload: InterventionActionTransition,
) -> InterventionAction:
    _require_permission(session, principal, "intervention.action.manage")
    action = _get_action(session, principal, action_id)
    parent = _parent_for_action(session, principal, action)
    _ensure_intervention_operational(parent)

    previous_status = action.status
    _validate_action_transition(previous_status, payload.status)
    now = utcnow()
    action.status = payload.status
    if payload.status == "ACKNOWLEDGED":
        action.acknowledged_at = now
    elif payload.status == "IN_PROGRESS":
        if action.acknowledged_at is None:
            action.acknowledged_at = now
        action.started_at = now

    action.updated_at = now
    session.add(action)
    event_type = {
        "ACKNOWLEDGED": "student.intervention.action_acknowledged",
        "IN_PROGRESS": "student.intervention.action_started",
        "CANCELLED": "student.intervention.action_cancelled",
    }[payload.status]
    _emit_action_event(
        session,
        principal,
        parent,
        action,
        event_type,
        extra={"previous_status": previous_status},
    )
    session.commit()
    session.refresh(action)
    return action


def complete_intervention_action(
    session: Session,
    principal: CurrentPrincipal,
    action_id: UUID,
    payload: InterventionActionComplete,
) -> InterventionAction:
    _require_permission(session, principal, "intervention.action.manage")
    action = _get_action(session, principal, action_id)
    parent = _parent_for_action(session, principal, action)
    _ensure_intervention_operational(parent)

    if action.status not in {"ACKNOWLEDGED", "IN_PROGRESS", "OVERDUE"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot complete action from state {action.status}",
        )

    now = utcnow()
    previous_status = action.status
    action.status = "COMPLETED"
    action.completed_at = now
    action.completed_by_user_id = principal.user_id
    action.completion_note = payload.completion_note
    action.updated_at = now
    session.add(action)
    _emit_action_event(
        session,
        principal,
        parent,
        action,
        "student.intervention.action_completed",
        extra={
            "previous_status": previous_status,
            "completion_note_recorded": bool(payload.completion_note),
        },
    )
    session.commit()
    session.refresh(action)
    return action


def create_intervention_followup(
    session: Session,
    principal: CurrentPrincipal,
    intervention_id: UUID,
    payload: InterventionFollowUpCreate,
) -> InterventionFollowUp:
    _require_permission(session, principal, "intervention.followup.create")
    parent = _get_intervention(session, principal, intervention_id)
    _ensure_intervention_operational(parent)

    if parent.sensitivity == "CONFIDENTIAL" and payload.sensitivity != "CONFIDENTIAL":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Follow-up sensitivity cannot be lower than "
                "a CONFIDENTIAL intervention"
            ),
        )
    if parent.sensitivity == "RESTRICTED" and payload.sensitivity == "GENERAL":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Follow-up sensitivity cannot be lower than "
                "a RESTRICTED intervention"
            ),
        )

    followup = InterventionFollowUp(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        intervention_id=parent.id,
        followup_type=payload.followup_type,
        sensitivity=payload.sensitivity,
        note=payload.note,
        observed_at=payload.observed_at,
        created_by_user_id=principal.user_id,
        created_at=utcnow(),
    )
    session.add(followup)
    _emit_followup_event(session, principal, parent, followup)
    session.commit()
    session.refresh(followup)
    return followup

def get_intervention_action(
    session: Session,
    principal: CurrentPrincipal,
    action_id: UUID,
) -> InterventionAction:
    _require_permission(session, principal, "intervention.read")
    action = _get_action(session, principal, action_id)
    parent = _parent_for_action(session, principal, action)
    require_student_scope(
        session,
        principal,
        parent.student_profile_id,
        permission_key="intervention.read",
    )
    return action_read_for_principal(
        session,
        principal,
        action,
        parent_sensitivity=parent.sensitivity,
    )


def list_intervention_actions(
    session: Session,
    principal: CurrentPrincipal,
    *,
    intervention_id: UUID,
    limit: int = 50,
    status_filter: str | None = None,
) -> list[InterventionAction]:
    _require_permission(session, principal, "intervention.read")
    parent = _get_intervention(session, principal, intervention_id)
    require_student_scope(
        session,
        principal,
        parent.student_profile_id,
        permission_key="intervention.read",
    )

    statement = (
        select(InterventionAction)
        .where(InterventionAction.intervention_id == intervention_id)
        .order_by(
            InterventionAction.created_at.desc(),
            InterventionAction.id.desc(),
        )
        .limit(max(1, min(limit, 100)))
    )
    if status_filter is not None:
        statement = statement.where(
            InterventionAction.status == status_filter
        )
    actions = list(session.exec(statement).all())
    return [
        action_read_for_principal(
            session,
            principal,
            action,
            parent_sensitivity=parent.sensitivity,
        )
        for action in actions
    ]


def _get_followup(
    session: Session,
    principal: CurrentPrincipal,
    followup_id: UUID,
) -> InterventionFollowUp:
    followup = session.get(InterventionFollowUp, followup_id)
    if followup is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intervention follow-up not found in authorized scope",
        )
    if (
        followup.organization_id != principal.organization_id
        or followup.institution_id != principal.institution_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intervention follow-up not found in authorized scope",
        )
    return followup


def get_intervention_followup(
    session: Session,
    principal: CurrentPrincipal,
    followup_id: UUID,
) -> InterventionFollowUp:
    _require_permission(session, principal, "intervention.read")
    followup = _get_followup(session, principal, followup_id)
    parent = _get_intervention(
        session,
        principal,
        followup.intervention_id,
    )
    require_student_scope(
        session,
        principal,
        parent.student_profile_id,
        permission_key="intervention.read",
    )
    return followup_read_for_principal(
        session,
        principal,
        followup,
    )


def list_intervention_followups(
    session: Session,
    principal: CurrentPrincipal,
    *,
    intervention_id: UUID,
    limit: int = 50,
    sensitivity_filter: str | None = None,
) -> list[InterventionFollowUp]:
    _require_permission(session, principal, "intervention.read")
    parent = _get_intervention(session, principal, intervention_id)
    require_student_scope(
        session,
        principal,
        parent.student_profile_id,
        permission_key="intervention.read",
    )

    statement = (
        select(InterventionFollowUp)
        .where(InterventionFollowUp.intervention_id == intervention_id)
        .order_by(
            InterventionFollowUp.observed_at.desc(),
            InterventionFollowUp.id.desc(),
        )
        .limit(max(1, min(limit, 100)))
    )
    if sensitivity_filter is not None:
        statement = statement.where(
            InterventionFollowUp.sensitivity == sensitivity_filter
        )
    followups = list(session.exec(statement).all())
    return [
        followup_read_for_principal(
            session,
            principal,
            followup,
        )
        for followup in followups
    ]
