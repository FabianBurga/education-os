from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlmodel import Session


@dataclass(frozen=True, slots=True)
class TenantContext:
    organization_id: UUID
    institution_id: UUID
    user_id: UUID


_TENANT_CONTEXT_INFO_KEY = "education_os.tenant_context"

_TENANT_CONTEXT_STATEMENT = text(
    """
    SELECT
      set_config('app.organization_id', :organization_id, true),
      set_config('app.institution_id', :institution_id, true),
      set_config('app.user_id', :user_id, true)
    """
)


def _tenant_params(ctx: TenantContext) -> dict[str, str]:
    return {
        "organization_id": str(ctx.organization_id),
        "institution_id": str(ctx.institution_id),
        "user_id": str(ctx.user_id),
    }


def _apply_context_on_connection(connection: Connection, ctx: TenantContext) -> None:
    connection.execute(_TENANT_CONTEXT_STATEMENT, _tenant_params(ctx))


@event.listens_for(Session, "after_begin")
def _restore_transaction_local_tenant_context(
    session: Session,
    _transaction,
    connection: Connection,
) -> None:
    """Reapply tenant RLS settings whenever SQLAlchemy opens a transaction."""
    ctx = session.info.get(_TENANT_CONTEXT_INFO_KEY)
    if isinstance(ctx, TenantContext):
        _apply_context_on_connection(connection, ctx)


def apply_tenant_context(session: Session, ctx: TenantContext) -> None:
    """Bind tenant identity to this Session and its active transaction."""
    session.info[_TENANT_CONTEXT_INFO_KEY] = ctx
    session.exec(_TENANT_CONTEXT_STATEMENT, params=_tenant_params(ctx))


def clear_tenant_context(session: Session) -> None:
    session.info.pop(_TENANT_CONTEXT_INFO_KEY, None)
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
