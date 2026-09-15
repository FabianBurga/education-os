# M22-2 Intelligence Read Boundary v1

## Status
SECURITY AMENDMENT REQUIRED BEFORE FORMAL GATE 1.

This amendment implements an access-control requirement already frozen in the
M22 Intelligence Contract: tenant isolation alone is not sufficient for
student-level institutional intelligence. M22 must enforce permission, role
and teacher student scope.

## Scope
Migration: `0026_m22_intel_read_boundary`
Down revision: `0025_m22_intelligence_foundation`

Hardens:
- `intelligence_signals`
- `student_intelligence_snapshots`
- `cohort_intelligence_daily`
- `institution_intelligence_daily`

## Permissions
- `intelligence.read`: SYSTEM_ADMIN, RECTOR, ACADEMIC_COORDINATOR, TEACHER
- `intelligence.manage`: SYSTEM_ADMIN, RECTOR, ACADEMIC_COORDINATOR

## Read rules
Managers read all four intelligence tables inside the active tenant.
TEACHER reads only student-scoped rows in `intelligence_signals` and
`student_intelligence_snapshots`, using active:
`user_accounts -> staff_profiles -> teaching_assignments -> course_offerings
-> student_section_assignments -> enrollments`, matching the row academic period.

TEACHER has no direct read of `cohort_intelligence_daily` or
`institution_intelligence_daily`.

## Write rules
INSERT/UPDATE/DELETE require tenant match, manager role and
`intelligence.manage`.

## RLS strategy
All pre-existing policies on the four tables are removed before the new
command-specific policies are created. All four tables remain ENABLE + FORCE
ROW LEVEL SECURITY.

## Formal Gate 1
HOLD until runtime proves manager read, teacher in-scope read, teacher
out-of-scope denial, teacher aggregate denial, teacher mutation denial,
manager/projector mutation, wrong-tenant denial and zero rollback residue.

## M4 compatibility rule

`intelligence_signals_tenant_isolation` is retained as the historical M4
policy name because existing regression contracts assert its presence.

In M22-2 the name no longer means tenant-only authorization. It is a
`FOR SELECT` policy whose predicate requires:

- tenant match,
- `intelligence.read`,
- manager role OR teacher student scope.

INSERT/UPDATE/DELETE remain separate command-specific manager-only policies
requiring `intelligence.manage`.

This preserves backward metadata compatibility without restoring the old
permissive `FOR ALL` behavior.

