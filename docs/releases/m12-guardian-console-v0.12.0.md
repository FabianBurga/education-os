# M12 Family / Guardian Console v0.12.0

## Frozen base

- Tag: `m11-student-console-v0.11.0`
- Commit: `db692b3c90033b7103ed9303466a822b11ff7bff`

## Database

`0013_m11 -> 0014_m12`

No application-data table is added. M12 adds only its RBAC permission catalog
and the institution-level `GUARDIAN` role. Student authorization continues to
use the M6 `guardian_student_portal_access` table.

## New operational API

- `GET /api/v1/guardian/dashboard`
- `GET /api/v1/guardian/me`
- `GET /api/v1/guardian/students`
- `GET /api/v1/guardian/students/{student_profile_id}/summary`
- `GET /api/v1/guardian/students/{student_profile_id}/classes`
- `GET /api/v1/guardian/students/{student_profile_id}/schedule`
- `GET /api/v1/guardian/students/{student_profile_id}/attendance`
- `GET /api/v1/guardian/students/{student_profile_id}/grades`
- `GET /api/v1/guardian/students/{student_profile_id}/pending`
- `GET /api/v1/guardian/students/{student_profile_id}/progress`
- `GET /api/v1/guardian/notices`
- `POST /api/v1/guardian/notices/{notice_id}/acknowledge`

## Scope invariant

For every student-specific operation:

`guardian user -> active GuardianProfile -> active portal grant -> StudentProfile`

An unlinked student returns 404 and never leaks whether data exists beyond the
guardian's authorized scope.

## Compatibility

M6 Family Portal is not deleted or rewritten. M12 validates that its existing
guardian endpoints continue to work for a valid guardian and remain scoped to
the same ACTIVE grants.

## Safety

M12 does not expose internal intelligence signal types, automation cases,
institutional risk labels or staff-only workflow reasoning.
