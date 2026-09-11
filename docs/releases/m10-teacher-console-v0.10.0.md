# M10 Teacher Console v0.10.0

## Base
`m9-rector-coordination-v0.9.0`
`7a1c8f5a661bdf1126f3b88264ebacfd1d063709`

## Database
Alembic `0011_m9 -> 0012_m10`

## Permission catalog
- `teacher.console.access`
- `teacher.classes.view`
- `teacher.attendance.manage`
- `teacher.grades.manage`
- `teacher.tasks.manage`

## Role
M10 ensures role `TEACHER` in each institution and grants the M10 permission set.
Existing SYSTEM_ADMIN receives the same permissions for support continuity.
No real user is automatically assigned TEACHER.

## Console
`GET /api/v1/teacher/dashboard`

Operational blocks:
1. Inicio
2. Mis clases
3. Asistencia
4. Calificaciones
5. Seguimiento

## Scope invariant
Every roster, attendance, assessment, grade, alert and TEACHER task is checked
against an active `teaching_assignments` relationship for the current
`staff_profile_id`.

## Legacy API boundary
Teacher-only actors receive 403 on broad institution-level historical staff
surfaces and must operate through `/api/v1/teacher/*`.
