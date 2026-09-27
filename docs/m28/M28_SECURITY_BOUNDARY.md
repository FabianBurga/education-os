# M28 security and privacy freeze v1

## Verified starting boundary

Signed `CurrentPrincipal` supplies organization/institution/user; active
membership is validated after applying PostgreSQL tenant context. M1–M3 tables
have tenant RLS/FORCE RLS and M2/M3 composite tenant relationships. Their
historical policies are not per-operation or per-teacher permissions. API
M1–M3 guards require staff and special-case teachers; absence of TEACHER can
currently pass without a domain permission. M28-1 must close that gap before
making the operational workspace available. Existing metadata tests do not
prove that staff without academic permissions are rejected.

## Permission contract (new keys are planned, not yet installed)

Reuse the effective-permission resolver and membership/role tables. Introduce
only the following domain keys where no equivalent exists. Grants are explicit
institution-scoped configuration; do not auto-grant by role name or console
access. M28-1 seeds catalog entries, not blanket SYSTEM_ADMIN access.

| Operation family | Required effective permission | Additional scope |
| --- | --- | --- |
| Student list/detail/history | `students.read` | institution + authorized subject; minimized fields |
| Student create/code/status | `students.manage` | institution; person reuse restriction; active-enrollment guard |
| Guardian read/link | `families.read` / `families.manage` | permitted student and guardian in same institution; no portal grant |
| Enrollment read/mutate | `enrollments.read` / `enrollments.manage` | student/period/campus; explicit transition; expected revision |
| Academic config read/write | `academics.read` / `academics.manage` | institution/campus/period |
| Placement and teacher assignment | `academics.assign` | both endpoints in permitted scope; cannot grant permissions |
| Institution attendance read/write | `attendance.read` / `attendance.manage` | authorized institution and roster/session |
| Historical attendance correction | `attendance.correct` | visible original fact/period; reason + current revision |
| Institution results read/write | `grades.read` / `grades.manage` | authorized institution and assessment/placement |
| Historical result correction | `grades.correct` | visible original fact/period; reason + current revision |
| Teacher classes/attendance/results | existing `teacher.classes.view`, `teacher.attendance.manage`, `teacher.grades.manage` and console access | current active staff assignment; no broader institution list |
| M24 apply | existing `integrations.run` AND required student/enrollment create permissions | connector tenant, item scope, revalidate at apply |
| M21/M22/M27/Mentor drill-through | existing destination permissions | destination independently reauthorizes; no delegated bypass |

Keys ending manage authorize their bounded mutations, not unrestricted SQL or
reading unrelated PII. Read screens check read keys separately. Attendance and
grades correction also requires the corresponding read permission; manage
alone does not authorize historical correction. Existing teacher permissions
continue to allow ordinary entry/correction within the active scoped workflow.
Catalog additions and API gates must ship together; existing grants are not
silently expanded. Record explicit operator grants in synthetic fixtures and
handoff, not universal production defaults.

## Role workflows (roles are examples, not authorization code)

| Actor | Create / modify | Read | Audit |
| --- | --- | --- | --- |
| SYSTEM_ADMIN without academic grants | existing technical account/institution administration only | technical context allowed by M8; no new academic access | privilege and configuration changes |
| Rector | only explicitly granted academic/config/approval operations | authorized institution record/readiness and M21/M22/M27 | every mutation; no hidden automatic domain action |
| Academic coordinator | permitted period/section/offering/assignment maintenance; corrections if granted | authorized academic scope | changes, transfers, corrections |
| Secretary / administrative staff | student and enrollment administration, optional guardian linking if delegated | minimized student/placement history | create/status/link/lifecycle commands |
| Teacher | assigned class sessions/attendance and assessments/results through M10/M20 | assigned course roster only | entries/corrections, offline identity and conflicts |

No seeded SECRETARY role was found. Use existing institution-specific roles
with the catalog above; do not grant `admin.console.access` merely to let
secretarial staff enroll students. M8 account/role-management remains distinct.
Migration 0012 already seeded teacher permissions to SYSTEM_ADMIN; test both a
bare role with no academic grants (deny) and an explicitly authorized scoped
actor. Do not revoke historical grants opportunistically or use the role as a
universal deny/allow. M21/M22 legacy role restrictions remain additional limits.

## Threat-to-test matrix

| Threat | Required control and proof |
| --- | --- |
| Client changes institution/org/owner fields | server-derived tenant, typed allowlist/forbid extras on new commands; negative HTTP and direct-service tests |
| IDOR/cross-tenant references | tenant-qualified existence + composite FK + RLS; invisible objects 404 without counts/PII; repeat with forged cursor |
| Organization Person lookup leaks another institution | explicit identity-admin authorization or permitted existing subject relation; do not expose all org people to students.read |
| Legacy M1–M3 route bypass | negative tests on old and new routes for non-teacher staff, bare SYSTEM_ADMIN, teacher and custom roles |
| Same-tenant cross-course teacher access | staff/offering assignment/date plus eligible roster; guessed session/assessment UUID and another teacher's subject must fail |
| Scope revoked after offline capture | reauthorize before receipt replay/read and apply; no cached auth or prior receipt as permission |
| Bulk import | M24 fixed CSV bounds and identity mapping; revalidate accepted row targets/permissions at apply; partial item failures are explicit |
| Mass assignment | update code/status only; reject id/person/tenant/created_at injection; internal services enforce allowlist too |
| Lost updates/double submit | row/target lock plus expected revision/base state and durable unique request identity; two-session concurrency tests |
| Partial commit | injected failure after row write but before audit/outbox/receipt must roll back all facts; test online teacher wrappers and M24 item savepoints |
| Historical deletion/cascade | no new delete routes; history append-only in retained audit/events; do not rely on old broad DELETE grants as a product feature |
| Aggregate inference | retain M22/M27 policy suppression; new operational list count uses identical permission/scope predicates; do not calculate suppressed complements |
| Provider authority | no new tools/capabilities; no raw PII provider path; Mentor remains L0 |

Use real `education_app` sessions, non-superuser/non-BYPASSRLS, with principal
context. Owner is fixture/migration only. Preserve existing grants and frozen
metadata contracts unless an explicit forward hardening decision requires
change. New history/receipt tables require FORCE RLS, tenant composite links,
least grants and append-only protections. If a SECURITY DEFINER function is
needed, it needs explicit ASTRA review for search_path, tenant/principal and
permission checks; no generic function accepting SQL is permitted.

## PII minimization

Operational identity (names, student code) is personal data: show only for the
authorized task, bound search results, and exclude from event payloads/logs.
Contact/guardian relationships are more restricted: separate permissions and
no bulk export. Attendance, grades and intervention references are sensitive
educational records: source authorization applies even within one tenant.
Free-text notes/feedback must not be copied into audit, ledger, metrics or
provider input. M28 adds no medical records, national identity collection or
general document warehouse. Existing data is not silently deleted or copied.

Person edits affecting several institution profiles must remain under explicit
identity administration. M20 caches retain existing expiry, tenant/user
partition and logout purge; no contacts, guardian records or new result cache.
Synthetic tests contain unmistakably synthetic names/IDs and no real student
PII. Error messages and retry receipts do not return invisible prior results.
Retention periods and field-consent procedures require institutional policy;
M28 must not invent or claim legal compliance/certification.
