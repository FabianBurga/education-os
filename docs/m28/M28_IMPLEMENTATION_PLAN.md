# M28 implementation plan and ASTRA/Luna handoff

## Baseline and constraints

M28-0 froze scope on published M27 tag at
`8af4557ee77d04adb2cb20d5994684268aacd194`. Branch:
`m28-operational-adoption-core`. M28-1 and M28-2 are CLOSED / PASS; M28-3 is
CLOSED / PASS on migration `0045_m28_academic_permissions`. M28-4 onward remain
NOT STARTED.

Read [scope](M28_SCOPE.md), [inventory](M28_CAPABILITY_INVENTORY.md),
[domain](M28_DOMAIN_BOUNDARIES.md), [security](M28_SECURITY_BOUNDARY.md) and
[events](M28_EVENT_MODEL.md) before implementation. Keep the modular monolith,
existing domain modules, React shell/components, TanStack Query/Router and
Vitest. No new design system, state framework, worker, Redis or parallel SIS.

Every migration below is a plan, not an existing revision, except completed
M28-1 revision 0043, M28-2 revision 0044 and M28-3 revision 0045. Future
revisions follow 0045; choose <=32-character IDs. Never
reserve several empty migrations, edit 0001–0042, or apply schema during M28-0.
Physical receipt/history/version design is Luna's bounded implementation
choice subject to the frozen behavior and ASTRA security acceptance.

## M28-1 — Permission-safe student record — CLOSED / PASS

- Goal delivered: explicitly permissioned institutional student lookup and
  bounded profile maintenance, without new identity/enrollment authorities.
- Backend delivered: operation gates on M1 student endpoints, bounded keyset
  read API, minimized DTOs, strict input schemas, scoped ID lookup, optimistic
  update conflict, idempotent duplicate create, active-enrollment status guard,
  atomic audit/M18 outbox. Catalog migration 0043 adds `students.read`,
  `students.manage`, and the M24-required `enrollments.manage`; it grants no
  permissions to roles automatically. M24 apply requires integration, student,
  and enrollment permissions while using the same canonical services.
- Frontend delivered: existing React/TanStack workspace navigation and a
  responsive list/detail/edit view selected by effective permissions. Loading,
  empty, denied, not-visible, validation, conflict, and generic server/network
  states are bounded and do not expose raw errors.
- No schema tables, RLS policy changes, Student copies, guardian linking, Person
  edits, enrollment lifecycle, or placement were added. Existing M0-M3 models
  and M24 import authority remain canonical. Details: [M28 student record](M28_STUDENT_RECORD.md).
- Evidence: 749 backend passed, 1 opt-in M21 E2E skipped, 0 failed; 71 frontend
  tests, typecheck, production build, changed-file Ruff, py_compile, and Alembic
  passed. M1/M2/M3/M18/M24 directed regression: 71 passed. Full backend ran
  once after directed PASS.
- Dependencies: M28-0 scope/security freeze.
- Stop boundary respected: M28-3 academic setup remains NOT STARTED.

## M28-2 — Enrollment lifecycle — CLOSED / PASS

- Goal delivered: canonical M1 enrollment lifecycle and history without a
  parallel table. Exact same-period create replay and same-command transition
  replay do not duplicate domain mutations, audit, or canonical events.
- Backend: bounded PENDING/ACTIVE create; PENDING->ACTIVE/CANCELLED;
  ACTIVE->WITHDRAWN/COMPLETED; explicit WITHDRAWN->ACTIVE reactivation that
  first preserves the previous interval in audit/event evidence. TRANSFERRED
  is rejected. Dates are period-bounded; active placement closes atomically
  for withdrawal. A row lock and expected revision arbitrate competitors.
- Permissions: 0044 adds the frozen `enrollments.read` catalog entry without
  role grants. Reads require enrollments.read; mutations require the existing
  enrollments.manage. Tenant/institution derives from CurrentPrincipal and
  role permission association must belong to that institution.
- Frontend: student detail exposes enrollment create/read/history and only
  server-provided next actions; API refetches after commands and on 409.
- Migration: `0044_m28_enrollment_read`, additive and forward-only. Required
  because the frozen M28 security contract separated enrollment reads from
  student-record reads while 0043 had seeded only enrollments.manage. No table,
  RLS policy, historical migration, or automatic grant was changed.
- Evidence: focused M1/M18/M24/M28-1 + M28-2 PostgreSQL/RLS suite, concurrency,
  idempotency, transaction rollback, React tests/typecheck/build, Ruff,
  `py_compile`, Alembic and diff checks. Full backend suite: NO; this slice
  changes only the enrollment service boundary/catalog entry, and directed
  regressions passed.
- Details: [M28 enrollment](M28_ENROLLMENT.md).
- Dependencies: M28-1; existing periods/placements only.
- Stop boundary: no academic setup, placement transfer, attendance or results.

## M28-3 — Academic structure operations — CLOSED / PASS

- Goal delivered: operationally maintain existing M1/M2 periods, levels,
  grades, sections, subjects, curriculum links, course offerings and bounded
  teaching assignments without parallel authority tables.
- Backend: effective `academics.read`, `academics.manage`, and `academics.assign`
  checks; principal-scoped reads; strict input schemas; institutional reference
  validation; period PLANNED→ACTIVE→CLOSED with active-enrollment close guard;
  atomic M1/M2 event/outbox and audit for touched writes. Generic entity edits
  were not added because existing entities lack revision/history semantics.
- Frontend: existing React workspace now has capability-driven setup for periods,
  levels/grades, subjects, sections, offerings and separately authorized teacher
  assignment creation; server refetch is authoritative.
- Migration: `0045_m28_academic_permissions` only adds the three permission
  catalog keys and makes no role grants; no table or RLS change. Required because
  the frozen security contract calls for explicit academic read/manage/assign
  capabilities and M1/M2 legacy routes had only generic staff guards.
- Evidence: 49 directed backend tests passed, including real foreign-tenant
  references, M2 FORCE-RLS metadata, M1/M18/M24/M28-1/2 compatibility and
  outbox-failure rollback. Focused frontend tests and typecheck passed;
  production build passed with existing dynamic-import/chunk-size warnings.
  Changed-file Ruff, `py_compile`, Alembic and diff-check passed. Full backend
  was not required because no shared auth/RLS/transaction primitive changed.
- Details: [M28 academic structure](M28_ACADEMIC_STRUCTURE.md).
- Stop boundary respected: no student placement transfer/roster lifecycle,
  attendance, assessment/results or timetable optimization; these remain later
  slices (M28-4+).

## M28-4 — Placement and teacher roster continuity — CLOSED / PASS

- Goal delivered: initial placement, atomic same-campus/period section transfer,
  retained placement intervals and derived institutional/teacher rosters using
  the M2 authorities only.
- Backend: enrollment row lock and expected-placement check arbitrate competing
  transfers; exact replay does not duplicate event/audit; the existing unique
  ACTIVE placement index remains authoritative. Date-valid rosters exclude
  inactive enrollment/profile/section/period. Transfers that strand later
  attendance or dated/undated grade evidence are rejected. Existing teacher
  assignments can be ended through a locked expected-state command with audit
  and `teaching.assignment.updated`; ended assignments lose roster access.
- Frontend: student detail presents placement history and an authorized,
  confirmed placement/section-transfer form; academic structure provides a
  bounded section roster. Existing Teacher Console remains the assigned-course
  roster UI. All mutations refetch server state.
- Migration: NONE. Existing placement dates/status, tenant constraints, RLS/
  FORCE RLS and partial unique active-placement index suffice. Revisions
  0001–0045 are unchanged.
- Security/evidence: effective academics.assign/read plus student/enrollment
  read boundaries; principal institution predicates; teacher visibility depends
  on an active date-valid assignment. PostgreSQL test verifies concurrent
  A→B/A→C transfer (one 200, one 409), replay, current roster, teacher
  authorization/revocation, unchanged enrollment state, foreign-object 404 and
  transactional rollback on outbox failure.
- Validation: 56 directed backend tests passed across M1/M2/M10/M18/M24/
  M28-1/2; 14 focused frontend tests passed; frontend typecheck/build, changed
  file Ruff, `py_compile`, Alembic and diff-check passed. Full backend was not
  required because no shared authorization/RLS/outbox primitive or cross-domain
  schema changed. The production build retains the pre-existing Vite
  dynamic-import/chunk-size warning.
- Details: [M28 placement and roster](M28_PLACEMENT_ROSTER.md).
- Stop boundary respected: no attendance correction, assessment/result entry or
  grade workflow. M28-5 remains NOT STARTED.

## M28-5 — Attendance correction and offline evidence — CLOSED / PASS

- Goal: teacher records and corrects one session safely online/offline, with
  one logical canonical fact per successful change.
- Backend: shared attendance transaction/target locking, history/reason/revision,
  consistent roster/date checks, canonical student event alongside existing M20
  sync event. Keep ATTENDANCE_MARK protocol, receipts and batch result vocabulary.
- Frontend: use existing teacher PWA; show pending/replayed/conflict/rejected
  state and require explicit conflict resolution; no optimistic confirmed fact.
- Migration: conditional receipt/revision support for online writers; M20 table
  and frozen protocol remain usable. No second offline engine.
- Security: reauthorize on replay and apply; revoke teacher while offline,
  expired snapshot, tenant/user cache isolation, historical correction permission.
- Tests: online-vs-offline race, double submit, first mark/correction/no-op,
  transaction failure, revoked scope; M3/M10/M18/M20/M21 attendance regression,
  existing `teacher-pwa.test.ts` plus focused conflict flows.
- Dependencies: M28-4.
- Full backend suite: NO here; required at M28-7 after continuity consolidation.
- Stop: attendance only; no offline grade entry or new sync queue technology.
- Closure: attendance online/offline, authorization, conflict/idempotency, and
  M18-to-M21 continuity gates passed on migration `0046_m28_attendance_perms`.
  The M21 E2E fixture lookup was corrected to discover tenant fixtures under
  the owner role; all mutations and projection work ran through runtime roles
  in rollback-contained transactions. Focused M28/M21 integration regression:
  8 passed, 0 skipped. Frontend focused tests, typecheck, production build,
  changed-file Ruff/py_compile, Alembic head/current, and diff-check passed.

## M28-6 — Assessment and results operations — CLOSED / PASS

- Goal delivered: authorized assessment definitions and student results remain
  in M3; result corrections preserve prior evidence and distinguish zero from
  missing.
- Backend: operation-specific academic permission checks for institutional
  actors; M10 teacher permission plus current assignment/offering/roster
  validation; bounded assessment lifecycle; finite `NUMERIC(8,3)` scores,
  assessment maximum validation and explicit status/score semantics. Operation
  replay, expected revision, row locks, audit history and canonical outbox event
  are transactionally coherent. No parallel authority or migration was needed.
- M21 diagnosis: the installed FORCE-RLS INSERT check was correct. The test's
  suffixed synthetic role passed `admin.console.access` but did not satisfy the
  SELECT visibility policy used by `INSERT ... RETURNING id`. The fixture now
  uses the recognized M21 role key with only the required projector/read grants.
  The runtime projector and policy were not changed. Same-tenant projection,
  teacher/unprivileged denial and mismatched-institution denial are covered.
- Frontend: extended the established M10 Teacher Console assessment/results
  surface; no parallel gradebook. M11 M12 M3 M10 contract tests preserve their
  existing route boundaries. No dedicated React assessment-result test exists.
- Migration: NONE. Existing M3 structures, audit log and outbox provide the
  required authority/history/event behavior; revisions 0001-0046 are unchanged.
- Validation: directed M28/M3/M10/M18/M20/M21 regression 88 passed; backend
  suite 768 passed, 2 skipped (the opt-in `M21_E2E_DATABASE_URL` attendance E2E
  tests), 0 failed. The new result-to-M18-to-M21 test executed and passed with
  0 skips. Frontend tests 76 passed; typecheck and production build passed;
  Ruff, `py_compile`, Alembic heads/current and diff-check passed. Full backend
  ran once after the shared M3 result authority change. Existing build chunk
  size/dynamic-import and test JWT/pytest-marker warnings remain.
- Details: [M28 assessment and results](M28_ASSESSMENT_RESULTS.md).
- Stop boundary respected: no weighted/final-grade calculation, GPA,
  report-card engine, promotion, graduation or progression logic.

## M28-7 — Operational history and evidence continuity — CLOSED / PASS

- Goal delivered: consolidated authority, event, projection, provenance,
  freshness, privacy and human-control boundaries across M28 and existing
  M18/M21/M22/M27. Existing IDs and services remain authoritative; no feature
  dashboard, composed history API, or new projection was introduced.
- Evidence: [M28 operational continuity](M28_OPERATIONAL_CONTINUITY.md)
  maps each authority and consumer. Focused cross-milestone regression passed
  60 tests; both opt-in M21 online/offline attendance E2E tests passed against
  the local application database. M28-6's runtime M3 result → M18 → M21
  integration remained green. M24 import→M1 enrollment lifecycle and M27
  append-only human review/decision/ownership paths passed in existing suites.
- Boundaries: M22 derives from operational records plus M21 intervention
  evidence; it does not consume the M21 timeline as an event feed. M27 can
  reference eligible existing evidence through authorized human review, but
  neither an M22 signal nor an operational event automatically creates a
  decision or high-impact action. Asynchronous consumers retain independent
  checkpoints; there is no cross-domain watermark.
- Migration: NONE. No source code, schema, RLS policy, grants or historical
  migration changed. Assessment commands continue to require explicit maximum
  score despite the historical M3 database default.
- Validation: required full backend passed 768 tests, 0 failed, with two
  opt-in M21 cases skipped in the default invocation; the two cases separately
  passed when configured for the local DB. Full frontend passed 76 tests;
  typecheck and production build passed (existing chunk/dynamic-import
  warnings). No Python files changed; Ruff/`py_compile` had no targets.
  Alembic heads/current remained `0046_m28_attendance_perms`; diff-check passed.
- Stop boundary respected: M28-8 remains NOT STARTED. No new signal rules,
  metrics, accountability automation, providers, or autonomous intervention.

## M28-8 — Controlled operational pilot and closeout

- Goal: prove daily synthetic operation and prepare a controlled human run.
- Backend/frontend: existing harnesses plus deterministic, synthetic fixtures
  and strongest existing UI integration harness; repair only pilot blockers.
- Migration: NONE expected; any genuine schema defect needs forward migration
  and affected tests before returning to pilot. Never edit a historical revision.
- Security: two institutions; operator, rector/coordinator, teachers A/B,
  bare SYSTEM_ADMIN and guardian negative controls. Application-role sessions,
  no real PII/providers; replay, concurrency and cleanup/reprovision safety.
- Tests: one complete lifecycle, one withdrawal/reactivation/transfer history,
  online/offline conflict, result correction, M24 import equivalence, cross-tenant
  denial, current/suppressed evidence, and manual instrument preparation.
- Dependencies: all previous slices accepted by ASTRA.
- Full backend suite: YES once at final accepted product state; full frontend
  tests/typecheck/build, changed-file Ruff, compile, Alembic and diff-check.
  A later docs-only closeout reuses this evidence. Real post-gate code changes
  invalidate the relevant evidence and require justified revalidation.
- Artifact: commit/schema/dataset/clock, actors, scenarios, observed facts,
  metric denominators, lineage, test summaries, cleanup and three gate decisions.
- Stop: local closeout only; push/tag/release and later milestones need new
  authorization. No claim of field validation or production certification.

## Validation economy and reproducibility

Per ordinary slice: focused behavior/HTTP tests; affected-domain regression;
changed Python Ruff + py_compile; frontend focused tests/typecheck if touched;
production build for new routes or build configuration; Alembic heads/current
and application-role RLS/constraints if DB touched; diff-check; local commit.
Check installed scripts: frontend has `test`, `typecheck`, `build` (no lint
script). Do not invent a frontend lint gate. Use existing pytest layout and
declared dependencies, no heavy new test framework.

Full backend points are exactly M28-1 (security), M28-7 (integration), M28-8
(final pilot), once per accepted code state after focused/directed gates.
Failures: diagnose -> minimal compatible fix -> focused retest -> affected
regression. Do not repeatedly run full suite during repairs. Record passed,
failed, skipped and exit code persistently; identify the M21 opt-in skip.

M28-0 uses source inspection, revision-chain verification, link/JSON/document
consistency and git diff checks only. It does not repeat the published M27
743/1 backend or 61 frontend gate or claim those as new M28 validation.
Before dynamic work, recover the declared interpreter safely if necessary;
the previous Python314 venv launcher was inaccessible in the sandbox. Verify
actual environment rather than altering dependencies/product to hide that.

## ASTRA / Luna contract

ASTRA: architecture, authority and event freeze, security/threat review, hard
contract problems, slice acceptance and final readiness classification.
Luna: implementation in existing modules, minimal forward migrations,
frontend/backend, fixtures/tests, debugging, targeted repair, and local commits.

Each handoff identifies accepted parent SHA, this contract version, one slice,
allowed files/domains, migration decision, focused/regression commands and stop
boundary. Luna records what changed and the evidence, including limitations;
ASTRA checks the behavior against this freeze before the next slice begins.

Luna resolves routine imports/types/lint/harness/local PostgreSQL/fixtures and
compatible bugs autonomously. Escalate only a changed frozen contract, security
relaxation, irreversible or production operation, external credentials/cost,
genuine product choice, or push/tag/release. Unknown institution settings remain
unconfigured/fail-closed and do not justify invented business defaults.
