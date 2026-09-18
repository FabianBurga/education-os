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
    "student.timeline.inspect": CapabilityDefinition(
        key="student.timeline.inspect", required_permission="student_timeline.read",
        maximum_autonomy="L0", side_effect_class="NONE",
    ),
    "intelligence.snapshot.inspect": CapabilityDefinition(
        key="intelligence.snapshot.inspect", required_permission="intelligence.read",
        maximum_autonomy="L0", side_effect_class="NONE",
    ),
}
TOOLS = {
    "m24.integration_run.inspect": ToolDefinition(
        key="m24.integration_run.inspect", capability_key="integration.run.inspect",
        required_permission="integrations.view", maximum_autonomy="L0",
        side_effect_class="NONE", input_schema_version="1",
    ),
    "m21.student_timeline.inspect": ToolDefinition(
        key="m21.student_timeline.inspect", capability_key="student.timeline.inspect",
        required_permission="student_timeline.read", maximum_autonomy="L0",
        side_effect_class="NONE", input_schema_version="1",
    ),
    "m22.intelligence_snapshot.inspect": ToolDefinition(
        key="m22.intelligence_snapshot.inspect", capability_key="intelligence.snapshot.inspect",
        required_permission="intelligence.read", maximum_autonomy="L0",
        side_effect_class="NONE", input_schema_version="1",
    ),
}
AGENTS = {
    "integration_run_advisor": AgentDefinitionRegistry(
        key="integration_run_advisor", capability_keys=("integration.run.inspect",),
        tool_keys=("m24.integration_run.inspect",), maximum_autonomy="L0",
    ),
    "student_timeline_advisor": AgentDefinitionRegistry(
        key="student_timeline_advisor", capability_keys=("student.timeline.inspect",),
        tool_keys=("m21.student_timeline.inspect",), maximum_autonomy="L0",
    ),
    "institution_intelligence_advisor": AgentDefinitionRegistry(
        key="institution_intelligence_advisor", capability_keys=("intelligence.snapshot.inspect",),
        tool_keys=("m22.intelligence_snapshot.inspect",), maximum_autonomy="L0",
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
