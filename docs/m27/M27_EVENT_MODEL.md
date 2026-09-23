# M27 — Event Model

M18 remains the canonical event ledger and chronology. M27 emits only facts for
new M27-owned concepts; M21 intervention/action/follow-up/outcome events and
M22 intelligence events are referenced, never duplicated.

Every event contains opaque event ID/type, occurred/recorded timestamps,
organization/institution scope, actor or system origin, correlation and
causation IDs, source lineage, policy/version context, and provenance hash.
Payloads are minimized and contain no raw provider internals or unnecessary
PII.

| Event | Why it is needed |
| --- | --- |
| `accountability.case.opened` | establishes M27 episode identity and lineage |
| `accountability.case.assigned` | records M27 accountable owner changes; distinct from M21 assignment |
| `accountability.review.completed` | records human assessment, evidence, disposition, and permission context |
| `accountability.decision.recorded` | records bounded institutional disposition and provenance |
| `accountability.obligation.created` | records a new M27 responsibility |
| `accountability.obligation.completed` | records evidence that the responsibility was fulfilled |
| `accountability.case.resolved` | records closure of the M27 episode |
| `accountability.case.reopened` | records a resolved case becoming active within the reopen window |

An event is emitted only when the fact cannot be derived unambiguously from an
existing authoritative event. Projection refreshes, metric calculation, and
provider explanations do not emit lifecycle events.

## Derived state and bounded transitions

Case lifecycle, owner, current obligation, SLA, recurrence, and pending review/
decision state derive from ordered M27 events plus M18/M21/M22 references. A
future read model is rebuildable and versioned; it is not authoritative.

Normal path is `OPENED → ASSIGNED → UNDER_REVIEW → DECIDED → OBLIGATION_OPEN →
RESOLVED`. Required intermediate states may be omitted. Only
`RESOLVED → REOPENED → UNDER_REVIEW` reopens a case. Duplicate decisions,
completion without an open obligation, missing review evidence, and
cross-tenant references are rejected. Corrections are new events or new
projections, never destructive history edits.

An owner transfer is a new `accountability.case.assigned` event with prior
owner reference, new primary owner, permitted collaborators, effective
permission context, and provenance. `UNASSIGNED` is explicit, not implicit.
`REQUEST_INFORMATION` creates or links an information obligation; it does not
emit an intervention event.

## Replay

Projection rebuild consumes the ledger in order and applies named identity and
policy versions. The same source set and versions must produce the same result.
New policy versions create new metric/projection versions and preserve
historical events. Late source facts trigger explicit recalculation with
provenance, not silent rewriting.
