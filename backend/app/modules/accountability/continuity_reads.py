"""Bounded, source-owned M27 reads for the M29-2 continuity surface."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.accountability.ledger_service import _require


def list_authorized_obligation_targets(
    session: Session,
    principal: CurrentPrincipal,
    *,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Return only bounded M27 obligation metadata visible to actor."""
    try:
        _require(session, principal, "accountability.view")
    except HTTPException:
        return []
    bounded_limit = max(1, min(int(limit), 25))
    rows = session.exec(
        text(
            """
            SELECT
                o.id AS target_id,
                CASE WHEN c.subject_type='STUDENT' THEN c.subject_id ELSE NULL END AS student_profile_id,
                o.obligation_type,
                o.next_required_step,
                o.lifecycle,
                o.due_at,
                o.owner_user_id,
                c.id AS case_id
            FROM accountability_obligations o
            JOIN accountability_cases c
              ON c.id=o.case_id
             AND c.organization_id=o.organization_id
             AND c.institution_id=o.institution_id
            WHERE o.organization_id=CAST(:organization_id AS uuid)
              AND o.institution_id=CAST(:institution_id AS uuid)
              AND c.lifecycle IN ('OPEN','REOPENED')
              AND o.lifecycle IN ('OPEN','IN_PROGRESS')
            ORDER BY
                CASE WHEN o.due_at IS NOT NULL AND o.due_at < now() THEN 0 ELSE 1 END,
                o.due_at NULLS LAST,
                o.created_at,
                o.id
            LIMIT :limit
            """
        ),
        params={
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
            "limit": bounded_limit,
        },
    ).all()
    return [
        {
            "target_id": row[0],
            "student_profile_id": row[1],
            "obligation_type": str(row[2]),
            "next_required_step": str(row[3]),
            "source_state": str(row[4]),
            "due_at": row[5],
            "owner_user_id": row[6],
            "case_id": row[7],
        }
        for row in rows
    ]
