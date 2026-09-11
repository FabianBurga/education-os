# M9 Rector / Coordination Console v0.9.0

## Base
`m8-administrator-console-v0.8.0`
`dd9686a37a25f7adf5222e1fcb888c196ef3b6b1`

## Database
Alembic `0010_m8 -> 0011_m9`

## New permission catalog
- `coord.console.access`
- `coord.analytics.view`
- `coord.signals.manage`
- `coord.cases.manage`

## Roles
For every existing institution M9 ensures:
- `RECTOR`
- `ACADEMIC_COORDINATOR`

Both receive the M9 permission set. Existing `SYSTEM_ADMIN` roles also receive
the same permissions for support / operational continuity. No real user is
automatically assigned to Rector or Coordinator.

## Console
`GET /api/v1/coordination/dashboard`

Operational blocks:
1. Executive overview
2. Attention queue
3. Cases and follow-up
4. Sections
5. Trends

## Security
M4 intelligence routes are upgraded from generic active-staff access to the
explicit `coord.console.access` boundary.

## Human-in-the-loop
The console can refresh signals and workflow state, but resolution and task
completion require a human action and written note.

## Architecture debt
M9 remains server-served HTML, matching M4/M8. It does not claim fulfillment of
the frozen React/TypeScript/Vite UI baseline.
