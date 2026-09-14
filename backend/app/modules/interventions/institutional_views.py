from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.interventions.models import (
    Intervention,
    InterventionAction,
    InterventionFollowUp,
)
from app.modules.interventions.schemas import (
    InstitutionalInterventionItem,
    InstitutionalInterventionQueue,
    InterventionActionRead,
    InterventionFollowUpRead,
    InterventionRead,
)
from app.modules.m21_access import (
    has_any_role,
    has_permission,
    is_teacher,
)

_MANAGER_ROLES = {
    "SYSTEM_ADMIN",
    "RECTOR",
    "ACADEMIC_COORDINATOR",
}


def _can_read_full_sensitive_detail(
    session: Session,
    principal: CurrentPrincipal,
    sensitivity: str,
) -> bool:
    if sensitivity == "GENERAL":
        return not is_teacher(session, principal)

    return has_permission(
        session,
        principal,
        "student_timeline.read_confidential",
    )


def intervention_read_for_principal(
    session: Session,
    principal: CurrentPrincipal,
    entity: Intervention,
) -> InterventionRead:
    protected = not _can_read_full_sensitive_detail(
        session,
        principal,
        entity.sensitivity,
    )
    return InterventionRead.model_validate(
        entity,
        from_attributes=True,
    ).model_copy(
        update={
            "reason": None if protected else entity.reason,
            "objective": None if protected else entity.objective,
            "outcome_summary": (
                None if protected else entity.outcome_summary
            ),
            "protected_detail": protected,
        }
    )


def action_read_for_principal(
    session: Session,
    principal: CurrentPrincipal,
    action: InterventionAction,
    *,
    parent_sensitivity: str,
) -> InterventionActionRead:
    protected = not _can_read_full_sensitive_detail(
        session,
        principal,
        parent_sensitivity,
    )
    return InterventionActionRead.model_validate(
        action,
        from_attributes=True,
    ).model_copy(
        update={
            "description": None if protected else action.description,
            "completion_note": (
                None if protected else action.completion_note
            ),
            "protected_detail": protected,
        }
    )


def followup_read_for_principal(
    session: Session,
    principal: CurrentPrincipal,
    followup: InterventionFollowUp,
) -> InterventionFollowUpRead:
    protected = not _can_read_full_sensitive_detail(
        session,
        principal,
        followup.sensitivity,
    )
    return InterventionFollowUpRead.model_validate(
        followup,
        from_attributes=True,
    ).model_copy(
        update={
            "note": None if protected else followup.note,
            "protected_detail": protected,
        }
    )


def list_institutional_intervention_queue(
    session: Session,
    principal: CurrentPrincipal,
    *,
    limit: int = 50,
    status_filter: str | None = None,
    severity_filter: str | None = None,
    assigned_user_id: UUID | None = None,
    overdue_only: bool = False,
    unassigned_only: bool = False,
) -> InstitutionalInterventionQueue:
    if not has_any_role(session, principal, _MANAGER_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Institutional intervention view requires management role",
        )

    limit = max(1, min(limit, 100))

    clauses = [
        "organization_id = CAST(:organization_id AS uuid)",
        "institution_id = CAST(:institution_id AS uuid)",
    ]
    params: dict[str, object] = {
        "organization_id": str(principal.organization_id),
        "institution_id": str(principal.institution_id),
        "limit": limit,
    }

    if status_filter is not None:
        clauses.append("status = CAST(:status_filter AS text)")
        params["status_filter"] = status_filter

    if severity_filter is not None:
        clauses.append("severity = CAST(:severity_filter AS text)")
        params["severity_filter"] = severity_filter

    if assigned_user_id is not None:
        clauses.append("assigned_user_id = CAST(:assigned_user_id AS uuid)")
        params["assigned_user_id"] = str(assigned_user_id)

    if overdue_only:
        clauses.append(
            "target_at IS NOT NULL "
            "AND target_at < now() "
            "AND status NOT IN ('RESOLVED','CLOSED','CANCELLED')"
        )

    if unassigned_only:
        clauses.append(
            "assigned_user_id IS NULL AND assigned_role_code IS NULL"
        )

    where_sql = " AND ".join(clauses)

    rows = session.exec(
        text(
            f"""
            SELECT
                id,
                student_profile_id,
                intervention_type,
                severity,
                status,
                sensitivity,
                title,
                assigned_role_code,
                assigned_user_id,
                target_at,
                opened_at
            FROM interventions
            WHERE {where_sql}
            ORDER BY
                CASE severity
                    WHEN 'CRITICAL' THEN 4
                    WHEN 'HIGH' THEN 3
                    WHEN 'MEDIUM' THEN 2
                    ELSE 1
                END DESC,
                target_at NULLS LAST,
                opened_at DESC
            LIMIT :limit
            """
        ),
        params=params,
    ).all()

    items = [
        InstitutionalInterventionItem(
            id=row[0],
            student_profile_id=row[1],
            intervention_type=str(row[2]),
            severity=str(row[3]),
            status=str(row[4]),
            sensitivity=str(row[5]),
            title=str(row[6]),
            assigned_role_code=row[7],
            assigned_user_id=row[8],
            target_at=row[9],
            opened_at=row[10],
            protected_detail=True,
        )
        for row in rows
    ]

    summary = session.exec(
        text(
            """
            SELECT status, COUNT(*) AS count
            FROM interventions
            WHERE organization_id = CAST(:organization_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
            GROUP BY status
            """
        ),
        params={
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
        },
    ).all()

    status_counts = {str(row[0]): int(row[1]) for row in summary}

    overdue_count = int(
        session.exec(
            text(
                """
                SELECT COUNT(*)
                FROM interventions
                WHERE organization_id = CAST(:organization_id AS uuid)
                  AND institution_id = CAST(:institution_id AS uuid)
                  AND target_at IS NOT NULL
                  AND target_at < now()
                  AND status NOT IN ('RESOLVED','CLOSED','CANCELLED')
                """
            ),
            params={
                "organization_id": str(principal.organization_id),
                "institution_id": str(principal.institution_id),
            },
        ).one()[0]
    )

    unassigned_count = int(
        session.exec(
            text(
                """
                SELECT COUNT(*)
                FROM interventions
                WHERE organization_id = CAST(:organization_id AS uuid)
                  AND institution_id = CAST(:institution_id AS uuid)
                  AND assigned_user_id IS NULL
                  AND assigned_role_code IS NULL
                  AND status NOT IN ('CLOSED','CANCELLED')
                """
            ),
            params={
                "organization_id": str(principal.organization_id),
                "institution_id": str(principal.institution_id),
            },
        ).one()[0]
    )

    return InstitutionalInterventionQueue(
        items=items,
        count=len(items),
        status_counts=status_counts,
        overdue_count=overdue_count,
        unassigned_count=unassigned_count,
    )
