from uuid import UUID

from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.agents.tools import inspect_integration_run


def execute_inspection_tool(session: Session, principal: CurrentPrincipal, *, run_id: UUID):
    """Closed dispatch point for M25-1; arbitrary tool selection is impossible."""
    return inspect_integration_run(session, principal, run_id=run_id)
