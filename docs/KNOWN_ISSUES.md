# Known Issues and Holds

## Historical external hold

Repository/project history records an M23 live-provider hold caused by provider/API credit or HTTP 429 availability. This is historical evidence and was not revalidated here; no provider call was made for this documentation gate.

M25-3A/M25-3B do not depend on live-provider availability. Fake-provider validation and deterministic fallback remain available with zero network calls.

## Current limitations

- M25-3C `integration_run_explainer` is implemented but not yet controlled-pilot validated or formally closed.
- OpenAI, Anthropic, and local adapters are known closed keys but are not executable in M25-3B.
- Provider model registry has no enabled rows seeded by M25-3B.
- Budget concurrency depends on retaining the transaction-scoped advisory-lock admission guard.
- The full backend suite has one accepted M21 E2E skip when `M21_E2E_DATABASE_URL` is not configured.

No live provider validation is implied by the current PASS state.

## M25-3 closure status

M25-3C and the M25-3D fake-provider controlled pilot are technically closed and pending the approved source-control commit. M25-3E is optional and unexecuted. This does not close the historical M23 live-provider HOLD EXTERNAL.
