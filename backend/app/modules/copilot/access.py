from fastapi import HTTPException, status
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.m21_access import has_any_role, has_permission

COPILOT_MANAGE_ROLES = {
    "SYSTEM_ADMIN",
}
COPILOT_APPROVER_ROLES = {
    "SYSTEM_ADMIN",
    "RECTOR",
    "ACADEMIC_COORDINATOR",
}

# Historical compatibility alias. Management authorization must use
# COPILOT_MANAGE_ROLES; approval authorization uses COPILOT_APPROVER_ROLES.
COPILOT_MANAGER_ROLES = COPILOT_APPROVER_ROLES


def require_copilot_use(
    session: Session,
    principal: CurrentPrincipal,
) -> None:
    if not has_permission(session, principal, "copilot.use"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required permission: copilot.use",
        )


def require_copilot_manage(
    session: Session,
    principal: CurrentPrincipal,
) -> None:
    if not has_permission(session, principal, "copilot.manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required permission: copilot.manage",
        )
    if not has_any_role(session, principal, COPILOT_MANAGE_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Copilot management requires SYSTEM_ADMIN role",
        )


def require_copilot_action_approve(
    session: Session,
    principal: CurrentPrincipal,
) -> None:
    if not has_permission(session, principal, "copilot.action.approve"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required permission: copilot.action.approve",
        )
    if not has_any_role(session, principal, COPILOT_APPROVER_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Copilot action approval requires approver role",
        )
