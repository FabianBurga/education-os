# M27-6 — Accountability Metrics & Outcome Intelligence

M27-6 is a read-only, tenant-scoped derived view over M18 chronology, M19
effective policy, M21 interventions/outcomes and M27 case, review, decision and
obligation projections. It adds no persistence and emits no events.

The closed registry contains `TIME_TO_DETECTION`, `TIME_TO_REVIEW`,
`TIME_TO_INTERVENTION`, `FOLLOW_UP_COMPLIANCE`, `LOST_CASE_RATE`,
`RECURRENCE_RATE`, `INTERVENTION_OUTCOME`, `REVIEW_ACCOUNTABILITY_RATE`,
`DECISION_ACCOUNTABILITY_RATE`, `NEXT_ACTION_COMPLIANCE`, and
`ADMINISTRATIVE_TIME_SAVED`. Results contain metric/version, bounded status,
value/unit, numerator/denominator, half-open UTC window, population, filters,
exclusions, missingness, freshness, policy/projection versions, generation
time, explanation and bounded provenance digest.

Effective M19 `accountability.metrics` policy supplies the small-cell threshold.
Missing or malformed policy fails closed. Institution and cohort scope remains
principal-derived; unsupported cohorts are rejected. M21 is the sole authority
for intervention outcomes. Summaries state only what was observed after an
intervention and never claim causality or rank interventions.

The bounded formulas are: `LostCaseRate = lost eligible cases / eligible
cases whose observation window closed`; `RecurrenceRate = TRUE_RECURRENCE /
resolved cases with a complete recurrence window`; `FollowUpCompliance =
on-time completed obligations / due or terminal obligations` (authorized
`WAIVED` obligations are retained as `EXEMPT`); `ReviewAccountabilityRate =
valid human reviews / review-required eligible cases`; `DecisionAccountabilityRate
= valid M27 decisions / decision-required eligible cases`; and
`NextActionCompliance = on-time completion or authorized waiver / obligations
with a valid due date`. Open is not lost, and continuation/reopen/related
episodes are not recurrence numerators.

Every result carries an explanation of population, window, numerator,
denominator, exclusions, policy version, freshness and bounded provenance.
Stale or missing policy evidence is never represented as a current zero.

Administrative Time Saved is always `NOT_COMPUTABLE` with reason
`BASELINE_REQUIRED`; no event, click or log count becomes minutes.

Read API:

* `GET /api/v1/accountability/metrics`
* `GET /api/v1/accountability/metrics/{metric_id}`
* `GET /api/v1/accountability/metrics/{metric_id}/definition`
* `GET /api/v1/accountability/outcomes`

All endpoints require effective `accountability.view` and signed tenant /
institution scope. Windows are UTC and half-open `[start,end)`.
