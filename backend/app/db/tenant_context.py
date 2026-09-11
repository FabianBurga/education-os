from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session


@dataclass(frozen=True, slots=True)
class TenantContext:
    organization_id: UUID
    institution_id: UUID
    user_id: UUID


def apply_tenant_context(session: Session, ctx: TenantContext) -> None:
    statement = text(
        """
        SELECT
          set_config('app.organization_id', :organization_id, true),
          set_config('app.institution_id', :institution_id, true),
          set_config('app.user_id', :user_id, true)
        """
    )
    session.exec(
        statement,
        params={
            "organization_id": str(ctx.organization_id),
            "institution_id": str(ctx.institution_id),
            "user_id": str(ctx.user_id),
        },
    )


def clear_tenant_context(session: Session) -> None:
    session.exec(
        text(
            """
            SELECT
              set_config('app.organization_id', '', true),
              set_config('app.institution_id', '', true),
              set_config('app.user_id', '', true)
            """
        )
    )
