from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

from app.api.access import GuardianPrincipal, get_guardian_principal
from app.db.session import get_session


def _guardian_permission_exists(
    session: Session,
    guardian: GuardianPrincipal,
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
            user_id=str(guardian.user_id),
            institution_id=str(guardian.institution_id),
            permission_key=permission_key,
        )
    ).first()
    return row is not None


def _require_guardian_permission(
    session: Session,
    guardian: GuardianPrincipal,
    permission_key: str,
    detail: str,
) -> GuardianPrincipal:
    if not _guardian_permission_exists(
        session,
        guardian,
        permission_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )
    return guardian


def require_guardian_access(
    guardian: GuardianPrincipal = Depends(get_guardian_principal),
    session: Session = Depends(get_session),
) -> GuardianPrincipal:
    return _require_guardian_permission(
        session,
        guardian,
        "guardian.console.access",
        "Guardian Console permission required",
    )


def require_guardian_students(
    guardian: GuardianPrincipal = Depends(get_guardian_principal),
    session: Session = Depends(get_session),
) -> GuardianPrincipal:
    return _require_guardian_permission(
        session,
        guardian,
        "guardian.students.view",
        "Guardian student-view permission required",
    )


def require_guardian_schedule(
    guardian: GuardianPrincipal = Depends(get_guardian_principal),
    session: Session = Depends(get_session),
) -> GuardianPrincipal:
    return _require_guardian_permission(
        session,
        guardian,
        "guardian.schedule.view",
        "Guardian schedule-view permission required",
    )


def require_guardian_attendance(
    guardian: GuardianPrincipal = Depends(get_guardian_principal),
    session: Session = Depends(get_session),
) -> GuardianPrincipal:
    return _require_guardian_permission(
        session,
        guardian,
        "guardian.attendance.view",
        "Guardian attendance-view permission required",
    )


def require_guardian_grades(
    guardian: GuardianPrincipal = Depends(get_guardian_principal),
    session: Session = Depends(get_session),
) -> GuardianPrincipal:
    return _require_guardian_permission(
        session,
        guardian,
        "guardian.grades.view",
        "Guardian grade-view permission required",
    )


def require_guardian_notices(
    guardian: GuardianPrincipal = Depends(get_guardian_principal),
    session: Session = Depends(get_session),
) -> GuardianPrincipal:
    return _require_guardian_permission(
        session,
        guardian,
        "guardian.notices.view",
        "Guardian notice-view permission required",
    )


def require_guardian_notice_acknowledgement(
    guardian: GuardianPrincipal = Depends(get_guardian_principal),
    session: Session = Depends(get_session),
) -> GuardianPrincipal:
    return _require_guardian_permission(
        session,
        guardian,
        "guardian.notices.acknowledge",
        "Guardian notice-acknowledgement permission required",
    )


def require_guardian_progress(
    guardian: GuardianPrincipal = Depends(get_guardian_principal),
    session: Session = Depends(get_session),
) -> GuardianPrincipal:
    return _require_guardian_permission(
        session,
        guardian,
        "guardian.progress.view",
        "Guardian progress-view permission required",
    )


GuardianAccessDep = Annotated[
    GuardianPrincipal,
    Depends(require_guardian_access),
]
GuardianStudentsDep = Annotated[
    GuardianPrincipal,
    Depends(require_guardian_students),
]
GuardianScheduleDep = Annotated[
    GuardianPrincipal,
    Depends(require_guardian_schedule),
]
GuardianAttendanceDep = Annotated[
    GuardianPrincipal,
    Depends(require_guardian_attendance),
]
GuardianGradesDep = Annotated[
    GuardianPrincipal,
    Depends(require_guardian_grades),
]
GuardianNoticesDep = Annotated[
    GuardianPrincipal,
    Depends(require_guardian_notices),
]
GuardianNoticeAckDep = Annotated[
    GuardianPrincipal,
    Depends(require_guardian_notice_acknowledgement),
]
GuardianProgressDep = Annotated[
    GuardianPrincipal,
    Depends(require_guardian_progress),
]
