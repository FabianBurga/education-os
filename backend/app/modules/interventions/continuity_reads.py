"""Bounded, source-owned M21 reads for the M29-2 continuity surface."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.m21_access import has_permission


def list_authorized_followup_targets(
    session: Session,
    principal: CurrentPrincipal,
    *,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Return only bounded M21 follow-up metadata already visible to actor."""
    if not has_permission(session, principal, "intervention.read"):
        return []
    bounded_limit = max(1, min(int(limit), 25))
    rows = session.exec(
        text(
            """
            SELECT
                f.id AS target_id,
                iv.id AS intervention_id,
                iv.student_profile_id,
                f.followup_type,
                f.sensitivity,
                f.observed_at,
                iv.status AS intervention_status,
                iv.target_at,
                iv.assigned_user_id,
                iv.assigned_role_code
            FROM intervention_followups f
            JOIN interventions iv
              ON iv.id=f.intervention_id
             AND iv.organization_id=f.organization_id
             AND iv.institution_id=f.institution_id
            WHERE f.organization_id=CAST(:organization_id AS uuid)
              AND f.institution_id=CAST(:institution_id AS uuid)
              AND iv.status NOT IN ('RESOLVED','CLOSED','CANCELLED')
              AND (
                EXISTS (
                    SELECT 1
                    FROM memberships m
                    JOIN membership_roles mr ON mr.membership_id=m.id
                    JOIN roles r ON r.id=mr.role_id
                    WHERE m.user_id=CAST(:user_id AS uuid)
                      AND m.institution_id=CAST(:institution_id AS uuid)
                      AND m.status='ACTIVE'
                      AND r.institution_id=CAST(:institution_id AS uuid)
                      AND r.key IN ('SYSTEM_ADMIN','RECTOR','ACADEMIC_COORDINATOR')
                )
                OR EXISTS (
                    SELECT 1
                    FROM user_accounts ua
                    JOIN staff_profiles sp
                      ON sp.person_id=ua.person_id
                     AND sp.institution_id=CAST(:institution_id AS uuid)
                     AND sp.status='ACTIVE'
                    JOIN teaching_assignments ta
                      ON ta.staff_profile_id=sp.id
                     AND ta.institution_id=CAST(:institution_id AS uuid)
                    JOIN course_offerings co
                      ON co.id=ta.course_offering_id
                     AND co.institution_id=CAST(:institution_id AS uuid)
                     AND co.status='ACTIVE'
                    JOIN student_section_assignments ssa
                      ON ssa.section_id=co.section_id
                     AND ssa.institution_id=CAST(:institution_id AS uuid)
                     AND ssa.status='ACTIVE'
                    JOIN enrollments e
                      ON e.id=ssa.enrollment_id
                     AND e.institution_id=CAST(:institution_id AS uuid)
                    WHERE ua.id=CAST(:user_id AS uuid)
                      AND ua.is_active=true
                      AND e.student_profile_id=iv.student_profile_id
                      AND (ta.starts_on IS NULL OR ta.starts_on<=CURRENT_DATE)
                      AND (ta.ends_on IS NULL OR ta.ends_on>=CURRENT_DATE)
                )
              )
            ORDER BY
                CASE WHEN iv.target_at IS NOT NULL AND iv.target_at < now() THEN 0 ELSE 1 END,
                iv.target_at NULLS LAST,
                f.observed_at DESC,
                f.id
            LIMIT :limit
            """
        ),
        params={
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
            "user_id": str(principal.user_id),
            "limit": bounded_limit,
        },
    ).all()
    return [
        {
            "target_id": row[0],
            "intervention_id": row[1],
            "student_profile_id": row[2],
            "followup_type": str(row[3]),
            "sensitivity": str(row[4]),
            "observed_at": row[5],
            "source_state": str(row[6]),
            "due_at": row[7],
            "owner_user_id": row[8],
            "owner_role": row[9],
        }
        for row in rows
    ]
