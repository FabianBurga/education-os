# M19 Institution Control Plane Architecture

## Position in Education OS

M19 adds a control plane without splitting the modular monolith.

```text
Experience Plane
      |
      v
Institution Control Plane
      |
      +------------------------------+
      |                              |
      v                              v
Operational Core              Event Plane (M18)
      |                              |
      v                              v
institution_capabilities      canonical event ledger
institution_policy_controls   projection checkpoints
      |
      v
effective institution state
```

## Control revision

Each managed mutation obtains one monotonically increasing institution revision.

The revision is allocated in the same PostgreSQL transaction as:

- capability/policy state change
- append-only control-change record
- audit record
- canonical outbox event

This gives one durable institutional ordering for managed control changes.

## Capability source of truth

`institution_capabilities` remains the runtime source of truth.

M19 intentionally does not duplicate effective capability state into a second
table.

The append-only change history stores the last state requested through the
Control Plane. Comparing that state against `institution_capabilities` detects
external changes made through older module-specific paths.

## Policy source of truth

`institution_policy_controls` is the M19 source of desired policy state.

Consumers must explicitly opt into a policy key. Unknown or unused policies do
not automatically alter operational behavior.

## Secrets boundary

Control Plane policy JSON is configuration, not secret storage.

Secret-like keys are rejected recursively and policy documents are size-bounded.

Future integrations that need credentials must use a dedicated secret-management
boundary rather than this table.

## Authorization

Two permissions form the public contract:

- `control_plane.view`
- `control_plane.manage`

RLS repeats the authorization at the database layer.

The HTTP layer and the database layer therefore both enforce the same
institution-scoped boundary.

## Event integration

Each managed change emits a versioned M18 canonical event.

M19 does not publish directly to an external broker.

The existing transactional outbox remains the reliability boundary, and M18
ingests those events into the immutable Event Ledger.

## Health semantics

The M19 summary is deliberately narrow. It measures control-plane-relevant
platform convergence:

- outbox -> ledger
- ledger -> projection
- managed capability -> effective capability

It does not claim to represent every infrastructure dependency or external
service.

## Future extension points

M19 is the intended base for:

- institutional feature rollout controls
- controlled policy consumers
- maintenance/change windows
- configuration approval flows
- multi-institution fleet views
- external integration governance
- deployment/control-plane telemetry

Those capabilities can be added without changing the M19 revision contract.
