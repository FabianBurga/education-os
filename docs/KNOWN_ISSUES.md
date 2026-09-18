# Known Issues and Holds

## Historical external hold

Repository/project history records an M23 live-provider hold caused by provider/API credit or HTTP 429 availability. This is historical evidence and was not revalidated by M25; no live provider call was made for M25 closure.

M25 does not depend on live-provider availability. Fake-provider validation and deterministic fallback remain available with zero network calls.

## Current limitations

- OpenAI, Anthropic, and local adapters are known closed keys but are not executable in M25.
- Provider model registry has no enabled live-provider rows seeded by M25.
- Budget concurrency depends on retaining the transaction-scoped advisory-lock admission guard.
- The full backend suite has one accepted M21 E2E skip when `M21_E2E_DATABASE_URL` is not configured.

No live provider validation is implied by the M25 PASS state.

## M25 closure status

M25 - Agentic Control Plane is formally CLOSED at `bd0fbaa719eae4884d9a6c3ab8600939e88bb433`, tagged `m25-governed-provider-explainer-v0.25.3`, and remotely backed up. M25-3E remains optional and unexecuted. This does not close the historical M23 live-provider HOLD EXTERNAL.
