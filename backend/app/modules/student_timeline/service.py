from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.m21_access import require_existing_student_scope, require_student_scope
from app.modules.student_timeline.schemas import (
    StudentTimelineEntryRead,
    StudentTimelinePage,
)

_ALLOWED_CATEGORIES = {
    "ENROLLMENT",
    "ATTENDANCE",
    "ACADEMIC",
    "SIGNAL",
    "INTERVENTION",
    "ACTION",
    "FOLLOW_UP",
    "COMMUNICATION",
    "OUTCOME",
    "SYSTEM",
}
_ALLOWED_SENSITIVITIES = {
    "GENERAL",
    "RESTRICTED",
    "CONFIDENTIAL",
}


def _bounded_limit(limit: int) -> int:
    return max(1, min(limit, 100))


def _normalized_category(category: str | None) -> str | None:
    if category is None:
        return None
    value = category.strip().upper()
    if value not in _ALLOWED_CATEGORIES:
        raise ValueError("Unsupported timeline category")
    return value


def _normalized_sensitivity(sensitivity: str | None) -> str | None:
    if sensitivity is None:
        return None
    value = sensitivity.strip().upper()
    if value not in _ALLOWED_SENSITIVITIES:
        raise ValueError("Unsupported timeline sensitivity")
    return value


def list_student_timeline(
    session: Session,
    principal: CurrentPrincipal,
    *,
    student_profile_id: UUID,
    limit: int = 50,
    before_position: int | None = None,
    category: str | None = None,
    sensitivity: str | None = None,
) -> StudentTimelinePage:
    """Read one student's authorized timeline.

    Row-level security remains the final authorization boundary:
    - privileged staff can see rows allowed by sensitivity permissions;
    - teachers only see GENERAL rows for students inside their teaching scope.
    An authorized student-subject precondition distinguishes an empty timeline
    from an invisible/nonexistent student without disclosing cross-tenant state.
    """
    category = _normalized_category(category)
    sensitivity = _normalized_sensitivity(sensitivity)
    limit = _bounded_limit(limit)

    require_student_scope(
        session,
        principal,
        student_profile_id,
        permission_key="student_timeline.read",
    )
    require_existing_student_scope(
        session,
        principal,
        student_profile_id,
        permission_key="student_timeline.read",
        scope_verified=True,
    )

    rows = session.exec(
        text(
            """
            SELECT
                id,
                student_profile_id,
                ledger_event_id,
                ledger_position,
                event_type,
                event_version,
                category,
                importance,
                sensitivity,
                title,
                summary,
                source_aggregate_type,
                source_aggregate_id,
                actor_user_id,
                correlation_id,
                causation_id,
                context_json,
                occurred_at,
                recorded_at,
                projected_at
            FROM student_timeline_entries
            WHERE student_profile_id = CAST(:student_profile_id AS uuid)
              AND (
                    CAST(:before_position AS bigint) IS NULL
                    OR ledger_position < CAST(:before_position AS bigint)
              )
              AND (
                    CAST(:category AS text) IS NULL
                    OR category = CAST(:category AS text)
              )
              AND (
                    CAST(:sensitivity AS text) IS NULL
                    OR sensitivity = CAST(:sensitivity AS text)
              )
            ORDER BY ledger_position DESC
            LIMIT :limit
            """
        ),
        params={
            "student_profile_id": str(student_profile_id),
            "before_position": before_position,
            "category": category,
            "sensitivity": sensitivity,
            "limit": limit + 1,
        },
    ).all()

    has_more = len(rows) > limit
    page_rows = rows[:limit]

    entries = [
        StudentTimelineEntryRead(
            id=row[0],
            student_profile_id=row[1],
            ledger_event_id=row[2],
            ledger_position=int(row[3]),
            event_type=str(row[4]),
            event_version=int(row[5]),
            category=str(row[6]),
            importance=str(row[7]),
            sensitivity=str(row[8]),
            title=str(row[9]),
            summary=row[10],
            source_aggregate_type=str(row[11]),
            source_aggregate_id=row[12],
            actor_user_id=row[13],
            correlation_id=row[14],
            causation_id=row[15],
            context_json=row[16] if isinstance(row[16], dict) else {},
            occurred_at=row[17],
            recorded_at=row[18],
            projected_at=row[19],
        )
        for row in page_rows
    ]

    next_before_position = None
    if has_more and entries:
        next_before_position = entries[-1].ledger_position

    return StudentTimelinePage(
        student_profile_id=student_profile_id,
        entries=entries,
        next_before_position=next_before_position,
    )
