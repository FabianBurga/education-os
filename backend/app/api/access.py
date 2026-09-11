from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session


@dataclass(frozen=True, slots=True)
class GuardianPrincipal:
    user_id: UUID
    organization_id: UUID
    institution_id: UUID
    person_id: UUID
    guardian_profile_id: UUID


@dataclass(frozen=True, slots=True)
class TeacherPrincipal:
    user_id: UUID
    organization_id: UUID
    institution_id: UUID
    person_id: UUID
    staff_profile_id: UUID


@dataclass(frozen=True, slots=True)
class StudentPrincipal:
    user_id: UUID
    organization_id: UUID
    institution_id: UUID
    person_id: UUID
    student_profile_id: UUID


def _person_id_for_user(session: Session, user_id: UUID) -> UUID:
    row = session.exec(
        text(
            """
            SELECT person_id
            FROM user_accounts
            WHERE id = CAST(:user_id AS uuid) AND is_active = true
            """
        ).bindparams(user_id=str(user_id))
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active user account not found in signed context",
        )
    return row[0]


def _active_staff_profile_id(
    session: Session,
    principal: CurrentPrincipal,
) -> UUID:
    person_id = _person_id_for_user(session, principal.user_id)
    row = session.exec(
        text(
            """
            SELECT id
            FROM staff_profiles
            WHERE person_id = CAST(:person_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND status = 'ACTIVE'
            """
        ).bindparams(
            person_id=str(person_id),
            institution_id=str(principal.institution_id),
        )
    ).first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active staff profile required",
        )
    return row[0]


def require_staff_access(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    _active_staff_profile_id(session, principal)
    return principal


def _permission_exists(
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
        ).bindparams(
            user_id=str(principal.user_id),
            institution_id=str(principal.institution_id),
            permission_key=permission_key,
        )
    ).first()
    return row is not None


def require_privileged_staff_access(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    _active_staff_profile_id(session, principal)

    teacher_role = session.exec(
        text(
            """
            SELECT 1
            FROM memberships m
            JOIN membership_roles mr ON mr.membership_id = m.id
            JOIN roles r ON r.id = mr.role_id
            WHERE m.user_id = CAST(:user_id AS uuid)
              AND m.institution_id = CAST(:institution_id AS uuid)
              AND m.status = 'ACTIVE'
              AND r.key = 'TEACHER'
            LIMIT 1
            """
        ).bindparams(
            user_id=str(principal.user_id),
            institution_id=str(principal.institution_id),
        )
    ).first()

    if teacher_role is None:
        return principal

    elevated = (
        _permission_exists(session, principal, "admin.console.access")
        or _permission_exists(session, principal, "coord.console.access")
    )
    if not elevated:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Teacher-only actors must use scoped Teacher Console APIs"
            ),
        )
    return principal


def require_admin_access(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    _active_staff_profile_id(session, principal)
    if not _permission_exists(session, principal, "admin.console.access"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator permission required",
        )
    return principal


def _require_staff_permission(
    session: Session,
    principal: CurrentPrincipal,
    permission_key: str,
    detail: str,
) -> CurrentPrincipal:
    _active_staff_profile_id(session, principal)
    if not _permission_exists(session, principal, permission_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )
    return principal


def require_coordination_access(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    return _require_staff_permission(
        session,
        principal,
        "coord.console.access",
        "Rector or academic coordination permission required",
    )


def require_coordination_analytics(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    return _require_staff_permission(
        session,
        principal,
        "coord.analytics.view",
        "Coordination analytics permission required",
    )


def require_coordination_signals(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    return _require_staff_permission(
        session,
        principal,
        "coord.signals.manage",
        "Coordination signal-management permission required",
    )


def require_coordination_cases(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    return _require_staff_permission(
        session,
        principal,
        "coord.cases.manage",
        "Coordination case-management permission required",
    )


def _require_teacher_permission(
    session: Session,
    principal: CurrentPrincipal,
    permission_key: str,
    detail: str,
) -> TeacherPrincipal:
    staff_profile_id = _active_staff_profile_id(session, principal)
    person_id = _person_id_for_user(session, principal.user_id)
    if not _permission_exists(session, principal, permission_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )
    return TeacherPrincipal(
        user_id=principal.user_id,
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        person_id=person_id,
        staff_profile_id=staff_profile_id,
    )


def require_teacher_access(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> TeacherPrincipal:
    return _require_teacher_permission(
        session,
        principal,
        "teacher.console.access",
        "Teacher Console permission required",
    )


def require_teacher_classes(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> TeacherPrincipal:
    return _require_teacher_permission(
        session,
        principal,
        "teacher.classes.view",
        "Teacher class-view permission required",
    )


def require_teacher_attendance(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> TeacherPrincipal:
    return _require_teacher_permission(
        session,
        principal,
        "teacher.attendance.manage",
        "Teacher attendance-management permission required",
    )


def require_teacher_grades(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> TeacherPrincipal:
    return _require_teacher_permission(
        session,
        principal,
        "teacher.grades.manage",
        "Teacher grade-management permission required",
    )


def require_teacher_tasks(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> TeacherPrincipal:
    return _require_teacher_permission(
        session,
        principal,
        "teacher.tasks.manage",
        "Teacher task-management permission required",
    )



def _active_student_profile_id(
    session: Session,
    principal: CurrentPrincipal,
) -> UUID:
    person_id = _person_id_for_user(session, principal.user_id)
    row = session.exec(
        text(
            """
            SELECT id
            FROM student_profiles
            WHERE person_id = CAST(:person_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND status = 'ACTIVE'
            """
        ).bindparams(
            person_id=str(person_id),
            institution_id=str(principal.institution_id),
        )
    ).first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active student profile required",
        )
    return row[0]


def _require_student_permission(
    session: Session,
    principal: CurrentPrincipal,
    permission_key: str,
    detail: str,
) -> StudentPrincipal:
    student_profile_id = _active_student_profile_id(session, principal)
    person_id = _person_id_for_user(session, principal.user_id)
    if not _permission_exists(session, principal, permission_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )
    return StudentPrincipal(
        user_id=principal.user_id,
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        person_id=person_id,
        student_profile_id=student_profile_id,
    )


def require_student_access(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> StudentPrincipal:
    return _require_student_permission(
        session,
        principal,
        "student.console.access",
        "Student Console permission required",
    )


def require_student_profile(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> StudentPrincipal:
    return _require_student_permission(
        session,
        principal,
        "student.profile.view",
        "Student profile permission required",
    )


def require_student_classes(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> StudentPrincipal:
    return _require_student_permission(
        session,
        principal,
        "student.classes.view",
        "Student class-view permission required",
    )


def require_student_schedule(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> StudentPrincipal:
    return _require_student_permission(
        session,
        principal,
        "student.schedule.view",
        "Student schedule permission required",
    )


def require_student_attendance(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> StudentPrincipal:
    return _require_student_permission(
        session,
        principal,
        "student.attendance.view",
        "Student attendance permission required",
    )


def require_student_grades(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> StudentPrincipal:
    return _require_student_permission(
        session,
        principal,
        "student.grades.view",
        "Student grade permission required",
    )


def require_student_notices(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> StudentPrincipal:
    return _require_student_permission(
        session,
        principal,
        "student.notices.view",
        "Student notice permission required",
    )


def require_student_progress(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> StudentPrincipal:
    return _require_student_permission(
        session,
        principal,
        "student.progress.view",
        "Student progress permission required",
    )


def get_guardian_principal(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> GuardianPrincipal:
    person_id = _person_id_for_user(session, principal.user_id)
    row = session.exec(
        text(
            """
            SELECT id
            FROM guardian_profiles
            WHERE person_id = CAST(:person_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND status = 'ACTIVE'
            """
        ).bindparams(
            person_id=str(person_id),
            institution_id=str(principal.institution_id),
        )
    ).first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active guardian profile required",
        )

    return GuardianPrincipal(
        user_id=principal.user_id,
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        person_id=person_id,
        guardian_profile_id=row[0],
    )


GuardianPrincipalDep = Annotated[
    GuardianPrincipal,
    Depends(get_guardian_principal),
]
