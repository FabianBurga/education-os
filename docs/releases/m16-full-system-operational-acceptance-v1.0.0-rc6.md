# Education OS — M16 Full-System Operational Acceptance / v1.0.0-rc6

## Frozen base

M16 starts from the formally frozen M15 release:

- tag: `m15-unified-frontend-foundation-v0.15.0`
- commit: `b7e47039314a59448dfdd954df37400367a5d6c6`
- database head: `0016_m14`

M16 introduces **no database migration** and no new business-domain behavior.

The intended release-candidate tag after all gates pass is:

`v1.0.0-rc6`

This is still a release candidate. **Production v1.0.0 is not released by M16.**

## Purpose

M0–M15 established the architecture, tenant isolation, core domains, role
consoles, communications, finance and unified React frontend.

M16 answers a different question:

> Can the frozen system operate as one coherent product across the major roles,
> security boundaries, database recovery flow and real browser experience?

The M16 acceptance flow is therefore:

`Frozen code → Full regression → Role matrix → Security negatives → Real browser
→ Backup/restore drill → Reproducible evidence → RC`

## Acceptance actors

The verifier creates synthetic actors only inside a disposable acceptance
database clone:

- SYSTEM_ADMIN
- RECTOR
- ACADEMIC_COORDINATOR
- TEACHER
- STUDENT
- GUARDIAN
- FINANCE_MANAGER
- active staff with no role

No actor is automatically added to PRIMARY.

## Unified workspace matrix

For every synthetic actor, M16 validates:

- signed bearer context
- organization/institution context
- assigned role
- effective backend permissions
- modules exposed by `/api/v1/ui/bootstrap`
- React workspace links rendered in Microsoft Edge

The expected role-specific spaces are derived from the frozen permission
catalog and then compared with the actual browser navigation.

## Positive and negative API boundaries

M16 explicitly probes both allowed and forbidden access paths, including:

- Administrator Console
- Rector / Coordination Console
- Teacher Console
- Student Console
- Guardian Console
- Communications Center
- Finance / Billing Core

Examples include:

- administrator → admin summary: allowed
- teacher → admin summary: forbidden
- rector → coordination summary: allowed
- student → coordination summary: forbidden
- teacher → teacher summary: allowed
- guardian → teacher summary: forbidden
- student → own student profile: allowed
- guardian → student self endpoint: forbidden
- guardian → guardian identity: allowed
- student → guardian endpoint: forbidden
- coordinator → communications summary: allowed
- teacher → communications summary: forbidden
- finance manager → finance capability: allowed
- teacher → finance capability: forbidden
- roleless active staff → admin summary: forbidden

## RLS negative isolation

M16 signs a deliberately mismatched institution context for an otherwise valid
administrator user.

The release gate requires:

- `/api/v1/campuses` returns no rows under the mismatched institution context.
- `/api/v1/ui/bootstrap` rejects that context.

This supplements the existing M0–M15 RLS and permission tests.

## Real Microsoft Edge acceptance

M16 launches the actual installed Microsoft Edge browser through Playwright.

It signs into `/app` separately as each acceptance actor and confirms that the
visible workspace links exactly match the backend-issued permission context.

A roleless actor is also forced directly to a protected React workspace URL;
the interface must show `Espacio no disponible`.

Screenshots are captured for every acceptance actor.

## Frozen milestone regression

Before the M16 role matrix runs, the installer must repeat the established
milestone gates:

- complete backend pytest
- M7 release/security gate
- M8 administrator verifier
- M9 rector/coordination verifier
- M10 teacher verifier
- native M11 student verifier at `0013_m11`
- native M12 guardian verifier at `0014_m12`
- native M13 communications verifier at `0015_m13`
- M14 finance verifier at `0016_m14`
- M15 unified frontend verifier at `0016_m14`
- frontend TypeScript typecheck
- frontend Vitest
- frontend production build

## Backup / restore recovery drill

The full acceptance is performed against a disposable clone restored from a
fresh PRIMARY backup.

After all operational gates pass:

1. The accepted clone is dumped.
2. A second clean recovery database is created.
3. The accepted dump is restored into that database.
4. Revision and critical-table fingerprints are compared between the accepted
   clone and the recovered clone.
5. Both disposable databases are removed.

PRIMARY must have the exact same release fingerprint before and after M16.

## Evidence

A successful M16 run produces:

- pre-acceptance PRIMARY backup + SHA-256
- accepted clone backup + SHA-256
- recovered database fingerprint
- post-acceptance PRIMARY backup + SHA-256
- Edge screenshots for all roles
- `m16_full_system_matrix.json`
- console acceptance transcript

## Freeze rule

M16 is only locally accepted when every local gate is green.

The RC is only formally frozen after:

1. local M16 acceptance
2. commit
3. push to `main`
4. main CI success
5. annotated tag `v1.0.0-rc6`
6. tag CI success

Only after a separate decision following the RC acceptance should the project
consider creating the production tag `v1.0.0`.
