# Technical Decisions

## Tenant governance

Tenant identity is derived from the authenticated principal and applied to PostgreSQL session context. Protected records use ENABLE RLS and FORCE RLS. Application authorization uses effective permissions, never role-name checks.

## Append-only control-plane records

M25 definitions/policies are versioned configuration. Runs, steps, tool calls, evidence references, events, provider calls, and budget events are append-only. Runtime grants are deliberately narrow.

At database revision `0036_m25_run_explainer`:

| Table | Runtime grant |
| --- | --- |
| `agent_model_registry` | SELECT |
| `agent_provider_calls` | SELECT, INSERT |
| `agent_budget_events` | SELECT, INSERT |

No runtime UPDATE or DELETE is allowed. Provider/budget records have composite tenant-aware foreign keys and RLS insert checks.

## Provider governance

Provider adapter keys are closed: `fake`, `openai`, `anthropic`, `local`. In M25-3B only `fake` executes, in-process and without network. Live adapter keys are known future identifiers, not executable transports.

Normalized failures are closed: `PROVIDER_AUTH`, `PROVIDER_RATE_LIMIT`, `PROVIDER_TIMEOUT`, `PROVIDER_UNAVAILABLE`, `PROVIDER_INVALID_RESPONSE`, `PROVIDER_BUDGET_EXCEEDED`, `PROVIDER_POLICY_BLOCK`, `PROVIDER_CONTEXT_TOO_LARGE`, and `PROVIDER_FALLBACK_EXHAUSTED`.

Provider audit stores only hashes, token/cost metadata, latency, normalized outcome/error, and fallback lineage. It never stores credentials, raw prompts, raw responses, or raw provider error bodies.

## M25-3C decision

The first provider-backed agent is `integration_run_explainer`, L0 only. It will use `integration.run.explain`, M24 `m24.integration_run.inspect` evidence, typed `integration_run_id` plus a closed focus enum, strict structured output, deterministic verifier, and mandatory deterministic fallback. The existing `integration_run_advisor` remains unchanged.

## Pre-code rule

Before making code changes, document and verify current state. Read `docs/AI_CONTEXT.md`, `docs/PROJECT_HANDOFF.md`, `docs/ARCHITECTURE.md`, `docs/CURRENT_STATE.md`, and this document. Verify Git HEAD/status and Alembic source/current revisions. Reconcile any mismatch before changing application code.

## M25-3C pilot validation

`integration_run_explainer` is L0 only. It uses `integration.run.explain`, M24 `m24.integration_run.inspect`, typed `integration_run_id`, and the closed `SUMMARY`/`ERRORS`/`OUTCOME` focus enum. Provider use is optional and deterministic fallback is mandatory.

The M25-3D fake-provider pilot passed with `0f706b7f-de79-4bde-ba15-a3b0795bc67a`: one in-process fake call, one verified opaque citation, 30 micro-USD consumed after 1,000 micro-USD reservation per scope, no duplicate replay work, and no domain mutation. M25-3E live-provider validation remains optional and unexecuted.
