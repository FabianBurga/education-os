# M27 Institutional Accountability Queue

M27-5 is a read-only service over the M27 case, review, decision,
ownership and obligation projections. M21 remains authoritative for
interventions, actions, follow-ups and outcomes; M22 remains authoritative
for signals, priorities and intelligence snapshots. The queue stores no new
authority and emits no event when read.

## Queue item

Each item returns the case and episode identity, source and normalized
categories, current accountable owner state, bounded review and decision
requirements, at most the most urgent open obligation, due/SLA/compliance
state, an optional M22 priority reference, freshness, projection/policy
versions, and provenance references. Raw provider payloads, hidden reasoning,
and unnecessary student PII are excluded.

## Reasons and next step

Reasons are the bounded values `UNASSIGNED`, `REVIEW_REQUIRED`,
`DECISION_REQUIRED`, `INFORMATION_REQUIRED`, `FOLLOW_UP_REQUIRED`,
`OBLIGATION_DUE`, and `OBLIGATION_OVERDUE`. They are derived from persisted
case/review/decision/obligation state; there is no score or model ranking.

`REVIEW_REQUIRED` is a queue reason. `HUMAN_REVIEW_REQUIRED` is the separate
obligation next-required-step value. They are intentionally not aliases.

The next step is one of `ASSIGN_OWNER`, `HUMAN_REVIEW`, `RECORD_DECISION`,
`PROVIDE_INFORMATION`, `COMPLETE_FOLLOW_UP`, `WAIT_FOR_DUE_DATE`, or
`NO_IMMEDIATE_ACTION`. It describes the next permitted human/service boundary;
it does not execute a command.

## Ordering and filters

The total order is ascending by:

1. attention precedence: overdue open obligation, due open obligation,
   unassigned case, review required, decision required, M22 HIGH priority,
   other;
2. bounded M22 priority (`HIGH`, `MEDIUM`, `LOW`, absent);
3. due timestamp (nulls last);
4. case creation timestamp;
5. stable case UUID.

The order is contractual and contains no arbitrary weights. Filters are
owner/unassigned, reason, case lifecycle, normalized category, M22 priority,
obligation type, compliance status, due window, review requirement, and
decision requirement. Pagination is tenant-bound keyset pagination over the
same tuple.

## Freshness, policy and privacy

The response includes generation time, source freshness where available,
projection version, policy versions, and provenance. The queue does not infer
staleness from an arbitrary time threshold; a policy-backed freshness rule is
required before a stale reason can be emitted. `NOT_EVALUABLE` remains
explicit when SLA or freshness policy/evidence is unavailable.

Authorization uses effective permission, scope, and principal-derived tenant
context. The API does not trust a client-supplied tenant identifier. Detail
views are minimized and fail closed outside the principal's case scope.

## Read API

* `GET /api/v1/accountability/queue`
* `GET /api/v1/accountability/queue/items/{case_id}`
* `GET /api/v1/accountability/cases/{case_id}/accountability`

These endpoints call the query service only. They do not mutate M18, M21,
M22, or M27 state and do not emit read events.
