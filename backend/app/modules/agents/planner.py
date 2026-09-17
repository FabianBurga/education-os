from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PlannedStep:
    sequence: int
    step_type: str
    tool_key: str | None = None


def plan_integration_run_advisor(run_id: UUID) -> tuple[PlannedStep, ...]:
    """Deterministic, closed plan; no provider or free-form planning input."""
    return (
        PlannedStep(1, "PLANNER"),
        PlannedStep(2, "POLICY"),
        PlannedStep(3, "EXECUTOR", "m24.integration_run.inspect"),
        PlannedStep(4, "VERIFIER"),
    )
