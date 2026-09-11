# M11 Student Console v0.11.0

## Frozen base

- Tag: `m10-teacher-console-v0.10.0`
- Commit: `79a7c9b57bda36fed6ff2b5554d6c93b35ecf71d`

## Database

`0012_m10 -> 0013_m11`

No application data table is added. M11 adds its permission catalog, STUDENT
role and a least-privilege extension to the existing `family_notices` SELECT
RLS policy for own-student notices.

## Permissions

- `student.console.access`
- `student.profile.view`
- `student.classes.view`
- `student.schedule.view`
- `student.attendance.view`
- `student.grades.view`
- `student.notices.view`
- `student.progress.view`

## Scope invariant

The signed user is resolved through:

`user_accounts.person_id -> student_profiles.person_id`

All Student Console queries use that resolved StudentProfile. No endpoint
accepts a caller-supplied student id.

## Operational surfaces

- `/api/v1/student/dashboard`
- `/api/v1/student/me`
- `/api/v1/student/summary`
- `/api/v1/student/classes`
- `/api/v1/student/schedule`
- `/api/v1/student/attendance`
- `/api/v1/student/grades`
- `/api/v1/student/pending`
- `/api/v1/student/progress`
- `/api/v1/student/notices`

## Human safety

M11 intentionally does not expose `intelligence_signals` or internal risk
labels to the student. It presents factual records, pending work and progress
aggregates.
