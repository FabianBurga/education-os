# M22-3 API + Decision Surfaces Contract Freeze v1.0

## Decision

`FREEZE_M22_3_API_DECISION_SURFACES_V1`

M22-3 exposes the secure analytical foundation through additive, deterministic
decision-support APIs. It preserves M4 API compatibility while adding explicit
authorization at the HTTP/service boundary.

No M22-3 endpoint may bypass the M22-2 database boundary, broaden teacher
scope, or infer hidden values from suppressed cohorts.

---

## 1. Architectural placement

```text
Authenticated principal
  -> HTTP role/permission boundary
  -> M22 decision-surface service
  -> M22 read models / M21 interventions / M4 signals
  -> PostgreSQL RLS
```

M22-3 remains deterministic institutional intelligence. It does not add an LLM,
ML prediction, embeddings, automatic high-impact decisions, diagnoses, or an
opaque risk score.

The database remains authoritative for tenant/scope enforcement; API/service
checks provide explicit deny semantics and protect legacy operational queries
that are not backed by the new M22 RLS tables.

---

## 2. Existing M4 routes: compatibility is mandatory

The following routes remain available with their existing response shapes:

- `GET /intelligence/rector/overview`
- `GET /intelligence/rector/sections`
- `GET /intelligence/rector/trends/attendance`
- `GET /intelligence/rector/trends/academic`
- `GET /intelligence/signals`
- `POST /intelligence/signals/refresh`
- `POST /intelligence/signals/{signal_id}/resolve`
- `GET /intelligence/rector/dashboard` (HTML shell, excluded from OpenAPI)

M22-3 must not rename or remove these routes.

### M4 authorization hardening

Legacy rector/institution-wide routes must require:

- permission `intelligence.read`, and
- one of `SYSTEM_ADMIN`, `RECTOR`, `ACADEMIC_COORDINATOR`.

`GET /intelligence/signals` requires `intelligence.read`.
Managers may see all tenant-authorized rows; teachers are limited by the M22-2
RLS student scope.

Signal mutation routes (`refresh`, `resolve`) require:

- permission `intelligence.manage`, and
- one of `SYSTEM_ADMIN`, `RECTOR`, `ACADEMIC_COORDINATOR`.

The static HTML shell may remain directly renderable because it contains no
institutional data. Every data request made by that shell must pass the secured
API boundary.

---

## 3. New M22 routes

### 3.1 `GET /intelligence/overview`

Management-only decision summary.

Authorization:

- `intelligence.read`
- role in `SYSTEM_ADMIN`, `RECTOR`, `ACADEMIC_COORDINATOR`

Data source:

- latest `institution_intelligence_daily`
- latest institution cohort row where needed for attendance/academic risk
- no raw event-ledger payload

Response contract:

```json
{
  "academic_period_id": "uuid|null",
  "snapshot_date": "YYYY-MM-DD",
  "in_scope_student_count": 0,
  "high_priority_count": 0,
  "medium_priority_count": 0,
  "active_intervention_count": 0,
  "interventions_without_action_count": 0,
  "overdue_followup_count": 0,
  "positive_outcome_count": 0,
  "unresolved_outcome_count": 0,
  "attendance_risk_count": 0,
  "academic_risk_count": 0,
  "rule_set_version": 1,
  "projection_version": 1,
  "policy_source": "BUILTIN_DEFAULT|CONTROL_PLANE",
  "policy_key": "institutional_intelligence",
  "policy_version": 1,
  "control_revision": null
}
```

`attendance_risk_count` and `academic_risk_count` are nullable if the source
institution cohort is suppressed or unavailable.

No invented freshness thresholds are introduced in v1. The response exposes
`snapshot_date` and provenance; freshness classification is deferred until a
baseline is measured.

---

### 3.2 `GET /intelligence/priorities`

Student priority queue.

Authorization:

- `intelligence.read`
- managers: tenant-wide authorized M22 snapshots
- teachers: RLS-limited to students inside actual teacher scope

Query parameters:

- `academic_period_id: UUID | null`
- `snapshot_date: date | null` — default latest available authorized date
- `priority: LOW|MEDIUM|HIGH | null`
- `dimension: ATTENDANCE|ACADEMIC|INTERVENTION | null`
- `limit: 1..100`, default `50`

Ordering:

1. `HIGH` before `MEDIUM` before `LOW`
2. evidence count descending
3. student UUID deterministic tie-break

Response item:

```json
{
  "student_profile_id": "uuid",
  "academic_period_id": "uuid|null",
  "snapshot_date": "YYYY-MM-DD",
  "overall_priority": "LOW|MEDIUM|HIGH",
  "attendance_priority": "LOW|MEDIUM|HIGH",
  "academic_priority": "LOW|MEDIUM|HIGH",
  "intervention_priority": "LOW|MEDIUM|HIGH",
  "evidence_count": 0,
  "rule_set_version": 1,
  "projection_version": 1,
  "policy_source": "BUILTIN_DEFAULT|CONTROL_PLANE",
  "policy_version": 1,
  "control_revision": null
}
```

M22-3 does not expose a hidden numeric risk score.

---

### 3.3 `GET /intelligence/cohorts`

Management-only cohort intelligence.

Authorization:

- `intelligence.read`
- manager role required

Query parameters:

- `academic_period_id: UUID | null`
- `snapshot_date: date | null` — latest by default
- `cohort_type: INSTITUTION|ACADEMIC_LEVEL|GRADE|SECTION|COURSE | null`
- `limit: 1..100`, default `100`

Response item:

```json
{
  "academic_period_id": "uuid|null",
  "snapshot_date": "YYYY-MM-DD",
  "cohort_type": "SECTION",
  "cohort_ref_id": "uuid|null",
  "student_count": 0,
  "high_priority_count": null,
  "medium_priority_count": null,
  "attendance_risk_count": null,
  "academic_risk_count": null,
  "active_intervention_count": null,
  "overdue_followup_count": null,
  "suppressed": true,
  "rule_set_version": 1,
  "projection_version": 1,
  "policy_source": "BUILTIN_DEFAULT|CONTROL_PLANE",
  "policy_version": 1,
  "control_revision": null
}
```

Privacy invariant:

If `suppressed=true`, sensitive component counts remain `null`. The API must
never convert them to zero, estimate them, derive percentages from them, or
combine other rows to reconstruct the hidden cell.

---

### 3.4 `GET /intelligence/trends`

Management-only institutional trend surface.

Authorization:

- `intelligence.read`
- manager role required

Query parameters:

- `academic_period_id: UUID | null`
- `days: 2..365`, default `30`

Data source:

- `institution_intelligence_daily`
- institution-level row from `cohort_intelligence_daily`

Each point:

```json
{
  "snapshot_date": "YYYY-MM-DD",
  "in_scope_student_count": 0,
  "high_priority_count": 0,
  "medium_priority_count": 0,
  "attendance_risk_count": null,
  "academic_risk_count": null,
  "active_intervention_count": 0,
  "overdue_followup_count": 0,
  "positive_outcome_count": 0,
  "unresolved_outcome_count": 0
}
```

Derived trend semantics:

- `attendance_risk_trend` is represented by the ordered
  `attendance_risk_count` series.
- `academic_risk_trend` is represented by the ordered
  `academic_risk_count` series.
- rising/falling labels are not persisted in M22-3 v1.
- no smoothing, interpolation, or prediction.

---

### 3.5 `GET /intelligence/interventions`

Management-only intervention-health surface.

Authorization:

- `intelligence.read`
- manager role required

Query parameters:

- `academic_period_id: UUID | null`
- `snapshot_date: date | null` — latest by default

Response:

```json
{
  "academic_period_id": "uuid|null",
  "snapshot_date": "YYYY-MM-DD",
  "active_interventions": 0,
  "interventions_without_action": 0,
  "followup_overdue": 0,
  "positive_outcomes": 0,
  "unresolved_outcomes": 0,
  "policy_source": "BUILTIN_DEFAULT|CONTROL_PLANE",
  "policy_version": 1,
  "control_revision": null
}
```

This endpoint is a health summary, not a replacement for the M21 institutional
intervention queue. Links/drilldown into intervention entities reuse the M21
intervention APIs and their sensitivity redaction.

---

## 4. Decision surfaces

M22-3 exposes five logical decision surfaces:

1. **Overview**
   - current institutional decision summary
2. **Priority Queue**
   - students requiring attention, with dimensions kept separate
3. **Cohort Intelligence**
   - grade/section/course comparisons with suppression
4. **Trend Intelligence**
   - historical deterministic counts
5. **Intervention Health**
   - action/follow-up/outcome health

The server API is the primary M22-3 deliverable. UI rendering may evolve
independently as long as it consumes these contracts and does not bypass them.

---

## 5. Authorization matrix

| Surface | SYSTEM_ADMIN | RECTOR | ACADEMIC_COORDINATOR | TEACHER |
|---|---|---|---|---|
| M4 rector overview/sections/trends | allow | allow | allow | deny |
| M4 signals list | allow | allow | allow | scoped |
| M4 signal refresh/resolve | allow | allow | allow | deny |
| M22 overview | allow | allow | allow | deny |
| M22 priorities | allow | allow | allow | scoped |
| M22 cohorts | allow | allow | allow | deny |
| M22 trends | allow | allow | allow | deny |
| M22 interventions health | allow | allow | allow | deny |

Roles outside this matrix are denied.

Teacher scope is defense-in-depth:

- API requires `intelligence.read`;
- DB RLS limits rows to actual student scope.

---

## 6. Error semantics

- missing authentication: existing authentication behavior
- missing `intelligence.read` or `intelligence.manage`: HTTP `403`
- authenticated but wrong institutional role for manager-only surface: HTTP `403`
- teacher requests an out-of-scope student through a future student-specific
  endpoint: HTTP `404`, consistent with M21 anti-enumeration semantics
- no analytical snapshot exists: return an empty collection for list surfaces;
  overview/health return HTTP `404` with deterministic `"Intelligence snapshot not found"`
- invalid filter: HTTP `422` through FastAPI/Pydantic validation

Do not return an empty tenant-wide result as a substitute for a missing
permission.

---

## 7. Provenance and explainability

All new M22 responses expose enough provenance to distinguish:

- rule set version
- projection version
- policy source
- policy version
- control revision where applicable
- snapshot date

The API must not label rule-derived priorities as AI.

---

## 8. Privacy

- suppressed cohort component metrics remain `null`
- no API-side reconstruction of small cells
- no arbitrary cohort builder
- no cross-institution comparison
- no hidden student names added to analytical records
- student identity enrichment, if introduced later, must pass the same scope
  boundary and is not part of this freeze

---

## 9. Performance and query shape

M22-3 v1 reads existing 0025/0026 analytical tables. It does not introduce a
new migration unless implementation proves an index or schema gap.

Requirements:

- bounded list limits
- deterministic ordering
- no N+1 lookup over students
- no direct `event_ledger` payload read
- no broad scan of operational attendance/grade tables for new M22 routes
- legacy M4 endpoints may retain their existing operational implementation for
  compatibility

---

## 10. Compatibility

M4 route paths and response models stay intact.

M22 endpoints are additive.

M21 intervention APIs remain authoritative for intervention detail and
sensitivity redaction.

No changes to M21 timeline/intervention contracts are required for M22-3 v1.

---

## 11. M22-3 directed contract tests

Implementation must add tests that prove at minimum:

1. legacy M4 route paths still exist
2. legacy rector route rejects teacher
3. legacy rector route accepts manager
4. signals list accepts manager
5. signals list teacher is scoped
6. signals mutation rejects teacher
7. M22 overview manager allowed
8. M22 overview teacher denied
9. M22 priorities manager sees tenant-authorized rows
10. M22 priorities teacher sees only scoped rows
11. priority filter is deterministic
12. priority dimension filter is deterministic
13. cohorts manager allowed
14. cohorts teacher denied
15. suppressed cohort values remain null
16. trends manager allowed
17. trends teacher denied
18. trends ordered by date
19. intervention health manager allowed
20. intervention health teacher denied
21. no new M22 route reads raw event-ledger payloads
22. all new list endpoints enforce bounded limits
23. full M0-M22 regression remains green

---

## 12. M22-3 implementation gate

Implementation is `PASS` only when:

- existing M4 route contract remains compatible
- API authorization matrix is proven
- teacher scope is proven at runtime
- suppression is preserved
- provenance is exposed
- full regression passes
- working tree is clean
- no unplanned migration is introduced

After implementation, proceed to M22-4 Controlled Institutional Pilot.
