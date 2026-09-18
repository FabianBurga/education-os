# ADR 0031 — M25 Governed Provider Execution

## Decision

Providers operate only behind the M25 Agentic Control Plane. They receive a code-owned prompt contract and a bounded Evidence Pack, return strict typed output, and are independently verified. The initial executable adapter is fake-only; live providers are not an availability dependency.

## Consequences

No arbitrary provider/model/tool selection, generic HTTP, persisted credentials, raw prompt/response storage, or raw DB-to-provider path is permitted. Existing deterministic advisors remain `DETERMINISTIC_ONLY`.

## Validation status

The L0 `integration_run_explainer` fake-provider controlled pilot passed. Valid opaque citations are accepted; duplicate and fabricated citations fail closed to deterministic fallback. OpenAI, Anthropic, and local provider validation remains unexecuted.
