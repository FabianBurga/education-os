from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.interventions.models import (
    InterventionSuggestion,
    InterventionSuggestionEvidence,
)
from app.modules.interventions.schemas import (
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
