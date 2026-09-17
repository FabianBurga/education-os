from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    key: str
    required_permission: str
    maximum_autonomy: str
    side_effect_class: str


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    key: str
    capability_key: str
    required_permission: str
    maximum_autonomy: str
    side_effect_class: str
    input_schema_version: str


@dataclass(frozen=True, slots=True)
class AgentDefinitionRegistry:
    key: str
    capability_keys: tuple[str, ...]
    tool_keys: tuple[str, ...]
    maximum_autonomy: str


CAPABILITIES = {
    "integration.run.inspect": CapabilityDefinition(
        key="integration.run.inspect", required_permission="integrations.view",
        maximum_autonomy="L0", side_effect_class="NONE",
    ),
}
TOOLS = {
    "m24.integration_run.inspect": ToolDefinition(
        key="m24.integration_run.inspect", capability_key="integration.run.inspect",
        required_permission="integrations.view", maximum_autonomy="L0",
        side_effect_class="NONE", input_schema_version="1",
    ),
}
AGENTS = {
    "integration_run_advisor": AgentDefinitionRegistry(
        key="integration_run_advisor", capability_keys=("integration.run.inspect",),
        tool_keys=("m24.integration_run.inspect",), maximum_autonomy="L0",
    ),
}


def known_agent(agent_key: str) -> AgentDefinitionRegistry:
    value = AGENTS.get(agent_key)
    if value is None:
        raise KeyError("Unknown agent key")
    return value


def known_capability(capability_key: str) -> CapabilityDefinition:
    value = CAPABILITIES.get(capability_key)
    if value is None:
        raise KeyError("Unknown capability key")
    return value


def known_tool(tool_key: str) -> ToolDefinition:
    value = TOOLS.get(tool_key)
    if value is None:
        raise KeyError("Unknown tool key")
    return value
