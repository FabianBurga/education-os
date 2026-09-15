# Education OS — M22-1 Intelligence Contract Freeze v1.0

**Milestone:** M22 — Institutional Intelligence + Early Warning  
**Phase:** M22-1 — Intelligence Contract Freeze  
**Baseline source release:** `m21-student-timeline-interventions-v0.21.0`  
**Baseline commit:** `6942ca3811674a704424742d2ebc4bb461ab4a79`  
**Baseline DB revision:** `0024_m21_projection_boundary`  
**Status:** CONTRACT CANDIDATE — READY FOR FREEZE REVIEW  
**Purpose:** Define the smallest complete, explainable, secure and backward-compatible contract required before any M22 production migration or implementation.

---

## 1. Product intent

M22 converts the operational and longitudinal information already present in Education OS into institutional intelligence that is:

- deterministic;
- explainable;
- auditable;
- tenant-safe;
- role-aware;
- privacy-aware;
- versioned;
- rebuildable;
- useful for human decision-making.

M22 does **not** create new operational truth. It derives intelligence from existing authoritative domains.

Canonical reasoning chain:

`Operational Data -> Canonical Events -> Timeline / Signals / Interventions -> M22 Intelligence -> Human Decision`

M22 must never convert a derived risk or priority into an automatic high-impact decision.

---

## 2. Non-negotiable architecture principles

1. **Operational truth remains in M0–M21.**
2. **M22 derived data is disposable and rebuildable.**
3. **No broad runtime access to protected Event Ledger payloads.**
4. **Reuse M21 least-privilege projection patterns.**
5. **Reuse existing RLS, RBAC, institution context and M21 scope rules.**
6. **Preserve M4 intelligence API compatibility wherever practical.**
7. **Rules are deterministic in M22 v1.**
8. **All rule outputs carry version + evidence provenance.**
9. **No opaque composite numeric risk score in v1.**
10. **No LLM/ML dependency in M22 core.**
11. **Aggregates must not leak small cohorts.**
12. **Interactive dashboards read analytical projections/snapshots, not large operational joins.**

---

## 3. Actors and authorization

### 3.1 SYSTEM_ADMIN
Permitted only through explicit capabilities. No implicit cross-tenant intelligence access.

### 3.2 RECTOR
Institution-wide institutional intelligence for the current authorized institution.

### 3.3 ACADEMIC_COORDINATOR
Institution-wide academic/intervention intelligence for the current authorized institution.

### 3.4 TEACHER
No global institutional dashboard. Student-level intelligence only for students already inside the teacher's authorized academic scope.

### 3.5 Other roles
Denied unless a future capability contract explicitly grants access.

---

## 4. M22 v1 decision surfaces

M22 v1 freezes five product surfaces:

1. **Institutional Overview**
2. **Priority Queue**
3. **Cohort Intelligence**
4. **Trend Intelligence**
5. **Intervention Health**

Each surface must answer a decision question:

| Surface | Decision question |
|---|---|
| Institutional Overview | What requires attention now? |
| Priority Queue | Which students need review first, and why? |
| Cohort Intelligence | Where is risk concentrated? |
| Trend Intelligence | What is improving, deteriorating, new or persistent? |
| Intervention Health | Are we responding, following up and obtaining outcomes? |

---

## 5. Source systems already present

### 5.1 Academic context
Authoritative concepts already available:

- `academic_periods`
- `enrollments`
- sections
- course offerings
- teaching assignments
- student-section assignments

`academic_periods` provide `starts_on`, `ends_on`, and `status`.

### 5.2 Attendance
Attendance semantics must be based on existing semantic flags such as:

- `counts_as_present`
- `counts_as_absent`
- `counts_as_late`

M22 must not depend on institution-specific textual attendance codes.

### 5.3 Academic performance
Existing grading/assessment data is the source for academic intelligence.

M22 compares normalized performance and/or grading-period aggregates. A single grade alone must not automatically imply persistent academic deterioration.

### 5.4 Existing M4 intelligence
M22 inherits the historical deterministic intelligence behavior and must not silently change existing signal semantics.

Historical defaults currently known:

- absence threshold: `20%`
- minimum attendance records: `5`
- late-count threshold: `3`
- academic average threshold: `70%`
- minimum graded records: `2`
- missing-work threshold: `3`

These become **versioned defaults**, not permanent hardcoded constants.

### 5.5 M21 longitudinal/intervention data
M22 reuses:

- Student Timeline
- Intelligence Signals
- Suggestions
- Interventions
- Actions
- Follow-ups
- Outcomes
- Intervention links
- Event/timeline provenance

---

## 6. Time semantics

M22 v1 explicitly rejects an invented `"N school days"` contract because Education OS does not yet have a canonical school-day calendar.

Allowed v1 windows:

- observed attendance/class-session windows;
- explicit calendar windows;
- academic periods;
- grading periods;
- intervention timestamp durations;
- daily institutional snapshots.

Every metric must expose its time-window semantics.

No metric may label a window as "school days" unless a canonical school-day source exists.

---

## 7. Priority model

### 7.1 Categories
The only overall priority categories in M22 v1 are:

- `LOW`
- `MEDIUM`
- `HIGH`

### 7.2 Dimensions
M22 v1 freezes three priority dimensions:

- `ATTENDANCE`
- `ACADEMIC`
- `INTERVENTION`

### 7.3 Overall priority aggregation
Deterministic v1 rule:

- if any dimension = `HIGH` -> overall = `HIGH`
- else if any dimension = `MEDIUM` -> overall = `MEDIUM`
- else -> overall = `LOW`

No hidden weighting is permitted in v1.

### 7.4 Interpretation
Priority is a workflow prioritization signal, not:

- diagnosis;
- sanction;
- disciplinary judgment;
- psychological assessment;
- automatic intervention authorization.

---

## 8. Metric Registry v1

The registry freezes 12 metrics.

### M22_METRIC_01 — high_priority_students
**Meaning:** number of currently in-scope students with overall priority `HIGH`.  
**Primary source:** latest student intelligence snapshot.  
**Window:** current snapshot.  
**Evidence:** underlying dimension/rule evidence.  
**Version:** `high_priority_students_v1`.

### M22_METRIC_02 — new_priority_cases
**Meaning:** students entering `MEDIUM` or `HIGH` relative to their previous valid snapshot.  
**Primary source:** current + prior student snapshots.  
**Window:** snapshot-to-snapshot transition.  
**Version:** `new_priority_cases_v1`.

### M22_METRIC_03 — persistent_priority_cases
**Meaning:** students remaining `MEDIUM/HIGH` across the configured persistence condition.  
**Primary source:** student snapshot history.  
**Window:** policy-controlled consecutive snapshots / configured duration.  
**Version:** `persistent_priority_cases_v1`.

### M22_METRIC_04 — active_interventions
**Meaning:** current M21 interventions not in terminal state.  
**Primary source:** M21 interventions.  
**Version:** `active_interventions_v1`.

### M22_METRIC_05 — interventions_without_action
**Meaning:** active interventions with no recorded intervention action.  
**Primary source:** M21 interventions + actions.  
**Version:** `interventions_without_action_v1`.

### M22_METRIC_06 — followup_overdue
**Meaning:** active interventions whose follow-up condition exceeds configured threshold or explicit target.  
**Primary source:** M21 intervention/follow-up timestamps and target dates.  
**Version:** `followup_overdue_v1`.

### M22_METRIC_07 — average_intervention_age
**Meaning:** average age of active interventions.  
**Primary source:** M21 intervention `opened_at` / current evaluation timestamp.  
**Time unit:** calendar duration.  
**Version:** `average_intervention_age_v1`.

### M22_METRIC_08 — positive_outcomes
**Meaning:** count/rate of closed/resolved interventions with explicitly positive outcome semantics.  
**Primary source:** M21 outcome model.  
**Version:** `positive_outcomes_v1`.

### M22_METRIC_09 — unresolved_outcomes
**Meaning:** interventions requiring outcome resolution according to current operational state.  
**Primary source:** M21 interventions/outcomes.  
**Version:** `unresolved_outcomes_v1`.

### M22_METRIC_10 — cohorts_with_rising_risk
**Meaning:** cohorts whose high/medium priority prevalence is rising relative to prior comparable snapshot.  
**Primary source:** cohort daily snapshots.  
**Version:** `cohorts_with_rising_risk_v1`.

### M22_METRIC_11 — attendance_risk_trend
**Meaning:** direction and magnitude of attendance-risk prevalence over comparable snapshots/windows.  
**Primary source:** student/cohort/institution snapshots derived from attendance evidence.  
**Version:** `attendance_risk_trend_v1`.

### M22_METRIC_12 — academic_risk_trend
**Meaning:** direction and magnitude of academic-risk prevalence/performance deterioration across comparable grading/academic windows.  
**Primary source:** academic aggregates + M22 snapshots.  
**Version:** `academic_risk_trend_v1`.

---

## 9. Rule registry v1

M22 v1 rule outputs must have:

- `rule_key`
- `rule_version`
- `policy_version`
- `evaluated_at`
- `window_start`
- `window_end`
- `observed_value`
- `threshold_value` where applicable
- evidence references

Initial rule families:

- `attendance_absence_priority_v1`
- `attendance_late_priority_v1`
- `academic_average_priority_v1`
- `academic_missing_work_priority_v1`
- `academic_deterioration_priority_v1`
- `intervention_no_action_priority_v1`
- `intervention_followup_overdue_priority_v1`
- `intervention_unresolved_outcome_priority_v1`

Existing M4 thresholds must be preserved as default behavior unless an institution policy explicitly overrides them.

---

## 10. M19 policy contract

M22 policy must be institution-scoped and versioned through the existing Control Plane.

Candidate policy namespace:

`institutional_intelligence`

Minimum v1 settings:

```json
{
  "attendance": {
    "absence_threshold_percent": 20,
    "minimum_records": 5,
    "late_count_threshold": 3
  },
  "academic": {
    "average_threshold_percent": 70,
    "minimum_graded_records": 2,
    "missing_work_threshold": 3
  },
  "intervention": {
    "followup_overdue_calendar_days": 7
  },
  "privacy": {
    "minimum_cohort_size": 5
  },
  "persistence": {
    "minimum_consecutive_snapshots": 2
  }
}
```

**Important:** numeric values for new M22-only policies (`followup_overdue_calendar_days`, `minimum_cohort_size`, persistence) remain candidate defaults until validated in the controlled pilot. Existing M4 defaults are compatibility defaults.

Policy changes must not rewrite historical intelligence silently. New evaluations use the new policy version.

---

## 11. Evidence / provenance contract

Every student priority result must be explainable.

Required evidence metadata:

- source type;
- source ID;
- event/timeline reference where available;
- observation timestamp;
- rule key/version;
- policy version.

Permitted initial evidence source types:

- `INTELLIGENCE_SIGNAL`
- `TIMELINE_ENTRY`
- `INTERVENTION`
- `INTERVENTION_ACTION`
- `INTERVENTION_FOLLOWUP`
- `INTERVENTION_OUTCOME`
- `ATTENDANCE_AGGREGATE`
- `ACADEMIC_AGGREGATE`

M22 must prefer references over copying sensitive raw payloads.

---

## 12. Analytical persistence contract

M22 v1 introduces exactly three analytical persistence concepts unless implementation evidence proves another structure is necessary.

### 12.1 `student_intelligence_snapshot`
Purpose: fast current/history student prioritization.

Minimum logical fields:

- id
- organization_id
- institution_id
- student_profile_id
- academic_period_id
- snapshot_date / evaluated_at
- overall_priority
- attendance_priority
- academic_priority
- intervention_priority
- evidence_count
- rule_set_version
- policy_version
- projection_version
- window_start
- window_end
- created_at

Uniqueness must prevent duplicate equivalent snapshots.

### 12.2 `cohort_intelligence_daily`
Purpose: privacy-safe cohort trends.

Minimum logical dimensions:

- organization_id
- institution_id
- academic_period_id
- cohort dimension/type
- cohort key/reference
- snapshot_date
- student_count
- high_priority_count
- medium_priority_count
- attendance_risk_count
- academic_risk_count
- active_intervention_count
- overdue_followup_count
- suppressed
- rule_set_version
- policy_version
- projection_version

### 12.3 `institution_intelligence_daily`
Purpose: executive trends without recalculating full historical operational joins.

Minimum logical fields:

- organization_id
- institution_id
- academic_period_id
- snapshot_date
- in_scope_student_count
- high_priority_count
- medium_priority_count
- active_intervention_count
- interventions_without_action_count
- overdue_followup_count
- positive_outcome_count
- unresolved_outcome_count
- rule_set_version
- policy_version
- projection_version

### Explicit non-table in v1
Do **not** create `intervention_intelligence_snapshot` initially. M21 remains authoritative and sufficiently structured. Materialize only later if measured query cost requires it.

---

## 13. Cohort contract

Initial cohort dimensions:

- institution
- academic period
- grade
- section
- course/subject where source semantics are unambiguous

No arbitrary user-defined cohort builder in M22 v1.

---

## 14. Small-cell privacy contract

For cohort-level results:

- if `student_count < minimum_cohort_size`, mark result `suppressed=true`;
- do not replace suppressed counts with zero;
- do not expose component counts that allow reverse calculation of the suppressed value;
- authorized student-level access remains governed separately by role/scope.

The minimum cohort size is policy-controlled.

---

## 15. API compatibility contract

Existing M4 endpoints must remain behaviorally compatible unless a dedicated deprecation plan is created.

Existing routes to preserve include:

- `/intelligence/rector/overview`
- `/intelligence/rector/sections`
- `/intelligence/rector/trends/attendance`
- `/intelligence/rector/trends/academic`
- `/intelligence/signals`

M22 may internally route these through new services/read models while preserving public contracts.

New M22 routes may be introduced for genuinely new capabilities, candidate set:

- `/intelligence/priorities`
- `/intelligence/cohorts`
- `/intelligence/interventions`

No duplicate endpoint should be added merely to rename an existing capability.

---

## 16. Security contract

M22 must pass all of the following:

### Tenant isolation
Institution A can never observe institution B data.

### Teacher scope
Teacher can never use M22 to expand access beyond current academic assignment scope.

### Manager scope
Institution-wide intelligence requires explicit authorized management role/capability.

### Sensitive detail
Free-text/sensitive M21 intervention detail remains redacted under existing sensitivity permissions.

### Event Ledger
M22 runtime receives no general Event Ledger payload access.

### Aggregate privacy
Suppressed cohorts do not leak values through alternate fields or totals.

### Negative testing
Every positive authorization path requires corresponding negative tests.

---

## 17. Determinism contract

Given the same:

- authoritative source state;
- rule set version;
- policy version;
- projection version;
- evaluation window;

M22 must produce the same derived intelligence result.

---

## 18. Idempotency contract

Re-running the same projection/evaluation for the same logical snapshot must not create duplicate analytical records or alter operational truth.

---

## 19. Rebuild contract

M22 analytical persistence must be rebuildable from authoritative M0–M21 data without changing M0–M21 operational records.

A controlled rebuild must demonstrate equivalent output for the same versions/windows.

---

## 20. Freshness contract

Institutional intelligence must expose freshness.

Initial states:

- `CURRENT`
- `DELAYED`
- `STALE`

Exact thresholds are implementation/operations policy and will be frozen before release.

The UI must not present stale intelligence as current.

---

## 21. Performance contract

M22 v1 does not freeze arbitrary latency numbers before measurement.

It freezes architecture:

- dashboards query analytical/read models;
- no giant request-time multi-domain joins as the default interactive path;
- indexes must support institution, period, date, priority and student/cohort filters;
- projector duration, lag, snapshot age and API latency must be observable.

Performance thresholds will be established from controlled-pilot baseline measurements.

---

## 22. Out of scope for M22 v1

Explicitly excluded:

- LLM Copilot;
- ML predictive models;
- vector database;
- embeddings;
- automatic high-impact decisions;
- automatic disciplinary action;
- automatic intervention authorization;
- district analytics;
- cross-institution benchmarking;
- warehouse/OLAP;
- external integrations;
- arbitrary cohort builder;
- behavioral/psychological diagnosis.

These belong to later roadmap milestones.

---

## 23. Controlled-pilot scenarios

The future M22 controlled pilot must include at least:

1. stable student;
2. new attendance risk;
3. persistent attendance risk;
4. academic deterioration;
5. combined attendance + academic risk;
6. healthy active intervention;
7. intervention without action;
8. overdue follow-up;
9. improving student after intervention;
10. unresolved/negative outcome;
11. stable cohort;
12. deteriorating cohort;
13. suppressed small cohort;
14. teacher denied global intelligence;
15. teacher allowed only authorized student intelligence;
16. wrong-tenant denial;
17. policy version change without rewriting prior snapshots;
18. replay/idempotency;
19. rebuild equivalence.

---

## 24. Formal M22 execution model

M22 will use five work blocks and three formal gates.

### M22-1 — Intelligence Contract Freeze
This document.

### M22-2 — Secure Analytical Foundation
- branch creation;
- migration;
- rule/policy registry;
- snapshots;
- projector;
- RLS;
- evidence references;
- observability.

**Formal Gate 1:** Secure Analytical Foundation.

### M22-3 — Intelligence APIs + Decision Surfaces
- compatible M4 evolution;
- priority queue;
- cohort intelligence;
- institutional overview/trends;
- intervention health;
- UI decision surfaces.

### M22-4 — Controlled Institutional Pilot
Single designed synthetic dataset covering all acceptance scenarios.

**Formal Gate 2:** Controlled Institutional Pilot.

### M22-5 — Final Impact / Security / Release
- full M1–M22 regression;
- security negative tests;
- RLS;
- deterministic output;
- idempotency;
- rebuild;
- performance baseline;
- repository integrity;
- release/tag readiness.

**Formal Gate 3:** Final Integrated Release.

---

## 25. M22-1 freeze acceptance criteria

M22-1 is considered frozen only if all are true:

- [x] Product intent defined
- [x] Actors and access model defined
- [x] Decision surfaces defined
- [x] 12-metric registry defined
- [x] Priority dimensions and aggregation defined
- [x] Existing M4 compatibility explicitly preserved
- [x] Existing M4 default thresholds captured
- [x] M19 policy migration strategy defined
- [x] Time semantics constrained to real existing sources
- [x] Evidence/provenance contract defined
- [x] Analytical persistence limited to 3 initial structures
- [x] Small-cell privacy requirement defined
- [x] Determinism/idempotency/rebuild contracts defined
- [x] Controlled-pilot scenarios defined
- [x] Out-of-scope explicitly frozen
- [x] 5-stage / 3-gate execution model frozen

Remaining before production code:
- inspect exact current model/column names needed for migration implementation;
- create M22 working branch from the published M21 release;
- create migration only after branch/repository preflight;
- validate candidate new-policy defaults in controlled pilot.

---

## 26. Freeze decision

**Recommended decision:** `FREEZE_M22_1`

This contract is intentionally conservative:
- it reuses existing M4 intelligence;
- reuses M19 policies;
- reuses M21 privacy/provenance/interventions;
- adds only the analytical persistence M22 actually needs;
- postpones AI and warehouse complexity;
- preserves explainability and human authority.

If frozen, the next allowed action is:

**M22-2 — Secure Analytical Foundation**, beginning with repository/branch preflight and the implementation design for the first M22 migration.
