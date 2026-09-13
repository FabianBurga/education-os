# Education OS â€” Testing Playbook

This file is the operational baseline for future Education OS integrations.

## Core rule

**Test only what changed, plus its direct security/data boundaries. Do not repeat already-passed modules unless dependency impact or a release gate requires it.**

## Preflight pattern

Every runner should:

1. Assert expected Git commit/tag when release-specific.
2. Assert expected Alembic revision.
3. Assert intended database and role.
4. Probe `/openapi.json`.
5. If API is down, start temporary Uvicorn.
6. Stop only the Uvicorn process started by the runner.
7. Generate fresh test tokens internally; never echo JWTs.
8. Write JSON + TXT evidence.

## Result classes

Use only:

- `PASS`
- `FAIL`
- `SKIP`
- `NOT_APPLICABLE`

Do not convert `NOT_APPLICABLE` into `FAIL`.

## Mutation rules

- Use clearly named synthetic fixtures.
- Prefer idempotent creates or discover-before-create.
- Do not mutate validated pilot records for destructive tests when an isolated fixture can be created.
- Capture original state before reversible settings changes.
- Restore immediately.
- Add emergency restore logic in `finally`.
- Never drop rollback DBs.
- Never terminate PRIMARY sessions automatically.

## API contract rule

Before writing payloads, inspect:
- router
- schema
- service when mutation semantics matter

Do not infer required fields from UI appearance.

Known example:
- Finance `ChargeCreate.due_on` is mandatory.

## Authorization rule

Expected denial = `PASS`.

Examples:
- Student â†’ Admin denied.
- Student â†’ Teacher denied.
- Guardian â†’ Admin denied.
- Guardian â†’ Teacher denied.
- Guardian â†’ another student denied (`403` or `404`).

## Legacy console/session rule

Known defect `UI/AUTH-01`:
legacy consoles use separate `sessionStorage` token keys and may retain stale identity.

Before classifying a mismatch as backend/RLS failure, inspect the legacy token state.

## Control Plane rule

When toggling capabilities:
- capture original value;
- toggle;
- validate;
- restore;
- validate history/revision;
- emergency restore on error.

For policy tests:
- `count=0` => `NOT_APPLICABLE`.

## Finance rule

For void/reversal:
- create isolated concept + charge + payment;
- void payment first;
- verify charge reopens and balance returns;
- then void charge;
- archive synthetic concept.

Do not void the previously validated primary pilot finance flow.

## Communications rule

For template tests:
- create synthetic template;
- create draft linked to template;
- verify `template_id`;
- archive draft;
- archive template.

## Regression strategy

### Targeted regression
Default for future integrations.

Test:
- changed module,
- direct callers/consumers,
- authorization boundaries,
- data integrity,
- event/audit behavior if touched.

### Full regression
Use when:
- migration touches shared tables,
- auth/RLS primitives change,
- core dependency wiring changes,
- release gate explicitly requires it,
- targeted testing indicates broader risk.

## Evidence naming

Recommended pattern:

`Education_OS_<scope>_<YYYYMMDD_HHMMSS>/`

Include:
- `REPORT.json`
- `REPORT.txt`
- `runner.stdout.log`
- `runner.stderr.log`
- Uvicorn logs when applicable

## Closed M20 coverage baseline

Do not re-run by default:
- Admin/onboarding basic coverage
- Rectorado read + mutation flow
- Teacher A/B
- M20 offline-first
- Student Console
- Family Portal
- Communications E2E
- Communications Templates
- Finance E2E
- Finance void/reversal
- Control Plane capability + change history
- authorization boundaries
- family cross-student isolation

Re-test only if future changes can affect those surfaces.
