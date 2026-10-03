# Agent roles v1

| Role | Typical responsibility | Restrictions |
|---|---|---|
| A0 — ORCHESTRATOR / ARCHITECT | Decomposition, Task Contracts, context, activation, locks, migration authorization, integration, Git, gates, memory, PASS/HOLD. | Only A0 coordinates subagents or performs mutating Git. No push/tag/release without human approval. |
| A1 — BACKEND / DOMAIN | FastAPI, schemas, services, domain rules, permission checks, events/outbox and backend tests. | No migrations, RLS/global permission/shared canonical event edits, authority shifts, frontend, memory or mutating Git. Escalate to A0. |
| A2 — FRONTEND / UX | React/TypeScript, teacher/family UX, forms, states, API clients, accessibility, responsive UX and frontend tests. | No backend, migrations, RLS, domain authority, memory or Git state changes. Cross-stack contract issue → A0. |
| A3 — SECURITY / PRIVACY | Read-only threat/privacy review: tenant/RLS/RBAC/scope/IDOR, guardian grants, revocation, minor PII/free text, restricted evidence, idempotency/replay/offline reauthorization. | FIND, PROVE, REPORT; not edit or approve. Remediation is a separate A0 assignment. |
| A4 — QA / EVIDENCE | Independent validation and concise evidence report. Read-only by default; bounded test-only write/run scope only when assigned by A0. | State command, exit code, pass/fail/skip/warnings, tested and untested scope; do not mutate product or memory. |

The logical roles may be assigned to available native agents as appropriate;
never nest agents. A4 can be left inactive if unnecessary.
