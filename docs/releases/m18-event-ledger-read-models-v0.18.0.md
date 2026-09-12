# Education OS — M18 Event Ledger + Read Models v0.18.0

## Frozen base

M18 starts from:

- tag: `v1.0.0-rc7`
- commit: `8f949c08ab120c7e3521aa27d4a6f563fabc7d73`
- database: `0016_m14`

M18 target:

- milestone tag: `m18-event-ledger-read-models-v0.18.0`
- database head: `0017_m18`

Production `v1.0.0` remains unreleased.

## Purpose

M18 adds a durable platform memory without replacing PostgreSQL as the
operational source of truth.

The architecture is:

`Transactional Outbox -> Canonical Event Ledger -> Projection Checkpoint ->
Read Models`

M18 is **not** full event sourcing. Existing domain tables remain authoritative
for current operational state.

## Canonical ledger

`event_ledger` is append-only and stores:

- canonical event ID
- monotonic ledger position
- organization and institution scope
- source lineage
- event type and event version
- aggregate type and aggregate ID
- actor, correlation and causation IDs when available
- payload and metadata
- occurrence and recording timestamps

The first source adapter is the existing transactional outbox.

The source outbox event ID is unique in the ledger, making ingestion
idempotent.

## Outbox envelope extension

M18 deliberately preserves the frozen `outbox_events` table schema so native
M11-M17 database revisions remain executable with current code.

The legacy `enqueue_event()` API remains unchanged.

New M18+ producers can use `enqueue_canonical_event()`. Versioning, actor,
correlation, causation and metadata are carried inside a reserved
`_education_os_event` envelope within the existing `payload_json` column.

The ledger ingestion adapter unwraps that envelope. Legacy outbox rows without
the envelope are ingested as event version `1` with `legacy_envelope=true`
metadata.

## Read models

M18 introduces:

### `institution_event_daily`

Daily counts by institution, event type and event version.

### `aggregate_activity_snapshots`

First/last event position, timestamps, count and last event metadata for each
aggregate.

### `projection_checkpoints`

Durable progress for each projection. M18 ships
`institution_activity_v1`.

Projection progress and read-model writes occur in the same transaction so a
failed run cannot advance the checkpoint without its read-model changes.

## Security

All M18 tables use PostgreSQL RLS + FORCE RLS.

Ledger/read-model SELECT requires:

- `admin.console.access`, or
- `coord.analytics.view`

Pipeline writes require `admin.console.access`.

Teachers, students and guardians cannot read the ledger directly.

`event_ledger` has no runtime UPDATE/DELETE grant and also has database
triggers that reject UPDATE, DELETE and TRUNCATE even when attempted by the
owner role.

## Privacy

The recent-events API deliberately returns event metadata only. It does not
return `payload_json` or `metadata_json`.

The runtime `education_app` role receives column-level SELECT only for ledger
metadata. Raw `payload_json` and `metadata_json` are not directly selectable by
runtime analytics readers, even when RLS permits the row.

Future specialized read models must continue data minimization rather than
turning the ledger into a broad PII API.

## Versioning rule

Canonical event types are stable names such as:

- `attendance.recorded`
- `grade.published`
- `student.enrolled`

Breaking payload changes require a new integer `event_version`.

Consumers must not reinterpret an old version silently.

## Recovery / rebuild

Read models are derived state.

If a read model becomes corrupt:

1. preserve evidence and backup
2. stop the projector
3. reset the affected read model/checkpoint using an owner-only maintenance
   procedure
4. replay the immutable ledger
5. compare counts and checkpoints
6. reopen the projector

The ledger itself is not rebuilt from read models.

## M18 Definition of Done

M18 must prove:

- migration `0016_m14 -> 0017_m18`
- downgrade back to `0016_m14`
- full backend regression
- M7-M17 frozen regressions
- canonical event lineage
- version and correlation preservation
- idempotent outbox ingestion
- idempotent checkpointed projection
- read-model correctness
- ledger immutability
- coordinator read / teacher deny boundary
- admin-only pipeline execution
- direct PostgreSQL RLS negative test
- backup/restore of accepted `0017_m18`
- safe PRIMARY promotion after disposable acceptance
- final PRIMARY head `0017_m18`

Formal freeze additionally requires:

1. local acceptance
2. commit
3. push to `main`
4. main CI success
5. annotated milestone tag
6. tag CI success
