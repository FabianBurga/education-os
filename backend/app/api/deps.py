from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.core.demo import demo_identity
from app.core.security import decode_access_token
from app.db.session import get_session
from app.db.tenant_context import TenantContext, apply_tenant_context

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class CurrentPrincipal:
    user_id: UUID
    organization_id: UUID
    institution_id: UUID


def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    if settings.EDUCATION_OS_DEMO_MODE:
        user, organization, institution = demo_identity(request, session)
        return CurrentPrincipal(user, organization, institution)
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = decode_access_token(credentials.credentials)
        principal = CurrentPrincipal(
            user_id=UUID(str(payload["sub"])),
            organization_id=UUID(str(payload["organization_id"])),
            institution_id=UUID(str(payload["institution_id"])),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        ) from exc

    # The three scope claims come from a token signed by Education OS.
    # Apply them first so PostgreSQL RLS can participate in membership validation.
    apply_tenant_context(
        session,
        TenantContext(
            organization_id=principal.organization_id,
            institution_id=principal.institution_id,
            user_id=principal.user_id,
        ),
    )

    row = session.exec(
        text(
            """
            SELECT m.user_id, m.institution_id, i.organization_id
            FROM memberships m
            JOIN institutions i ON i.id = m.institution_id
            WHERE m.user_id = CAST(:user_id AS uuid)
              AND m.institution_id = CAST(:institution_id AS uuid)
              AND i.organization_id = CAST(:organization_id AS uuid)
              AND m.status = 'ACTIVE'
              AND i.status = 'ACTIVE'
            """
        ),
        params={
            "user_id": str(principal.user_id),
            "institution_id": str(principal.institution_id),
            "organization_id": str(principal.organization_id),
        },
    ).first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active membership for signed institution context",
        )

    return principal
