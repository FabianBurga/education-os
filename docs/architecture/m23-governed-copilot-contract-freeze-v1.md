# Education OS â€” M23 Governed Copilot Contract Freeze v1

Status: FROZEN FOR IMPLEMENTATION  
Milestone: M23 â€” Governed Copilot  
Baseline: M22 remote release `m22-institutional-intelligence-v0.22.0`  
Baseline commit: `0ca1aa2d92a8bb2bf72ba937c4e0e613438f2d12`  
Baseline database revision: `0026_m22_intel_read_boundary`

## 1. Purpose

M23 adds a governed institutional Copilot on top of Education OS's existing
authoritative operational data, M21 timeline/intervention capabilities, M22
institutional intelligence, authorization model, audit/event plane, and human
decision workflow.

M23 does not create an independent source of institutional truth.

The governing flow is:

`authorized request -> deterministic policy gate -> scoped evidence assembly ->
redaction/minimization -> governed model invocation -> structured validation ->
evidence-backed answer/proposal -> audit/provenance -> human decision`

The non-negotiable responsibility split is:

- AI may: detect, summarize, recommend, explain.
- Human must: verify, decide, approve, act.

## 2. Architectural invariants

1. No raw-database-to-LLM path.
2. No model provider may bypass Education OS authorization or RLS.
3. Model output is never authoritative operational truth.
4. A model may not directly execute domain mutations.
5. High-impact educational, disciplinary, welfare, or access decisions are
   human decisions.
6. Every substantive Copilot answer must be traceable to authorized evidence.
7. Deterministic policy gates run before and after every model invocation.
8. Existing M0-M22 domain services remain authoritative for mutations.
9. Existing tenant and actor scope can only be narrowed by M23, never widened.
10. M23 remains inside the modular monolith for v1.
11. M23 v1 adds no vector database and no embeddings requirement.
12. Hidden chain-of-thought is neither required nor persisted.

## 3. Actors and access contract

### SYSTEM_ADMIN

May use Copilot only inside an explicitly selected authorized organization /
institution context. System administration status alone does not create an
unbounded cross-tenant evidence scope.

### RECTOR

May use institution-wide advisory intelligence for the institution authorized
by current membership, permissions, and tenant context.

### ACADEMIC_COORDINATOR

May use institution-wide academic/advisory intelligence within the authorized
institution.

### TEACHER

May use Copilot only for students, courses, sections, signals, timeline items,
and intervention information already allowed by the teacher's existing
assignment/enrollment scope and sensitivity permissions.

### Out of scope for M23 v1

Direct Copilot access for STUDENT, GUARDIAN, and other roles is not enabled
unless a later frozen contract explicitly adds it.

## 4. Permission contract

M23 introduces explicit Copilot permissions rather than borrowing unrelated
console permissions:

- `copilot.use`
- `copilot.manage`
- `copilot.action.approve`

Initial role intent:

- SYSTEM_ADMIN: `copilot.use`, `copilot.manage`, `copilot.action.approve`
  inside explicit authorized tenant context.
- RECTOR: `copilot.use`, `copilot.action.approve`.
- ACADEMIC_COORDINATOR: `copilot.use`, `copilot.action.approve`.
- TEACHER: `copilot.use` only, with existing academic/student scope.
- Other roles: denied by default.

Permission possession never overrides tenant, student, course, section,
sensitivity, or domain-specific scope.

## 5. Governed context/evidence contract

The Copilot receives an evidence package assembled by Education OS, not an
arbitrary database connection.

Allowed evidence classes, when independently authorized, include:

- M22 institutional intelligence read models and priorities;
- M22 cohort/trend/intervention-health summaries for manager actors;
- M21 student timeline and intervention state;
- existing intelligence signals;
- attendance and academic facts exposed through authoritative domain/read
  services;
- institution policy/configuration that is explicitly approved for Copilot
  context;
- current actor/tenant/scope metadata required to enforce authorization.

Evidence must be represented by stable references containing enough metadata
to audit source, version/freshness, tenant, and scope.

## 6. Prohibited context

The evidence assembler must exclude:

- another tenant's data;
- secrets, API keys, JWTs, passwords, credentials, or connection strings;
- unrestricted Event Ledger payloads;
- raw operational tables merely because the application role can technically
  query them;
- sensitive free text when the current actor lacks the existing sensitivity
  permission;
- unrelated student/person PII;
- hidden system prompts or provider credentials;
- data outside the minimum necessary scope for the requested task.

## 7. Data minimization and PII boundary

Before provider invocation, Education OS must minimize and redact the evidence
package to the smallest authorized set sufficient for the request.

Stable internal identifiers may be used for provenance. Direct personal
identifiers should be omitted or pseudonymized when the task does not require
them.

A provider/model is eligible only when its configured data-handling policy is
approved for the deployment. Provider configuration must not weaken Education
OS tenant, privacy, retention, or audit requirements.

## 8. Deterministic pre-invocation policy gate

Before a model call, a deterministic gate must decide:

- actor is authenticated;
- tenant/institution context is explicit;
- `copilot.use` is present;
- requested intent is allowed;
- evidence classes are allowed for the actor;
- evidence instances are inside current scope;
- sensitivity rules pass;
- provider/model is enabled;
- prompt template and policy versions are enabled;
- quota/cost limit permits invocation.

Failure at this gate produces no model call.

## 9. Evidence assembler

The evidence assembler is an application service.

It may call authorized Education OS services/read models and must return a
structured evidence bundle. It must not hand an unrestricted SQL session or
generic repository to a model adapter.

Every evidence item must expose an audit-safe reference, evidence type,
freshness/version where applicable, and scope metadata.

## 10. Provider/model abstraction

M23 v1 must use a provider-neutral gateway.

Domain/application code must not depend directly on a specific vendor SDK.
Provider adapters sit behind one interface and return a normalized result.

The model registry records at least:

- provider key;
- model key;
- enabled/disabled status;
- capability class;
- policy eligibility;
- effective configuration version.

Secrets are never stored in audit records or prompts.

## 11. Prompt/version registry

Every invocation references a frozen prompt template version.

Prompt templates are controlled artifacts, not arbitrary user-provided system
instructions. User text is treated as request content, not privileged system
policy.

The registry records at least:

- prompt key;
- version;
- status;
- intended task/intent;
- compatible output schema;
- policy version.

## 12. Prompt-injection boundary

Retrieved institutional text is data, never trusted instructions.

The provider request must structurally separate:

- system governance instructions;
- user request;
- evidence.

Evidence cannot grant new tools, expand scope, change system policy, reveal
secrets, or override approval requirements.

M23 v1 has no unrestricted autonomous tool execution.

## 13. Structured output contract

Provider output must validate against an Education OS schema before it is
returned or persisted.

A valid advisory response contains at least:

- status;
- answer/summary;
- evidence references/citations;
- confidence/insufficiency state;
- policy/prompt/model provenance.

An invalid, uncited, out-of-scope, or policy-violating result is rejected or
converted to a safe refusal/insufficient-evidence response.

## 14. Evidence/citation contract

Substantive factual claims about institutional state must be supported by one
or more evidence references from the assembled authorized bundle.

M23 must not fabricate citations.

If evidence is insufficient, stale, conflicting, or outside scope, the
Copilot must say so rather than infer operational facts as certain.

## 15. Explainability contract

Education OS exposes concise user-facing rationale and evidence, not private
chain-of-thought.

The explanation must make clear:

- what authorized evidence was used;
- why the answer/recommendation follows at a high level;
- relevant uncertainty or freshness limits;
- what requires human verification.

## 16. Advisory-only boundary

Normal Copilot answers are read/advisory operations.

The model cannot directly:

- change a grade;
- change attendance;
- resolve a signal;
- open/close/modify an intervention;
- sanction a student;
- change enrollment, membership, role, permission, or tenant data;
- send an external communication;
- execute an integration;
- alter institutional policy.

## 17. Governed action-proposal contract

M23 may create structured action proposals, never direct actions.

A proposal must contain:

- proposed action type;
- target domain entity reference;
- human-readable reason;
- supporting evidence references;
- proposing Copilot run id;
- policy/prompt/model provenance;
- required approving permission;
- status.

Initial statuses:

- `PROPOSED`
- `APPROVED`
- `REJECTED`
- `EXECUTED`
- `FAILED`
- `EXPIRED`

Approval is a new human authorization event. Approval does not bypass the
target domain service's own authorization and validation.

Execution, when implemented, calls the existing authoritative domain service
under the approving human's current identity/context and re-checks permission
and scope at execution time.

## 18. High-impact decision rule

M23 must never autonomously decide or execute:

- disciplinary sanctions;
- academic promotion/failure decisions;
- welfare/psychological diagnosis;
- special-education placement;
- exclusion or access denial;
- high-impact intervention authorization;
- any equivalent consequential decision about a minor.

The Copilot may summarize evidence and propose considerations for an authorized
human decision-maker.

## 19. Audit/provenance contract

Every model invocation creates an auditable Copilot run record even when the
provider call fails after the pre-gate.

The audit/provenance record includes at least:

- run id;
- actor user id;
- organization/institution id;
- effective role/scope descriptor;
- normalized intent;
- policy version;
- prompt version;
- provider key and model key;
- evidence reference ids or immutable evidence manifest hash;
- request timestamp;
- completion timestamp;
- status;
- refusal/failure code when applicable;
- token/usage metadata when available;
- normalized cost metadata when available;
- output schema version;
- action proposal ids, if any.

Secrets and hidden chain-of-thought are never persisted.

## 20. Persistence contract

M23 v1 may introduce governed persistence for:

- model registry;
- policy versions;
- prompt versions;
- Copilot runs;
- evidence references/manifests;
- action proposals and human decisions.

All tenant-bearing M23 tables require tenant isolation and, where accessible by
the runtime application role, RLS/FORCE RLS consistent with Education OS
security architecture.

Audit/provenance history must not be silently rewritten by ordinary runtime
operations.

## 21. Events

M23 may emit canonical events after committed state transitions, such as:

- `copilot.run.completed`
- `copilot.run.refused`
- `copilot.action_proposal.created`
- `copilot.action_proposal.approved`
- `copilot.action_proposal.rejected`
- `copilot.action_proposal.executed`
- `copilot.action_proposal.failed`

Events follow the existing transactional outbox/event-plane pattern. Model
adapters do not publish directly to external systems.

## 22. API surface contract

The initial public application surface will live under `/api/v1/copilot`.

Frozen v1 intent:

- `POST /copilot/queries` â€” submit governed advisory query;
- `GET /copilot/runs/{run_id}` â€” retrieve authorized run/result/provenance;
- `GET /copilot/action-proposals` â€” list proposals in actor scope;
- `POST /copilot/action-proposals/{proposal_id}/approve` â€” human approval;
- `POST /copilot/action-proposals/{proposal_id}/reject` â€” human rejection.

Exact request/response schemas are implemented under this contract and must
preserve all authorization, evidence, audit, and approval invariants.

No generic arbitrary SQL, arbitrary tool invocation, or arbitrary prompt
execution endpoint is permitted.

## 23. Availability/failure contract

Provider failure must degrade safely.

If no eligible provider/model is available, M23 returns a deterministic
unavailable state; it must not bypass governance with an alternate unregistered
provider.

Timeouts, malformed provider output, schema failures, and policy failures are
distinguishable audit outcomes.

Operational truth remains available through normal Education OS surfaces even
when Copilot is unavailable.

## 24. Cost/quota contract

Model use is bounded by deterministic quotas/cost controls.

At minimum the governance layer supports limits by deployment and may support
institution/user dimensions.

A request over limit is rejected before model invocation and is auditable.

Cost controls never change authorization semantics.

## 25. Freshness contract

The evidence bundle carries freshness where the source supports it.

M22 `CURRENT` / `DELAYED` / `STALE` semantics are preserved. Copilot must not
present stale M22 intelligence as current.

## 26. Determinism and reproducibility contract

Model text itself is not assumed deterministic.

The deterministic/reproducible envelope is:

- actor and scope;
- normalized intent;
- evidence manifest;
- policy version;
- prompt version;
- provider/model version;
- output schema version;
- model invocation parameters allowed by policy.

This envelope is sufficient to explain which governed configuration produced a
result without persisting private chain-of-thought.

## 27. Security negative-testing contract

Every positive M23 authorization path requires corresponding negative tests,
including at least:

- wrong tenant;
- missing `copilot.use`;
- teacher outside assignment/student scope;
- teacher requesting manager-only evidence;
- sensitive evidence without permission;
- disabled provider/model;
- disabled prompt/policy;
- quota denied;
- malformed/uncited provider output;
- action approval without `copilot.action.approve`;
- execution after scope/permission changed;
- prompt-injection attempt through user text/evidence.

## 28. Controlled pilot scenarios

The M23 controlled pilot must include at least:

1. rector asks for top institutional risks and receives evidence-backed answer;
2. academic coordinator asks for deteriorating cohorts;
3. teacher asks about an assigned student;
4. teacher is denied an out-of-scope student;
5. teacher is denied institution-wide manager evidence;
6. wrong-tenant request denied before model call;
7. sensitive evidence redacted/denied;
8. insufficient evidence produces explicit insufficiency;
9. stale intelligence is labeled stale;
10. provider unavailable produces safe deterministic failure;
11. malformed provider output rejected;
12. prompt-injection text cannot expand scope;
13. every answer carries valid evidence references;
14. action proposal created without executing mutation;
15. unauthorized approval denied;
16. authorized human approval audited;
17. execution re-checks target-domain authorization;
18. policy/prompt/model versions recorded;
19. cost/quota denial occurs before provider call;
20. audit trail reconstructs run envelope without chain-of-thought.

## 29. Out of scope for M23 v1

Explicitly excluded:

- autonomous agents with unrestricted tools;
- autonomous high-impact decisions;
- autonomous student discipline;
- generic internet browsing by the model;
- arbitrary SQL generation/execution;
- direct provider access to the database;
- vector database requirement;
- embeddings requirement;
- cross-institution benchmarking;
- district-level Copilot;
- student/guardian conversational assistant;
- provider training/fine-tuning on institutional production data;
- Integration Hub/external system orchestration;
- replacement of deterministic M22 intelligence rules with opaque ML.

## 30. Implementation sequence and gates

### M23-1 â€” Discovery + Contract Freeze
- discovery evidence;
- this frozen contract;
- contract tests;
- dedicated M23 branch.

### M23-2 â€” Governed Context / Evidence Foundation
- permission foundation;
- policy/prompt/model registries;
- Copilot run/evidence persistence;
- RLS/FORCE RLS;
- evidence assembler;
- deterministic pre-gate.

**Formal Gate 1:** secure governed foundation.

### M23-3 â€” Provider Gateway + Advisory Answers
- provider-neutral adapter;
- structured output validation;
- citations/provenance;
- post-invocation policy gate;
- safe failure and cost accounting.

### M23-4 â€” Governed API / Decision Surfaces
- governed query API;
- run retrieval;
- actor-specific scope semantics.

**Formal Gate 2:** runtime authorization + advisory semantics.

### M23-5 â€” Human-Governed Action Proposals
- proposal lifecycle;
- approval/rejection;
- execution through existing domain services;
- re-authorization at execution time.

### M23-6 â€” Controlled Pilot + Impact / Security / Release
- synthetic controlled pilot;
- prompt-injection negative tests;
- tenant/scope negatives;
- impact regression;
- release evidence.

**Formal Gate 3:** release authorization.

## 31. Release criteria

M23 may be released only when:

- M22 release baseline remains intact;
- no model/provider can bypass tenant/scope authorization;
- no raw DB-to-model path exists;
- every substantive answer is evidence-backed or explicitly insufficient;
- every invocation is auditable with policy/prompt/model/evidence provenance;
- high-impact actions remain human decisions;
- action execution reuses authoritative domain services and re-authorization;
- provider failure is safe;
- negative security tests pass;
- full repository regression passes;
- controlled pilot passes with synthetic data;
- source, DB, tag, and evidence gates are clean.

## 32. Frozen decision

M23 v1 is a governed advisory and action-proposal layer over Education OS.

It is not an autonomous decision-maker, not an alternate authorization system,
not a direct database agent, and not a replacement for deterministic
institutional intelligence.

Implementation may refine internal class/table names, but it must not violate
the behavioral, security, privacy, evidence, audit, or human-approval contracts
frozen above without a new explicit contract revision.

## Appendix A â€” M23-1 discovery evidence (non-normative)

This appendix records the repository discovery evidence used when freezing
the contract. It does not expand authorization by itself.

- Python modules scanned: 166
- Migrations scanned: 26
- Relevant tests discovered: 56
- Backend AI/LLM-related files discovered: 85
- Backend governance-related files discovered: 89
- Roles discovered: ACADEMIC_COORDINATOR, GUARDIAN, RECTOR, STUDENT, SYSTEM_ADMIN, TEACHER

Top candidate integration files from discovery:
- `docs/architecture/m22-intelligence-contract-freeze-v1.md` (discovery score 92)
- `M21_TECHNICAL_SPEC_V1.md` (discovery score 75)
- `.venv/Lib/site-packages/sentry_sdk/consts.py` (discovery score 64)
- `docs/architecture/m22-api-decision-surfaces-contract-v1.md` (discovery score 59)
- `.venv/Lib/site-packages/playwright/async_api/_generated.py` (discovery score 55)
- `.venv/Lib/site-packages/playwright/sync_api/_generated.py` (discovery score 55)
- `.venv/Lib/site-packages/pydantic_extra_types/mime_types.py` (discovery score 53)
- `docs/architecture/m22-0025-intelligence-foundation-design-v1.md` (discovery score 52)
- `backend/tests/unit/test_m21_suggestion_full_security_e2e_contract.py` (discovery score 50)
- `.venv/Lib/site-packages/pygments/lexers/_cocoa_builtins.py` (discovery score 45)
- `docs/releases/m14-finance-billing-core-v0.14.0.md` (discovery score 45)
- `.venv/Lib/site-packages/sentry_sdk/integrations/litellm.py` (discovery score 43)
- `backend/alembic/versions/0021_m21_intervention_core.py` (discovery score 43)
- `.venv/Lib/site-packages/pygments/lexers/_lilypond_builtins.py` (discovery score 42)
- `.venv/Lib/site-packages/pygments/lexers/_lasso_builtins.py` (discovery score 41)
- `.venv/Lib/site-packages/pygments/lexers/lisp.py` (discovery score 41)
- `backend/alembic/versions/0023_m21_intervention_suggestions.py` (discovery score 41)
- `.venv/Lib/site-packages/pygments/lexers/matlab.py` (discovery score 40)
- `backend/tests/unit/test_m21_suggestion_model_contract.py` (discovery score 39)
- `.venv/Lib/site-packages/sentry_sdk/integrations/langchain.py` (discovery score 38)
- `backend/alembic/versions/0020_m21_student_timeline.py` (discovery score 38)
- `backend/alembic/versions/0024_m21_projection_boundary.py` (discovery score 37)
- `backend/app/modules/interventions/models.py` (discovery score 37)
- `backend/tests/unit/test_m22_intelligence_foundation_migration_contract.py` (discovery score 37)
- `docs/releases/m13-communications-center-v0.13.0.md` (discovery score 37)
- `.venv/Lib/site-packages/pygments/lexers/_php_builtins.py` (discovery score 36)
- `.venv/Lib/site-packages/sentry_sdk/tracing_utils.py` (discovery score 36)
- `backend/alembic/versions/0006_m5_automation_engine.py` (discovery score 36)
- `backend/app/modules/intelligence/projector.py` (discovery score 36)
- `.venv/Lib/site-packages/pygments/lexers/_openedge_builtins.py` (discovery score 35)

Discovery evidence SHA-256:

`5dc3598e0284735be5c6cd2f4096f046c6e8af7406d1dd7987c030cb7781d478`
