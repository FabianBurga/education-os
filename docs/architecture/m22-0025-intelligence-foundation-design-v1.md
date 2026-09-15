# Education OS — M22-2 / Migration 0025 Design Freeze v1.0

**Milestone:** M22 — Institutional Intelligence + Early Warning  
**Phase:** M22-2 — Secure Analytical Foundation  
**Baseline M22 commit:** `09abe2900f6d6f51e29ef80d0e660c2b106fd944`  
**Baseline DB revision:** `0024_m21_projection_boundary`  
**Preflight:** `M22-2 SCHEMA/SOURCE PREFLIGHT V4: PASS`  
**Preflight report SHA256:** `f1fcb64518b070b4147e3ab82dffcc789c2f33a8a8abf5141b690ea3900534c2`  
**Status:** DESIGN FREEZE CANDIDATE  
**Next revision:** `0025_m22_intelligence_foundation`

## 1. Decision

Migration `0025` will create only the secure analytical persistence foundation required by M22.

It will NOT:
- alter M4 `intelligence_signals`;
- alter M21 intervention/timeline tables;
- create APIs or UI;
- add LLM/ML functionality;
- read Event Ledger payloads directly;
- create an intervention intelligence snapshot;
- seed or overwrite institution policy documents.

## 2. New tables

Exactly three tables:

1. `student_intelligence_snapshots`
2. `cohort_intelligence_daily`
3. `institution_intelligence_daily`

All three are derived/read-model state and are rebuildable.

## 3. Version/provenance semantics

Every analytical row records:

- `rule_set_version INTEGER NOT NULL`
- `projection_version INTEGER NOT NULL`
- `policy_source VARCHAR(30) NOT NULL`
- `policy_key VARCHAR(120) NOT NULL`
- `policy_version INTEGER NOT NULL`
- `control_revision BIGINT NULL`

Allowed `policy_source`:
- `BUILTIN_DEFAULT`
- `CONTROL_PLANE`

Rules:
- `rule_set_version >= 1`
- `projection_version >= 1`
- `policy_version >= 1`
- `control_revision IS NULL` is allowed only for `BUILTIN_DEFAULT`.
- `control_revision > 0` is required for `CONTROL_PLANE`.

Reason:
`institution_policy_controls` is mutable current state. Historical snapshots therefore do not FK to it. The immutable applied-policy identity/version/revision is copied as metadata, while policy history remains authoritative in M19 `institution_control_changes`.

Initial built-in policy identity:
- `policy_source = 'BUILTIN_DEFAULT'`
- `policy_key = 'institutional_intelligence'`
- `policy_version = 1`
- `control_revision = NULL`

## 4. Table: student_intelligence_snapshots

Columns:

- `id UUID PK`
- `organization_id UUID NOT NULL`
- `institution_id UUID NOT NULL`
- `student_profile_id UUID NOT NULL`
- `academic_period_id UUID NULL`
- `snapshot_date DATE NOT NULL`
- `evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `overall_priority VARCHAR(20) NOT NULL`
- `attendance_priority VARCHAR(20) NOT NULL`
- `academic_priority VARCHAR(20) NOT NULL`
- `intervention_priority VARCHAR(20) NOT NULL`
- `evidence_count INTEGER NOT NULL DEFAULT 0`
- version/provenance fields from section 3
- `window_start TIMESTAMPTZ NULL`
- `window_end TIMESTAMPTZ NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Checks:

- each priority in `LOW|MEDIUM|HIGH`
- `evidence_count >= 0`
- `window_end IS NULL OR window_start IS NULL OR window_end >= window_start`
- version/provenance checks from section 3

Tenant-safe FKs:

- `(institution_id, organization_id)` -> `institutions(id, organization_id)` RESTRICT
- `(student_profile_id, institution_id)` -> `student_profiles(id, institution_id)` CASCADE
- `(academic_period_id, institution_id)` -> `academic_periods(id, institution_id)` SET NULL

Idempotency unique key:

`(institution_id, student_profile_id, snapshot_date, rule_set_version, projection_version, policy_source, policy_key, policy_version)`

Note: `academic_period_id` is intentionally not required for uniqueness because nullable values weaken PostgreSQL uniqueness semantics. A student may have at most one equivalent logical snapshot per date/version/policy identity.

Indexes:

- organization
- institution
- student
- academic period
- snapshot date
- `(institution_id, snapshot_date, overall_priority)`
- `(institution_id, student_profile_id, snapshot_date)`

## 5. Table: cohort_intelligence_daily

Columns:

- `id UUID PK`
- `organization_id UUID NOT NULL`
- `institution_id UUID NOT NULL`
- `academic_period_id UUID NULL`
- `snapshot_date DATE NOT NULL`
- `cohort_type VARCHAR(30) NOT NULL`
- `cohort_ref_id UUID NULL`
- `student_count INTEGER NOT NULL`
- `high_priority_count INTEGER NULL`
- `medium_priority_count INTEGER NULL`
- `attendance_risk_count INTEGER NULL`
- `academic_risk_count INTEGER NULL`
- `active_intervention_count INTEGER NULL`
- `overdue_followup_count INTEGER NULL`
- `suppressed BOOLEAN NOT NULL DEFAULT false`
- version/provenance fields from section 3
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Allowed `cohort_type` v1:
- `INSTITUTION`
- `ACADEMIC_LEVEL`
- `GRADE`
- `SECTION`
- `COURSE`

Suppression semantics:
- `student_count` may remain visible.
- when `suppressed = true`, all component intelligence counts MUST be `NULL`, never zero.
- when `suppressed = false`, component counts MUST be non-null and `>= 0`.
- component counts cannot exceed `student_count` where logically student-count based.

Cohort identity:
- `cohort_ref_id IS NULL` only for `cohort_type='INSTITUTION'`
- `cohort_ref_id IS NOT NULL` for all other cohort types.

No polymorphic FK is created in `0025`; `cohort_type + cohort_ref_id` is validated by projection/service logic because one column cannot safely FK to multiple target tables.

Idempotency unique key:

`(institution_id, snapshot_date, cohort_type, cohort_ref_id, rule_set_version, projection_version, policy_source, policy_key, policy_version)`

Because `cohort_ref_id` is NULL for institution cohorts, add a separate partial unique index for `cohort_type='INSTITUTION'`.

Indexes:

- organization
- institution
- academic period
- snapshot date
- `(institution_id, snapshot_date, cohort_type)`
- `(institution_id, cohort_type, cohort_ref_id, snapshot_date)`

## 6. Table: institution_intelligence_daily

Columns:

- `id UUID PK`
- `organization_id UUID NOT NULL`
- `institution_id UUID NOT NULL`
- `academic_period_id UUID NULL`
- `snapshot_date DATE NOT NULL`
- `in_scope_student_count INTEGER NOT NULL`
- `high_priority_count INTEGER NOT NULL`
- `medium_priority_count INTEGER NOT NULL`
- `active_intervention_count INTEGER NOT NULL`
- `interventions_without_action_count INTEGER NOT NULL`
- `overdue_followup_count INTEGER NOT NULL`
- `positive_outcome_count INTEGER NOT NULL`
- `unresolved_outcome_count INTEGER NOT NULL`
- version/provenance fields from section 3
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Checks:
- all counts >= 0
- high/medium counts <= in-scope student count
- version/provenance checks from section 3

Tenant-safe FKs:
- tenant FK to institutions
- optional period FK to academic periods

Idempotency unique key:

`(institution_id, snapshot_date, rule_set_version, projection_version, policy_source, policy_key, policy_version)`

Indexes:
- organization
- institution
- academic period
- snapshot date
- `(institution_id, snapshot_date)`

## 7. RLS and privileges

All three tables:

- `ENABLE ROW LEVEL SECURITY`
- `FORCE ROW LEVEL SECURITY`

Initial v1 database policy:

tenant isolation using the established context:

`organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid`
AND
`institution_id = NULLIF(current_setting('app.institution_id', true), '')::uuid`

Privileges:
- `education_app`: `SELECT, INSERT, UPDATE, DELETE`

Rationale:
write authorization for the internal projector remains application/service controlled in this foundation migration. Role-aware end-user reads are enforced in API/service scope and will receive dedicated negative tests before M22 release.

No cross-tenant access is permitted.

## 8. Downgrade contract

Downgrade drops only M22 analytical tables and their indexes/policies.

It MUST NOT:
- mutate M4 signals;
- mutate M19 policy/control history;
- mutate M21 timeline/interventions;
- remove M0-M21 permissions/functions.

Drop order:
1. `cohort_intelligence_daily`
2. `institution_intelligence_daily`
3. `student_intelligence_snapshots`

(or any FK-safe equivalent order).

## 9. Required tests before Gate 1

Migration contract tests:
- revision is exactly `0025_m22_intelligence_foundation`
- down_revision exactly `0024_m21_projection_boundary`
- exactly three M22 analytical tables
- required columns/checks/unique indexes
- FORCE RLS on all three
- tenant policies exist
- runtime grants exist
- no alteration of M4/M21 tables
- downgrade restores `0024`

DB tests:
- wrong-tenant row invisible/rejected
- same logical snapshot cannot duplicate
- different policy/rule/projection versions may coexist
- suppressed cohort cannot persist component counts
- unsuppressed cohort requires component counts
- control-plane policy metadata validity enforced
- downgrade/upgrade round trip

## 10. Explicitly deferred

Deferred to subsequent M22-2 implementation commits:
- SQLModel classes for snapshots
- projector/service
- metric registry implementation
- policy resolution service
- evidence-link persistence if needed
- teacher/manager API authorization
- UI
- performance baseline thresholds

## 11. Freeze recommendation

`FREEZE_0025_DESIGN_V1`

After freeze, allowed next action:
generate migration `backend/alembic/versions/0025_m22_intelligence_foundation.py` and migration contract tests from this specification.
