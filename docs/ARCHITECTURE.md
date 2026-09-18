# Architecture

Education OS preserves the institutional learning loop:

`evidence → decision → action → outcome → institutional learning`

## Responsibility boundary

- Deterministic services calculate exact rules, permissions, validation, tenant scope, and command authorization.
- Statistical/read-model services calculate attendance, grades, risk values, projections, severity, and M22 signals.
- AI/provider components only explain, summarize, compare, and communicate bounded evidence.
- Humans control sensitive, irreversible, or broad-impact decisions.

Provider output is explanatory, never authoritative. It cannot calculate authoritative statistics, select tenant scope, grant permissions, authorize tools/actions, mutate domain data, or execute integrations.

## Agentic Control Plane

`authenticated request → principal context → agent/capability registry → policy engine → deterministic planner → closed Tool Gateway → typed domain adapter → Evidence Pack → budget admission → deterministic provider router → fixed adapter → strict parser → deterministic verifier → append-only audit → M18 lifecycle event`

Providers receive no arbitrary tool access. M25 remains a modular-monolith control plane, not a set of domain-specific agent runtimes.

Current deterministic L0 advisors remain `DETERMINISTIC_ONLY`:

| Advisor | Domain | Capability | Tool |
| --- | --- | --- | --- |
| `integration_run_advisor` | M24 | `integration.run.inspect` | `m24.integration_run.inspect` |
| `student_timeline_advisor` | M21 | `student.timeline.inspect` | `m21.student_timeline.inspect` |
| `institution_intelligence_advisor` | M22 | `intelligence.snapshot.inspect` | `m22.intelligence_snapshot.inspect` |

## Governed provider foundation

M25-3A defines code-owned `m25.evidence.v1`: typed, bounded, canonical, SHA-256 manifested, tenant/subject hashed, provenance preserving, PII minimized, and provider safe. Citation IDs such as `ev_01` are opaque; provider-facing context never exposes raw IDs merely to cite evidence. Raw packs are not persisted.

Prompt contracts are code-owned, versioned, and hashable. They combine immutable system rules, a bounded Evidence Pack, and typed intent. Evidence is untrusted data, never instruction.

M25-3B adds deterministic model routing and fake-only execution. The model registry is tenant-scoped/versioned with no credentials. Router inputs are principal context, policy, capability, evidence size, and budget—not client model/provider input.

## Provider-budget control

Provider invocation requires pre-admission. `agent_budget_events` is an append-only ledger with `RESERVED`, `CONSUMED`, and `RELEASED` events in `RUN`, `TENANT_DAY`, and `TENANT_MONTH` scopes. Money is integer micro-USD only.

Admission is atomic under transaction-scoped PostgreSQL advisory locks:

`pg_advisory_xact_lock(hashtextextended(...))`

The lock, exposure check, and RESERVED writes belong in one transaction. Do not replace this with mutable balances or remove it without an equally strong atomic guard. Verified baseline: two concurrent 60 micro-USD requests against 100 admit one and reject one; overspend is zero.

## First provider-backed L0 advisor

`integration_run_explainer` uses exactly `m24.integration_run.inspect`; it accepts only an integration-run UUID and the closed `SUMMARY`/`ERRORS`/`OUTCOME` intent. It remains useful with no model configuration through deterministic fallback. The controlled fake-provider pilot passed: valid opaque citations are accepted, while duplicate and fabricated citations fail closed before a provider result is accepted.
