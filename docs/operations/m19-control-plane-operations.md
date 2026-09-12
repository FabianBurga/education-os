# M19 Institution Control Plane Operations

## What to inspect first

For a Control Plane incident, check:

1. `/api/v1/control-plane/summary`
2. capability drift count
3. unledgered outbox count
4. Event Ledger latest position
5. projection checkpoint and lag
6. recent Control Plane changes
7. audit records for the same revision

## Capability drift

Drift means:

- the Control Plane previously managed a capability
- the effective value in `institution_capabilities` now differs from the most
  recent managed value

A capability with no Control Plane history is considered legacy/unmanaged, not
drifted.

To reconcile:

1. verify the effective value is intended
2. use the Control Plane to set the desired value
3. provide a reason
4. confirm drift returns to zero
5. drain the M18 event pipeline if it is not scheduled automatically

## Policy safety

Do not put credentials, API keys, tokens, passwords, private keys, or student
PII in policy documents.

The API rejects secret-like JSON keys, but operational review is still required.

## Immutable history

Never repair a Control Plane issue by editing
`institution_control_changes`.

The table is append-only and protected against UPDATE, DELETE, and TRUNCATE.

If a bad configuration was approved, create a new revision that corrects it.

## Event convergence

A healthy Control Plane requires:

- unledgered outbox = 0
- projection lag = 0
- capability drift = 0

If outbox/ledger lag grows, use the M18 event-platform procedures before
creating more control changes.

## Backup and recovery

M19 acceptance validates backup/restore after the new schema is accepted.

Before production migration:

- create a fresh pre-deploy backup
- verify SHA-256
- migrate a disposable clone first
- run full regressions
- only then migrate PRIMARY

Read-model recovery does not replace database backup for Control Plane state.
