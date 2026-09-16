# Education OS — AGENTS.md

## Project identity
Project: Education OS — Institutional Intelligence & Action Platform

Core differentiator:
evidence → decision → action → outcome → institutional learning

This repository is a security-sensitive, multi-tenant institutional platform.
Correctness, tenant isolation, auditability, migration safety, and evidence-backed
behavior take priority over speed.

## Current authoritative baseline
Branch:
m23-governed-copilot

Current source commit:
d963a55520bf5914d42bb07afe2b3b715874f583

Current Alembic revision:
0030_m23_action_proposals

Current phase:
M23-6 Controlled Pilot + Release

Latest known full regression:
571 passed, 1 skipped, 4 warnings

Latest M23-5 install evidence:
C:\Users\USER\Downloads\M23_5_ACTION_PROPOSALS_REPORT_V4.json

Latest M23-5 install report SHA256:
4b990119e36bfad6ddb16aade1502f35c5f7c0296db2efde791394c1a13c8197

M23-5 Runtime Formal Gate:
PASS

M23-5 closure source commit:
d963a55520bf5914d42bb07afe2b3b715874f583

M23-5 runtime gate evidence:
C:\Users\USER\Downloads\M23_5_RUNTIME_FORMAL_GATE_REPORT_V1.json

M23-5 runtime gate report SHA256:
9533e6a990418f113a44bc26c5aa65e14e3b4fdb0563851d25d4a8ac8431a4ad

## Repository environment
Primary repository:
C:\Users\USER\Downloads\Education_OS_M0_Foundation_Package_v0.1\Education_OS_M0_Foundation_Package_v0.1

Python:
.venv\Scripts\python.exe

Runtime DB:
postgresql+psycopg://education_app:education_app_dev@127.0.0.1:5432/education_os

Owner DB:
postgresql+psycopg://education_owner:education_owner_dev@127.0.0.1:5432/education_os

PostgreSQL Docker container:
education_os_m0_foundation_package_v01-postgres-1

PostgreSQL image:
postgres:17

Remote:
FabianBurga/education-os

## Product architecture
Education OS must never become:
raw DB → LLM → decision

Trusted architecture:
authorized request
→ deterministic policy gate
→ scoped evidence assembly
→ redaction/minimization
→ governed model invocation
→ structured validation
→ evidence-backed answer/proposal
→ audit/provenance
→ human decision
→ authoritative domain service

Operational truth must remain in existing domain services and governed read models.

## Roadmap status
M0–M7: FOUNDATION
M8–M16: OPERATIONAL PRODUCT
M17: RELIABILITY
M18: EVENT PLATFORM
M19: CONTROL PLANE
M20: OFFLINE-FIRST TEACHER PWA
M21: STUDENT TIMELINE + INTERVENTION ENGINE
M22: INSTITUTIONAL INTELLIGENCE + EARLY WARNING
M23: GOVERNED COPILOT
M24: INTEGRATION HUB
M25+: SCALING
M26+: LEARNING

## M23 frozen architecture
M23 Governed Copilot sits only on trusted M21/M22 evidence/read models.

Non-negotiable:
1. No raw DB-to-LLM path.
2. Provider cannot bypass auth/RLS.
3. Model output is not authoritative truth.
4. Provider cannot execute domain mutations.
5. High-impact decisions require a human.
6. Substantive answers must be traceable to authorized evidence.
7. Deterministic gates run before and after model invocation.
8. M0–M22 services remain authoritative for mutations.
9. Scope may narrow but never widen.
10. Keep modular-monolith architecture in v1.
11. No vector DB requirement for M23.
12. Hidden chain of thought is neither required nor persisted.

## M23 role model
SYSTEM_ADMIN:
- copilot.use
- copilot.manage
- copilot.action.approve

RECTOR:
- copilot.use
- copilot.action.approve

ACADEMIC_COORDINATOR:
- copilot.use
- copilot.action.approve

TEACHER:
- copilot.use

STUDENT / GUARDIAN / other roles:
out of scope for M23 v1.

Manage and approve are separate concepts.
Do not collapse them.

## M23-5 frozen action contract
Only one governed action type exists in M23-5 v1:

CREATE_INTERVENTION

Authoritative domain service:
app.modules.interventions.service.create_intervention

Authoritative payload schema:
app.modules.interventions.schemas.InterventionCreate

Required domain permission:
intervention.create

Human approval permission:
copilot.action.approve

Public surfaces:
GET  /api/v1/copilot/action-proposals
POST /api/v1/copilot/action-proposals/{proposal_id}/approve
POST /api/v1/copilot/action-proposals/{proposal_id}/reject

There is intentionally NO public action-proposal creation endpoint.

Explicitly excluded in M23-5 v1:
- financial mutation
- communication publication/send
- intervention assign
- intervention transition
- intervention resolve
- intervention close
- intervention cancel
- arbitrary SQL
- arbitrary service invocation
- provider-selected tool execution
- free-form domain mutation

Action lifecycle:
PROPOSED
→ APPROVED / REJECTED
→ EXECUTED / FAILED

Proposal history:
APPEND-ONLY

Lifecycle events:
APPEND-ONLY

Current proposal status:
DERIVED FROM LATEST EVENT

Provider execution:
FORBIDDEN

Human approval:
REQUIRED

## Current M23-5 DB contract
Migration:
0030_m23_action_proposals

Tables:
- copilot_action_proposals
- copilot_action_proposal_events

Both tables:
- FORCE ROW LEVEL SECURITY
- runtime grants are SELECT + INSERT only
- no UPDATE
- no DELETE

Proposal state must not be represented as a mutable status column.
State must be derived from lifecycle events.

PostgreSQL trigger enforces valid event transitions.

## Current task
The immediate task is to run and close the M23-5 Runtime Formal Gate.

A prior gate script may exist under Downloads, but do not assume the harness is correct.
Run it, inspect failures, and distinguish carefully between:
- product defect
- harness defect
- historical test evolution issue
- environment/configuration issue
- DB/RLS issue
- migration issue
- HTTP runtime issue

Fix the smallest valid cause.

## Required M23-5 Runtime Formal Gate behavior
The final runtime gate must prove, with no persistent residue:

1. GET action proposals is operational.
2. approve endpoint is operational.
3. reject endpoint is operational.
4. no public create endpoint exists.
5. teacher cannot approve/reject.
6. teacher cannot see another actor's proposal unless policy explicitly allows it.
7. wrong tenant is denied.
8. nonexistent/invisible proposal resolves as 404 where appropriate.
9. student scope widening is denied.
10. unbacked citations are denied.
11. SYSTEM_SUGGESTION origin is enforced for governed intervention proposals.
12. PROPOSED → REJECTED works.
13. PROPOSED → APPROVED → EXECUTED works.
14. duplicate decisions are denied.
15. execution reauthorizes through authoritative intervention service.
16. intervention is actually created inside controlled fixture.
17. canonical event student.intervention.opened is emitted.
18. canonical event metadata includes human_authorized=true.
19. no real provider/network model call occurs.
20. all fixture data is rolled back.
21. no persistent transactional residue remains.
22. directed security regression passes.
23. full repository regression passes.
24. working tree remains clean after the gate.

## Engineering rules
These rules are mandatory.

### Git
- Never force-push.
- Never rewrite Git history.
- Never use git reset --hard unless explicitly approved by the human.
- Never delete branches unless explicitly approved.
- Never push or create release tags without explicit human approval.
- Formal gates should end with a clean working tree.
- Do not commit generated reports unless intentionally part of the release contract.

### Alembic / database
- Never rewrite an already committed migration.
- Harden forward with a new migration if DB behavior must change.
- Alembic revision IDs must remain <= 32 chars.
- Never downgrade unless the current run itself upgraded that revision and rollback is necessary.
- Do not downgrade a valid milestone to repair a report/harness issue.
- PostgreSQL CHECK constraints must account for SQL three-valued logic explicitly.
- Preserve FORCE RLS on protected tables.
- Prefer 127.0.0.1 instead of localhost in automation scripts.

### Security
- Never weaken a security requirement or test merely to get PASS.
- Distinguish compatibility-test evolution from real security-test weakening.
- Tenant scope must never widen.
- Invisible cross-tenant objects should return 404 where the existing contract requires invisibility.
- Provider cannot bypass application authorization or RLS.
- No unrestricted table access for the model/provider.
- No secrets, system prompts, provider credentials, raw provider payloads, or hidden chain-of-thought in user-facing/audit payloads.
- Append-only registries/history must remain append-only.
- Runtime lifecycle rows may only use precisely bounded mutation if the contract requires it.
- Manage permission and approve permission are distinct.

### Testing
- Before full regression, run:
  1. py_compile on touched Python
  2. targeted Ruff
  3. contract/unit tests for changed modules
  4. directed security regression
  5. full pytest
- Do not use global `ruff --fix`.
- If Ruff repair is needed, scope it to exact rules and exact files.
- Historical tests must evolve with frozen architecture; do not preserve a "future route must not exist" assertion after that route becomes part of a later frozen milestone.
- HTTP-runtime security must be verified with real FastAPI/TestClient behavior, not only static source checks.
- Provider tests must use fake/injected gateways; no real network/token spend for tests.
- Do not rely on a rich pre-existing pilot dataset if a controlled transactional fixture can prove the contract.

### Harnesses / PowerShell
- Treat harness bugs separately from product bugs.
- Native command success is determined by exit code, not stderr text.
- Alembic INFO on stderr is normal.
- Keep stdout and stderr handling robust.
- Do not use brittle fixed-offset parsing for git porcelain.
- Do not use unsafe multiline Python via PowerShell `python -c`; write a temporary .py file for complex logic.
- Never call `.Trim()` on a possibly null value without checking.
- Do not use PowerShell reserved `$Args` as a custom parameter name.
- Validate all patch assumptions before writing.
- Avoid brittle regex when AST or exact-token checks are safer.
- When exact byte identity matters, SHA-gate it.
- If a product commit and migration succeeded but only report emission failed, use a non-mutating post-commit finalizer; do not rollback a valid product milestone.

### Runtime transactions
- Controlled formal-gate fixtures should be wrapped so all test data is rolled back.
- Verify before/after counts or equivalent deterministic residue checks.
- Domain execution in M23 action proposals must remain bounded to create_intervention.
- Human APPROVED state must be persisted before execution attempt.
- Domain execution must run under the approving human's authorization context.
- EXECUTED/FAILED must follow APPROVED only.

## M23 completed milestones
M23-1:
Discovery + Contract Freeze — COMPLETE

M23-2:
Context/Evidence Foundation — COMPLETE
DB revision: 0027_m23_copilot_foundation

Formal Gate 1:
PASS

M23-3:
Provider Gateway + Advisory — COMPLETE
DB revision: 0028_m23_advisory_answers

M23-4:
Governed API — COMPLETE

Formal Gate 2:
PASS

Contract hardening baseline:
source:
9f2fa6232b4538a014d8c7940786efdb65b04aa8
DB:
0029_m23_contract_hardening

M23-5:
Action Proposals + Runtime Formal Gate — COMPLETE

M23-5 install source:
a955a633d1c2a3b5574a87a7b95eee105f910ded

M23-5 closure source:
d963a55520bf5914d42bb07afe2b3b715874f583

M23-5 DB:
0030_m23_action_proposals

M23-5 Runtime Formal Gate:
PASS

M23-5 closure report:
C:\Users\USER\Downloads\M23_5_RUNTIME_FORMAL_GATE_REPORT_V1.json

M23-5 closure report SHA256:
9533e6a990418f113a44bc26c5aa65e14e3b4fdb0563851d25d4a8ac8431a4ad

## M23-6 target
Do not begin M23-6 until the M23-5 Runtime Formal Gate is PASS.

M23-6 responsibilities:
- controlled pilot
- cross-role runtime proof
- security verification
- no provider bypass
- no scope widening
- release evidence
- Formal Gate 3
- release preparation
- annotated release tag only after explicit human approval

## Coding behavior
When a command/test fails:

1. Capture the exact failure.
2. Identify whether it is product, harness, environment, historical-contract, or data-fixture related.
3. Inspect the actual source before editing.
4. Make the smallest valid change.
5. Re-run targeted checks.
6. Re-run directed regression.
7. Re-run full regression when milestone-level behavior is affected.
8. Do not hide failures.
9. Do not reduce assertions merely to obtain green tests.
10. Preserve all frozen contracts unless a new milestone explicitly supersedes them.

## Human approval boundaries
Ask before:
- git push
- git tag
- release publication
- deleting branches
- destructive DB operations
- docker volume removal
- operating outside the Education OS workspace
- changing production/external credentials
- making real provider calls that consume tokens
- changing frozen architectural contracts

Routine local code edits, tests, Ruff, local Git inspection, DB inspection, controlled local migration execution, and rollback-contained fixtures may proceed inside the workspace when consistent with these rules.
