from uuid import UUID

from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.agents.tools import (
    inspect_institution_intelligence,
    inspect_integration_run,
    inspect_student_timeline,
)


def execute_inspection_tool(
    session: Session,
    principal: CurrentPrincipal,
    *,
    agent_key: str,
    entity_id: UUID | None,
):
    """Closed M25 tool gateway; unknown agent or tool selection is impossible."""
    if agent_key == "integration_run_advisor" and entity_id is not None:
        return inspect_integration_run(session, principal, run_id=entity_id)
    if agent_key == "student_timeline_advisor" and entity_id is not None:
        return inspect_student_timeline(session, principal, student_id=entity_id)
    if agent_key == "institution_intelligence_advisor" and entity_id is None:
        return inspect_institution_intelligence(session, principal)
    raise ValueError("Closed tool gateway rejected input")
