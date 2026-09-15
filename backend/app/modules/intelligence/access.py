from fastapi import HTTPException, status
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.m21_access import has_any_role, has_permission

INTELLIGENCE_MANAGER_ROLES = {
    "SYSTEM_ADMIN",
    "RECTOR",
    "ACADEMIC_COORDINATOR",
}


def require_intelligence_read(
    session: Session,
    principal: CurrentPrincipal,
) -> None:
    if not has_permission(
        session,
        principal,
        "intelligence.read",
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required permission: intelligence.read",
        )


def require_intelligence_manager_read(
    session: Session,
    principal: CurrentPrincipal,
) -> None:
    require_intelligence_read(session, principal)
    if not has_any_role(
        session,
        principal,
        INTELLIGENCE_MANAGER_ROLES,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Institutional intelligence view requires management role",
        )


def require_intelligence_manage(
    session: Session,
    principal: CurrentPrincipal,
) -> None:
    if not has_permission(
        session,
        principal,
        "intelligence.manage",
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required permission: intelligence.manage",
        )
    if not has_any_role(
        session,
        principal,
        INTELLIGENCE_MANAGER_ROLES,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Intelligence mutation requires management role",
        )
