# Education OS — M19 Institution Control Plane v0.19.0

## Frozen base

M19 starts from the formally frozen M18 release:

- tag: `m18-event-ledger-read-models-v0.18.0`
- commit: `badaf5456d3f55683d2e74af78076f06b04e6adb`
- database: `0017_m18`

M19 target:

- milestone tag: `m19-institution-control-plane-v0.19.0`
- database head: `0018_m19`

Production `v1.0.0` remains unreleased.

## Purpose

M19 creates an institution-scoped control plane over the existing modular
monolith. It does not move Education OS to microservices.

The control plane provides:

- capability governance
- policy registry
- monotonically increasing institutional control revision
- immutable control-change history
- capability drift detection
- event-platform health visibility
- role-separated read/manage boundaries
- unified frontend entry point
- canonical M18 event emission for control-plane changes

## Permissions

M19 introduces:

- `control_plane.view`
- `control_plane.manage`

Default grants:

- `SYSTEM_ADMIN`: view + manage
- `RECTOR`: view only

Teachers, students, guardians, finance-only staff, and roleless users receive no
Control Plane permission by default.

## Capability governance

M19 uses the existing `institution_capabilities` table as the effective runtime
capability state.

The Control Plane will not invent arbitrary capability keys. An update is only
allowed for a capability already registered for the institution.

This protects the platform from configuration that looks valid but has no
runtime consumer.

Because older module-specific endpoints can still update an existing
capability, M19 records the last managed state and reports drift when the
effective capability differs from the most recent Control Plane revision.

This allows migration toward centralized governance without silently rewriting
frozen M8-M18 modules.

## Policy registry

`institution_policy_controls` stores institution-scoped policy documents.

Policy keys follow:

`^[a-z][a-z0-9_.-]{2,119}$`

Policy JSON is limited to 16 KiB and explicitly rejects secret-like keys such
as password, secret, token, api_key, credentials, and private_key.

The Control Plane is not a secrets store.

A policy record is desired/configured state. It does not imply enforcement by
another module until that module explicitly consumes the policy.

## Revision history

Every effective Control Plane change increments
`institution_control_state.revision`.

The corresponding record in `institution_control_changes` contains:

- institution revision
- capability/policy change type
- subject key
- actor
- reason
- before state
- after state
- timestamp

The history table is append-only. UPDATE, DELETE, and TRUNCATE are rejected by
database triggers.

## M18 integration

Capability and policy changes emit canonical events:

- `institution.capability.changed`
- `institution.policy.changed`

using the M18 canonical outbox envelope.

These events are later ingested into the immutable Event Ledger and projected
through the existing M18 pipeline.

## Health summary

`GET /api/v1/control-plane/summary` reports:

- runtime release id
- current Alembic database revision
- unledgered transactional outbox count
- latest Event Ledger position
- M18 projection checkpoint
- projection lag
- capability drift count
- overall health status

The M19 health state is `HEALTHY` only when:

- unledgered outbox count is zero
- projection lag is zero
- capability drift count is zero

Otherwise the status is `ATTENTION`.

## Database structures

M19 adds:

- `institution_control_state`
- `institution_policy_controls`
- `institution_control_changes`

All three tables use PostgreSQL RLS + FORCE RLS.

## Unified frontend

M19 adds the `control-plane` module to the M15 unified navigation when
`control_plane.view` is granted.

The module opens an operational Control Plane dashboard with:

- summary metrics
- capability state and drift
- policy editor
- immutable revision history

The dashboard reuses the unified `education_os_access_token` session token.

## Definition of Done

M19 must prove:

- migration `0017_m18 -> 0018_m19`
- downgrade to `0017_m18`
- full backend regression
- frontend typecheck/test/build
- M7-M18 milestone regressions
- SYSTEM_ADMIN view/manage
- RECTOR view-only
- TEACHER denied
- capability management
- external capability drift detection
- drift reconciliation
- policy create/update/versioning
- secret-like policy rejection
- immutable control history
- canonical M18 event emission
- Event Ledger drain and projection convergence
- direct PostgreSQL RLS negative boundaries
- real Microsoft Edge workspace + dashboard
- backup/restore recovery
- controlled PRIMARY promotion
- core data fingerprint unchanged

Formal freeze additionally requires:

1. local acceptance
2. commit
3. push to `main`
4. main CI success
5. annotated milestone tag
6. tag CI success
