# Education OS â€” M20 Internal Pilot Validation Report

Date: 2026-09-13  
Release under test: `m20-teacher-offline-pwa-v0.20.0`  
Frozen release commit: `b057c3ff3dea1f16aa45bb7862e3a0303c7e0fd7`  
PRIMARY database revision: `0019_m20`  
Pilot decision: **PASS**

## 1. Purpose

This report consolidates the controlled internal pilot executed against the M20 release of Education OS. It records what was actually validated, what was intentionally skipped, the defects and observations found, the synthetic data used, and the testing rules that must be preserved for future integrations.

The goal is to avoid re-testing already closed areas without a reason, avoid repeating test-harness mistakes, and provide a reliable baseline for future milestone and integration validation.

## 2. Environment and source of truth

- Repository: `FabianBurga/education-os`
- Frozen M20 tag: `m20-teacher-offline-pwa-v0.20.0`
- Frozen release SHA: `b057c3ff3dea1f16aa45bb7862e3a0303c7e0fd7`
- PRIMARY database: `education_os`
- PRIMARY Alembic revision: `0019_m20`
- Runtime role: `education_app`
- Owner role used only for controlled setup/validation: `education_owner`
- Rollback clone retained from migration stage.

The release itself remains frozen at the tag above. Documentation commits added after the pilot do not change the frozen release artifact.

## 3. Pilot actors and synthetic data

Controlled pilot actors:

- System administrator: `pilot-admin@education-os.internal`
- Teacher A: `pilot-teacher-a@education-os.internal`
- Teacher B: `pilot-teacher-b@education-os.internal`
- Synthetic student authentication fixture created for Student Console validation.
- Synthetic guardian accounts already present and reused for Family Portal validation.

Institutional pilot data included:

- Institution: Universidad de Otavalo
- Type: PRIVATE
- Campus: Sede Ã‘ucahua Estudio
- Academic period: 2026-2027 ACTIVE
- Grade: EducaciÃ³n General BÃ¡sica / Sexto grado
- Section: Sexto B, MORNING
- Subjects: MatemÃ¡tica and Ciencias Naturales
- 5 synthetic students
- 5 synthetic representatives

## 4. Functional coverage and final status

| Area | Result | Evidence summary |
|---|---|---|
| Unified frontend / home | PASS | Roles, modules and context rendered correctly |
| Administrator console | PASS | Institution, people/access, structure, enrollments/families, onboarding and controlled CRUD validated |
| Rectorado / Coordination read layer | PASS | Summary, priorities, cases, sections and trends validated |
| Rectorado / Coordination mutations | PASS | Workflow run, task acknowledge, task complete, timeline, signal resolve and tick validated |
| Teacher A | PASS | Classes, attendance and M20 offline flow validated |
| Teacher B | PASS | Isolation from Teacher A, classes, attendance, grades and follow-up validated |
| M20 offline-first | PASS | Offline package, offline mutation, reload, sync and persistence validated |
| Student Console | PASS | Profile, summary, classes, schedule, attendance, grades, pending, progress and notices validated |
| Family Portal | PASS | Child overview, attendance, grades, notices, read and acknowledgement validated |
| Family cross-student isolation | PASS | Guardian access to another student denied with 404 |
| Communications E2E | PASS | Draft â†’ targeting â†’ publish â†’ delivery â†’ read â†’ acknowledgement |
| Communications templates | PASS | Template create â†’ use in draft â†’ archive draft â†’ archive template |
| Finance E2E | PASS | Concept â†’ charge â†’ partial payment â†’ PARTIAL â†’ final payment â†’ PAID â†’ zero balance |
| Finance void / reversal | PASS | Payment void â†’ charge reopened â†’ charge void â†’ concept archived |
| Control Plane capabilities | PASS | Reversible toggle and restoration validated |
| Control Plane change history | PASS | Control revision increment and change history validated |
| Control Plane policies | N/A | Institution currently has zero configured policies; correctly treated as NOT_APPLICABLE |
| Authorization boundaries | PASS | Student/guardian access to admin and teacher surfaces denied |
| RLS / role isolation | PASS | Teacher and family scope isolation confirmed |

## 5. Key pilot evidence

### Teacher offline persistence
Teacher A changed attendance while offline, reloaded offline successfully, synchronized after reconnecting, and the fresh snapshot returned the persisted value from PRIMARY.

### Teacher isolation
Teacher B saw only the Ciencias Naturales class and did not inherit Teacher A's MatemÃ¡tica attendance mutation.

### Communications E2E
A controlled communication was published to 5 reachable families. Guardian 1 opened the Family Portal notice, moving delivery state to READ, then acknowledged it, moving the state to ACKNOWLEDGED.

### Finance E2E
A `$10.00` obligation was created. A `$4.00` partial payment produced `PARTIAL` with `$6.00` outstanding. A second payment closed the charge as `PAID` with `$0.00` balance.

The secondary reversal test created an isolated `$1.00` fixture, posted a payment, voided the payment, verified that the charge returned to `OPEN` with `$1.00` balance, then voided the charge and archived the concept.

### Rectorado / Coordination mutations
The engine was run against existing synthetic signals. Existing cases were reused, one open task was acknowledged and completed, case timeline events were verified, one signal was resolved, and a workflow tick completed successfully.

### Control Plane
`finance.billing` was toggled `True â†’ False â†’ True`. The original state was restored immediately. Change history recorded the actions and `control_revision` advanced from `0` to `2`.

There were zero policies configured, so policy mutation was classified as `SKIP / NOT_APPLICABLE`, not as a failure.

## 6. Confirmed defects and non-blocking findings

### UI/AUTH-01 â€” Medium
Legacy consoles maintain independent tokens in `sessionStorage`. A user switch in the unified frontend can leave a stale identity in an inherited console.

### UI-COM-01 â€” Low
After creating a communications draft, the table updates but the top-level draft counter can remain stale until a full refresh.

### UI-COM-02 â€” Low
A helper/status message can continue to display stale draft text after publication.

### UX-FIN-01 â€” Low/Medium
`due_on` is required by the backend for charge creation, but the frontend did not make that requirement sufficiently explicit. Backend validation correctly returned `422`.

### UI-03 â€” Low
The M20 teacher offline table can clip controls at very narrow viewport widths.

### SECRET_KEY hardening â€” Warning
The pilot environment used a 30-byte HMAC secret. Production should use a secret of at least 32 bytes.

## 7. Important test-harness lessons

1. Do not assume the API is already running. Probe `/openapi.json`; start temporary Uvicorn if required, and stop only the process started by the runner.
2. Do not fail a test because optional domain data does not exist. Example: `policies=0` means `NOT_APPLICABLE`.
3. Inspect the actual schema before constructing mutation payloads. Example: Finance `due_on` is mandatory.
4. Separate backend defects from frontend/session defects.
5. Do not repeat already-passed modules by default. Regression should be impact-based unless a release gate explicitly requires full regression.
6. Use isolated synthetic fixtures for destructive tests.
7. Reversible Control Plane changes must restore the original state immediately and include emergency restore logic.
8. Treat expected authorization denials as PASS.
9. Do not expose or echo JWTs in logs or reports.
10. Never automatically terminate PRIMARY sessions, drop rollback databases, or perform destructive cleanup unrelated to the test fixture.

## 8. Runner history

- `RUN_M20_PENDING_INTERNAL_PILOT_V1_1.ps1`
- `RUN_M20_PENDING_MUTATIONS_V2.ps1`
- `RUN_M20_FINAL_GAP_CLOSURE_V3.ps1`

Final gap closure result: `FAILURES=0`, `SKIPS=1`, `DECISION=PASS`.

## 9. Final decision

**M20 INTERNAL PILOT: PASSED**

The remaining items are non-blocking UI/UX/session-hardening issues and production hardening tasks.

## 10. Rule for future integrations

Before adding a new milestone or integration:

- read this report;
- read `TESTING_PLAYBOOK.md`;
- identify only the surfaces affected by the new change;
- create a targeted runner for those surfaces;
- use full regression only when the release gate or dependency impact requires it;
- preserve prior PASS evidence instead of re-running the same manual flows without cause.