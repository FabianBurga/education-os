# M28 — Operational Adoption Core

## M28-0 freeze

Planning baseline: `m27-decision-accountability-os-v0.27.0`, annotated tag,
peeled commit `8af4557ee77d04adb2cb20d5994684268aacd194`.
Development branch: `m28-operational-adoption-core`. Source migration head:
`0042_m27_true_recurrence`. M28-0 creates documentation only. M28-1 and all
implementation slices remain NOT STARTED and require the next slice handoff.

M27 is CLOSED / PASS and published. Technical and synthetic operational gates
passed; value evidence is PASS_WITH_HUMAN_LIMITATIONS. Controlled human pilot
ready: YES. Field validated: NO. Production certified: NO. The tag, rather than
the older M27-8 SHA still printed in some historical closeout notes, identifies
the canonical base. This freeze does not recertify M27 or change its contracts.

## Minimum operational core

Education OS already owns the M0–M3 operational entities and M8/M10 consoles.
M28 must make their daily use coherent, permission-safe, history-preserving,
and traceable through M18/M21/M22 into M27. Creating another SIS schema would
duplicate existing authorities. The missing core is governed maintenance and
continuity of existing records, not a second Student, Enrollment or Gradebook.

The implementation target is one institutional operator maintaining a student,
matriculating them in an existing period, placing them in a section, assigning
a teacher, and letting that teacher record/correct attendance and results.
Rector/coordinator must see the resulting evidence and its freshness through
existing views. New SIS connectors, autonomous decisions and field-value
claims are outside this target.

## IN

- Granular effective permissions for existing M1–M3 entry points, including
  legacy callers; safe student lookup and a bounded student record workspace.
- Reuse Person, StudentProfile, staff and guardian references. Minimal
  student create/update/status commands and separately authorized guardian
  linking; no account creation requirement for a student.
- Enroll/activate/withdraw/complete/cancel with validated transitions,
  historical records, explicit reactivation and idempotent commands.
- Existing academic periods, levels, sections, subjects and offerings, with
  necessary period/date consistency and a usable configuration journey.
- Placement/transfer and teaching assignments; derive rosters from those
  authorities, retaining historical placement references.
- Reliable attendance and result entry/correction; reuse M10 and M20,
  preserve concurrency, audit and exactly-once logical evidence on retry.
- Existing M24 create-only student/enrollment CSV path as an alternative
  intake, with the same domain authorization and data-quality checks.
- Bounded operational history and readiness views for staff/coordination;
  M21 timeline, M22 intelligence and M27 links retain their own permissions.
- Synthetic operational pilot and instruments for later human adoption
  observation. Every slice has a concrete user journey and stop boundary.

## OUT

Admissions CRM; accounting/payroll; inventory/library/transport ERP; family
communications expansion; full LMS; final report-card certification; national
grading law; complex timetable optimization; district analytics; ministry
connectors; generalized synchronization; new agent capabilities; live
providers; production rollout; full M29 teacher continuity. Existing finance,
family, communications and teacher features are preserved, not reimplemented.

Scheduling is existing weekly `schedule_slots` plus `class_sessions`; no new
calendar platform. Assessment results are existing entries, not an official
transcript, promotion decision, or computed final grade. Guardian access is
not inferred from a contact link. Cross-institution transfer automation and
cross-organization person matching are deferred.

## Acceptance and evidence

Technical: real HTTP authorization tests plus PostgreSQL application-role RLS,
transaction rollback, idempotency, conflict, migration, frontend and build
gates. Existing source-string tests alone cannot establish operational safety.

Operational: operator -> enrollment -> placement -> teacher roster -> recorded
and corrected facts -> M18 -> M21/M22 -> authorized M27 view is reproducible.
No orphan placement, missing logical event, unauthorized roster or silent
overwrite in critical scenarios. Corrected evidence must be distinguishable
from stale projections. M27 decisions continue to require human authority.

Value/adoption: report synthetic completion/trace counts with denominators,
seeded data-quality errors detected, rejected unauthorized operations and
unresolved conflicts. Require zero critical scenario failures, tenant leaks
and autonomous high-impact mutations. Do not set arbitrary business targets.
Human task completion, time, comprehension and adoption require observation;
institutional outcomes require a real field pilot. Administrative Time Saved
remains NOT_COMPUTABLE / BASELINE_REQUIRED.

Reuse M27's human measurement instrument: task, participant role, start/end
condition, traditional baseline method/duration, Education OS duration, sample
count, period, measurement conditions, errors and provenance. Leave observed
values empty until a human run. Automated request latency is not human task
time or adoption. The synthetic pilot records technical timings separately.

## Decisions and responsibility

No product choice blocks M28-0. The smallest scope is frozen here and in
[domain boundaries](M28_DOMAIN_BOUNDARIES.md), [security](M28_SECURITY_BOUNDARY.md)
and [events](M28_EVENT_MODEL.md). Institutional values (school labels, dates,
attendance codes, grading maxima, authorized staff and correction windows)
are configured during a future pilot; synthetic fixtures must label their
values as examples. Unknown national/reporting requirements are deferred.

ASTRA owns contract changes, security review and acceptance. Luna implements
only the accepted slice, repairs local technical failures and creates local
commits. Contract/security relaxation, production or irreversible operations,
external credentials/cost, genuine product expansion, push/tag/release require
escalation. See [implementation plan](M28_IMPLEMENTATION_PLAN.md).
