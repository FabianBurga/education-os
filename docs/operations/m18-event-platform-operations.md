# M18 Event Platform Operations

## Health questions

When investigating the event platform, check in this order:

1. outbox events exist
2. ledger ingestion position is moving
3. projection checkpoint is moving
4. read-model row counts are plausible
5. dropped runtime log metric is not increasing abnormally

## Pipeline lag

M18 does not yet create a permanent background scheduler. The pipeline service
is deliberately callable and independently testable.

A later operational milestone may schedule it through the existing async worker
or deployment scheduler.

Until then, the important invariant is that each run is idempotent.

## Safe read-model rebuild

Never edit `event_ledger` to repair a projection.

Read models can be rebuilt because they are derived. The ledger is the durable
history.

Owner-only maintenance should:

- backup first
- clear only the affected projection rows
- reset only its checkpoint
- replay ledger positions from zero
- validate counts before returning to service

## Alert candidates for later monitoring

- outbox rows not represented in ledger
- ledger latest position minus projection checkpoint
- projector failures
- unexpected ledger mutation attempts
- projection duration
- read-model rebuild duration

## Pilot performance budget

For the controlled pilot:

- pipeline batch limit: max 5000
- recent event API: max 200 metadata rows
- daily read-model API: max 500 rows
- no raw payload returned by read endpoints

These are operational guards, not long-term scale limits.
