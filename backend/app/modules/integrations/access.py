from fastapi import HTTPException, status
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.m21_access import has_permission


def require_integration_permission(session: Session, principal: CurrentPrincipal, key: str) -> None:
    if not has_permission(session, principal, key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing required permission: {key}")


def require_integrations_view(session: Session, principal: CurrentPrincipal) -> None:
    require_integration_permission(session, principal, "integrations.view")


def require_integrations_manage(session: Session, principal: CurrentPrincipal) -> None:
    require_integration_permission(session, principal, "integrations.manage")


def require_integrations_run(session: Session, principal: CurrentPrincipal) -> None:
    require_integration_permission(session, principal, "integrations.run")


def require_integrations_audit_read(session: Session, principal: CurrentPrincipal) -> None:
    require_integration_permission(session, principal, "integrations.audit.read")
