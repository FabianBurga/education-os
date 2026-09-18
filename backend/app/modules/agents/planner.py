from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PlannedStep:
    sequence: int
    step_type: str
    tool_key: str | None = None


_AGENT_TO_TOOL = {
    "integration_run_advisor": "m24.integration_run.inspect",
    "student_timeline_advisor": "m21.student_timeline.inspect",
    "institution_intelligence_advisor": "m22.intelligence_snapshot.inspect",
}


def plan_advisor(agent_key: str) -> tuple[PlannedStep, ...]:
    """Deterministic closed plans; no provider or free-form planning input."""
    tool_key = _AGENT_TO_TOOL.get(agent_key)
    if tool_key is None:
        raise ValueError("Unknown deterministic advisor")
    return (
        PlannedStep(1, "PLANNER"),
        PlannedStep(2, "POLICY"),
        PlannedStep(3, "EXECUTOR", tool_key),
        PlannedStep(4, "VERIFIER"),
    )


def plan_integration_run_advisor(run_id: UUID) -> tuple[PlannedStep, ...]:
    """M25-1 compatibility wrapper."""
    return plan_advisor("integration_run_advisor")
