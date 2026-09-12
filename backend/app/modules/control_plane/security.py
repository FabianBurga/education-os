from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session


def _staff_permission_exists(
    session: Session,
    principal: CurrentPrincipal,
    permission_key: str,
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
            JOIN memberships m
              ON m.user_id = ua.id
             AND m.institution_id = CAST(:institution_id AS uuid)
             AND m.status = 'ACTIVE'
            JOIN membership_roles mr ON mr.membership_id = m.id
            JOIN role_permissions rp ON rp.role_id = mr.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE ua.id = CAST(:user_id AS uuid)
              AND ua.is_active = true
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


def _require(
    session: Session,
    principal: CurrentPrincipal,
    permission_key: str,
    detail: str,
) -> CurrentPrincipal:
    if not _staff_permission_exists(
        session,
        principal,
        permission_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )
    return principal


def require_control_plane_view(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    return _require(
        session,
        principal,
        "control_plane.view",
        "Institution Control Plane view permission required",
    )


def require_control_plane_manage(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    return _require(
        session,
        principal,
        "control_plane.manage",
        "Institution Control Plane management permission required",
    )


ControlPlaneViewDep = Annotated[
    CurrentPrincipal,
    Depends(require_control_plane_view),
]
ControlPlaneManageDep = Annotated[
    CurrentPrincipal,
    Depends(require_control_plane_manage),
]
