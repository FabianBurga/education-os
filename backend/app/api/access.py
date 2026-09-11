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


def require_staff_access(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
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
    return principal


def require_admin_access(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    person_id = _person_id_for_user(session, principal.user_id)
    row = session.exec(
        text(
            """
            SELECT sp.id
            FROM staff_profiles sp
            JOIN memberships m
              ON m.user_id = CAST(:user_id AS uuid)
             AND m.institution_id = CAST(:institution_id AS uuid)
             AND m.status = 'ACTIVE'
            JOIN membership_roles mr ON mr.membership_id = m.id
            JOIN role_permissions rp ON rp.role_id = mr.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE sp.person_id = CAST(:person_id AS uuid)
              AND sp.institution_id = CAST(:institution_id AS uuid)
              AND sp.status = 'ACTIVE'
              AND p.key = 'admin.console.access'
            LIMIT 1
            """
        ).bindparams(
            user_id=str(principal.user_id),
            person_id=str(person_id),
            institution_id=str(principal.institution_id),
        )
    ).first()

    if row is None:
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
    person_id = _person_id_for_user(session, principal.user_id)
    row = session.exec(
        text(
            """
            SELECT sp.id
            FROM staff_profiles sp
            JOIN memberships m
              ON m.user_id = CAST(:user_id AS uuid)
             AND m.institution_id = CAST(:institution_id AS uuid)
             AND m.status = 'ACTIVE'
            JOIN membership_roles mr ON mr.membership_id = m.id
            JOIN role_permissions rp ON rp.role_id = mr.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE sp.person_id = CAST(:person_id AS uuid)
              AND sp.institution_id = CAST(:institution_id AS uuid)
              AND sp.status = 'ACTIVE'
              AND p.key = :permission_key
            LIMIT 1
            """
        ).bindparams(
            user_id=str(principal.user_id),
            person_id=str(person_id),
            institution_id=str(principal.institution_id),
            permission_key=permission_key,
        )
    ).first()

    if row is None:
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
