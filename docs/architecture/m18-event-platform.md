# M18 Event Platform Architecture

## Invariant

Operational domain tables remain the current-state source of truth.

The ledger records what happened. Read models optimize how derived information
is consumed.

## Flow

```text
Domain transaction
      |
      v
outbox_events
      |
      | idempotent ingest
      v
event_ledger  (immutable)
      |
      | checkpointed projection
      v
+---------------------------+
| institution_event_daily   |
| aggregate_activity_*      |
+---------------------------+
```



## Frozen outbox compatibility

M18 does not add columns to `outbox_events`.

Canonical producers place metadata in this reserved shape:

```json
{
  "_education_os_event": {
    "version": 1,
    "actor_user_id": null,
    "correlation_id": null,
    "causation_id": null,
    "metadata": {}
  },
  "data": {}
}
```

This preserves historical native-milestone database compatibility while giving
M18+ producers a versioned contract.

## Event identity

For the transactional-outbox source, the canonical ledger `id` equals the
source outbox event ID. `source_outbox_event_id` is also persisted explicitly
for lineage and uniqueness.

## Ordering

`event_ledger.position` is a database-generated monotonic position used only
for deterministic projection progress.

Business chronology remains `occurred_at`; ingestion chronology is
`recorded_at`.

## Correlation

`correlation_id` groups events belonging to one broader flow.

`causation_id` points to the event that directly caused another event when the
producer knows it.

Both are optional so legacy events remain ingestible.

## Projection consistency

A projector reads events after its `last_position`.

Read-model mutations and checkpoint advancement use one SQL transaction.

Therefore:

- a failed transaction replays safely
- a committed transaction does not replay already-counted events
- duplicate outbox ingestion is blocked by a unique source key

## No distributed broker yet

M18 intentionally does not introduce Kafka, RabbitMQ or a separate streaming
cluster.

PostgreSQL + the existing outbox is sufficient for the current scale and keeps
operations simple.

A broker can be introduced later behind the event-platform boundary if measured
load requires it.

## Future consumers

M18 is designed to support:

- M19 institution control-plane telemetry
- M21 student longitudinal timeline
- M21 intervention outcomes
- M22 AI context/evidence
- M23 integration adapters
- advanced analytics

Those consumers should depend on canonical event contracts and read models, not
on ad-hoc joins across transactional tables.
