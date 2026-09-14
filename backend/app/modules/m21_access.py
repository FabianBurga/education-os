from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal

_PRIVILEGED_M21_ROLES = {
    "SYSTEM_ADMIN",
    "RECTOR",
    "ACADEMIC_COORDINATOR",
}


def has_permission(
    session: Session,
    principal: CurrentPrincipal,
    permission_key: str,
) -> bool:
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
              AND p.key = :permission_key
            LIMIT 1
            """
        ),
        params={
            "user_id": str(principal.user_id),
            "institution_id": str(principal.institution_id),
            "permission_key": permission_key,
        },
    ).first()
    return row is not None


def has_any_role(
    session: Session,
    principal: CurrentPrincipal,
    role_keys: set[str],
) -> bool:
    if not role_keys:
        return False

    row = session.exec(
        text(
            """
            SELECT 1
            FROM memberships m
            JOIN membership_roles mr ON mr.membership_id = m.id
            JOIN roles r ON r.id = mr.role_id
            WHERE m.user_id = CAST(:user_id AS uuid)
              AND m.institution_id = CAST(:institution_id AS uuid)
              AND m.status = 'ACTIVE'
              AND r.key = ANY(CAST(:role_keys AS text[]))
            LIMIT 1
            """
        ),
        params={
            "user_id": str(principal.user_id),
            "institution_id": str(principal.institution_id),
            "role_keys": sorted(role_keys),
        },
    ).first()
    return row is not None


def is_privileged_m21_staff(
    session: Session,
    principal: CurrentPrincipal,
) -> bool:
    return has_any_role(session, principal, _PRIVILEGED_M21_ROLES)


def is_teacher(
    session: Session,
    principal: CurrentPrincipal,
) -> bool:
    return has_any_role(session, principal, {"TEACHER"})


def teacher_has_student_scope(
    session: Session,
    principal: CurrentPrincipal,
    student_profile_id: UUID,
) -> bool:
    row = session.exec(
        text(
            """
            SELECT 1
            FROM user_accounts ua
            JOIN staff_profiles sp
              ON sp.person_id = ua.person_id
             AND sp.institution_id = CAST(:institution_id AS uuid)
             AND sp.status = 'ACTIVE'
            JOIN teaching_assignments ta
              ON ta.staff_profile_id = sp.id
             AND ta.institution_id = CAST(:institution_id AS uuid)
            JOIN course_offerings co
              ON co.id = ta.course_offering_id
             AND co.institution_id = CAST(:institution_id AS uuid)
             AND co.status = 'ACTIVE'
            JOIN student_section_assignments ssa
              ON ssa.section_id = co.section_id
             AND ssa.institution_id = CAST(:institution_id AS uuid)
             AND ssa.status = 'ACTIVE'
            JOIN enrollments e
              ON e.id = ssa.enrollment_id
             AND e.institution_id = CAST(:institution_id AS uuid)
            WHERE ua.id = CAST(:user_id AS uuid)
              AND ua.is_active = true
              AND e.student_profile_id = CAST(:student_profile_id AS uuid)
              AND (ta.starts_on IS NULL OR ta.starts_on <= CURRENT_DATE)
              AND (ta.ends_on IS NULL OR ta.ends_on >= CURRENT_DATE)
            LIMIT 1
            """
        ),
        params={
            "user_id": str(principal.user_id),
            "institution_id": str(principal.institution_id),
            "student_profile_id": str(student_profile_id),
        },
    ).first()
    return row is not None


def can_access_student(
    session: Session,
    principal: CurrentPrincipal,
    student_profile_id: UUID,
    *,
    permission_key: str,
) -> bool:
    if not has_permission(session, principal, permission_key):
        return False

    if is_privileged_m21_staff(session, principal):
        return True

    if is_teacher(session, principal):
        return teacher_has_student_scope(
            session,
            principal,
            student_profile_id,
        )

    return False


def require_student_scope(
    session: Session,
    principal: CurrentPrincipal,
    student_profile_id: UUID,
    *,
    permission_key: str,
) -> None:
    if not has_permission(session, principal, permission_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {permission_key}",
        )

    if is_privileged_m21_staff(session, principal):
        return

    if is_teacher(session, principal) and teacher_has_student_scope(
        session,
        principal,
        student_profile_id,
    ):
        return

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Student not found in authorized M21 scope",
    )
