from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.events.service import enqueue_canonical_event
from app.modules.interventions.models import (
    Intervention,
    InterventionSuggestion,
    InterventionSuggestionEvidence,
)
from app.modules.interventions.schemas import (
    InterventionSuggestionAccept,
    InterventionSuggestionDismiss,
    InterventionSuggestionEvidenceRead,
    InterventionSuggestionRead,
)


def _require_suggestion_permission(
    session: Session,
    principal: CurrentPrincipal,
    permission_key: str,
) -> None:
    allowed = session.exec(
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

    if allowed is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {permission_key}",
        )


def _suggestion_read(
    session: Session,
    suggestion: InterventionSuggestion,
) -> InterventionSuggestionRead:
    evidence = list(
        session.exec(
            select(InterventionSuggestionEvidence)
            .where(
                InterventionSuggestionEvidence.suggestion_id
                == suggestion.id
            )
            .order_by(
                InterventionSuggestionEvidence.created_at,
                InterventionSuggestionEvidence.id,
            )
        ).all()
    )
    return InterventionSuggestionRead.model_validate(
        suggestion,
        from_attributes=True,
    ).model_copy(
        update={
            "evidence": [
                InterventionSuggestionEvidenceRead.model_validate(
                    item,
                    from_attributes=True,
                )
                for item in evidence
            ]
        }
    )


def get_intervention_suggestion(
    session: Session,
    principal: CurrentPrincipal,
    suggestion_id: UUID,
) -> InterventionSuggestionRead:
    _require_suggestion_permission(
        session,
        principal,
        "intervention.suggestion.read",
    )

    suggestion = session.exec(
        select(InterventionSuggestion).where(
            InterventionSuggestion.id == suggestion_id
        )
    ).first()

    if suggestion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intervention suggestion not found",
        )

    return _suggestion_read(session, suggestion)


def list_intervention_suggestions(
    session: Session,
    principal: CurrentPrincipal,
    *,
    limit: int = 50,
    status_filter: str | None = None,
    severity_filter: str | None = None,
    sensitivity_filter: str | None = None,
    student_profile_id: UUID | None = None,
) -> list[InterventionSuggestionRead]:
    _require_suggestion_permission(
        session,
        principal,
        "intervention.suggestion.read",
    )

    statement = select(InterventionSuggestion)

    if status_filter is not None:
        statement = statement.where(
            InterventionSuggestion.status == status_filter
        )
    if severity_filter is not None:
        statement = statement.where(
            InterventionSuggestion.severity == severity_filter
        )
    if sensitivity_filter is not None:
        statement = statement.where(
            InterventionSuggestion.sensitivity == sensitivity_filter
        )
    if student_profile_id is not None:
        statement = statement.where(
            InterventionSuggestion.student_profile_id
            == student_profile_id
        )

    statement = statement.order_by(
        InterventionSuggestion.generated_at.desc(),
        InterventionSuggestion.id,
    ).limit(max(1, min(limit, 100)))

    suggestions = list(session.exec(statement).all())
    return [
        _suggestion_read(session, suggestion)
        for suggestion in suggestions
    ]


def _emit_suggestion_review_event(
    session: Session,
    principal: CurrentPrincipal,
    suggestion: InterventionSuggestion,
    *,
    event_type: str,
) -> None:
    enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type=event_type,
        event_version=1,
        aggregate_type="intervention_suggestion",
        aggregate_id=suggestion.id,
        actor_user_id=principal.user_id,
        payload={
            "student_profile_id": str(suggestion.student_profile_id),
            "suggestion_id": str(suggestion.id),
            "rule_key": suggestion.rule_key,
            "rule_version": suggestion.rule_version,
            "status": suggestion.status,
            "severity": suggestion.severity,
            "sensitivity": suggestion.sensitivity,
            "accepted_intervention_id": (
                str(suggestion.accepted_intervention_id)
                if suggestion.accepted_intervention_id
                else None
            ),
        },
        metadata={"human_authorized": True},
    )


def _get_pending_suggestion_for_review(
    session: Session,
    suggestion_id: UUID,
) -> InterventionSuggestion:
    suggestion = session.exec(
        select(InterventionSuggestion)
        .where(InterventionSuggestion.id == suggestion_id)
        .with_for_update()
    ).first()

    if suggestion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intervention suggestion not found",
        )

    if suggestion.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Intervention suggestion has already been reviewed "
                f"or expired: {suggestion.status}"
            ),
        )

    return suggestion


def _emit_intervention_opened_from_suggestion(
    session: Session,
    principal: CurrentPrincipal,
    intervention: Intervention,
    suggestion: InterventionSuggestion,
) -> None:
    enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type="student.intervention.opened",
        event_version=1,
        aggregate_type="intervention",
        aggregate_id=intervention.id,
        actor_user_id=principal.user_id,
        payload={
            "student_profile_id": str(intervention.student_profile_id),
            "intervention_id": str(intervention.id),
            "intervention_type": intervention.intervention_type,
            "status": intervention.status,
            "severity": intervention.severity,
            "sensitivity": intervention.sensitivity,
            "origin_type": intervention.origin_type,
            "suggestion_id": str(suggestion.id),
            "academic_period_id": (
                str(intervention.academic_period_id)
                if intervention.academic_period_id
                else None
            ),
            "section_id": (
                str(intervention.section_id)
                if intervention.section_id
                else None
            ),
        },
        metadata={"human_authorized": True},
    )


def accept_intervention_suggestion(
    session: Session,
    principal: CurrentPrincipal,
    suggestion_id: UUID,
    payload: InterventionSuggestionAccept,
) -> InterventionSuggestionRead:
    _require_suggestion_permission(
        session,
        principal,
        "intervention.suggestion.review",
    )
    _require_suggestion_permission(
        session,
        principal,
        "intervention.create",
    )

    suggestion = _get_pending_suggestion_for_review(
        session,
        suggestion_id,
    )
    now = datetime.now(UTC)

    intervention = Intervention(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        student_profile_id=suggestion.student_profile_id,
        academic_period_id=suggestion.academic_period_id,
        section_id=suggestion.section_id,
        intervention_type=suggestion.recommended_intervention_type,
        severity=suggestion.severity,
        status="OPEN",
        sensitivity=suggestion.sensitivity,
        title=suggestion.title,
        reason=suggestion.rationale_summary,
        objective=None,
        origin_type="SYSTEM_SUGGESTION",
        opened_by_user_id=principal.user_id,
        opened_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(intervention)
    session.flush()

    suggestion.status = "ACCEPTED"
    suggestion.reviewed_at = now
    suggestion.reviewed_by_user_id = principal.user_id
    suggestion.review_note = payload.review_note
    suggestion.accepted_intervention_id = intervention.id
    suggestion.updated_at = now
    session.add(suggestion)

    _emit_intervention_opened_from_suggestion(
        session,
        principal,
        intervention,
        suggestion,
    )
    _emit_suggestion_review_event(
        session,
        principal,
        suggestion,
        event_type="student.intervention_suggestion.accepted",
    )

    session.commit()
    session.refresh(suggestion)
    return _suggestion_read(session, suggestion)


def dismiss_intervention_suggestion(
    session: Session,
    principal: CurrentPrincipal,
    suggestion_id: UUID,
    payload: InterventionSuggestionDismiss,
) -> InterventionSuggestionRead:
    _require_suggestion_permission(
        session,
        principal,
        "intervention.suggestion.review",
    )

    suggestion = _get_pending_suggestion_for_review(
        session,
        suggestion_id,
    )
    now = datetime.now(UTC)

    suggestion.status = "DISMISSED"
    suggestion.reviewed_at = now
    suggestion.reviewed_by_user_id = principal.user_id
    suggestion.review_note = payload.review_note
    suggestion.accepted_intervention_id = None
    suggestion.updated_at = now
    session.add(suggestion)

    _emit_suggestion_review_event(
        session,
        principal,
        suggestion,
        event_type="student.intervention_suggestion.dismissed",
    )

    session.commit()
    session.refresh(suggestion)
    return _suggestion_read(session, suggestion)
