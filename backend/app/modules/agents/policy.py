from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.agents.registry import AgentDefinitionRegistry, ToolDefinition
from app.modules.m21_access import has_permission

AUTONOMY_ORDER = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5}


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    code: str


def require_permission(session: Session, principal: CurrentPrincipal, permission: str) -> None:
    if not has_permission(session, principal, permission):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent permission denied")


def evaluate_l0_policy(
    session: Session,
    principal: CurrentPrincipal,
    agent: AgentDefinitionRegistry,
    tool: ToolDefinition,
    *,
    policy_max_autonomy: str,
    max_steps: int,
    max_tool_calls: int,
) -> PolicyDecision:
    if agent.maximum_autonomy != "L0" or tool.maximum_autonomy != "L0":
        return PolicyDecision(False, "AUTONOMY_DENIED")
    if tool.side_effect_class != "NONE":
        return PolicyDecision(False, "SIDE_EFFECT_DENIED")
    if AUTONOMY_ORDER[tool.maximum_autonomy] > AUTONOMY_ORDER.get(policy_max_autonomy, -1):
        return PolicyDecision(False, "POLICY_AUTONOMY_DENIED")
    if max_steps < 4 or max_tool_calls < 1:
        return PolicyDecision(False, "POLICY_LIMIT_DENIED")
    if tool.key not in agent.tool_keys:
        return PolicyDecision(False, "TOOL_NOT_ALLOWLISTED")
    require_permission(session, principal, "agents.use")
    require_permission(session, principal, tool.required_permission)
    return PolicyDecision(True, "ALLOW")
