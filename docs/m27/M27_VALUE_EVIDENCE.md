# M27-8 Value Evidence

This document separates deterministic software evidence from claims that need
people or a real institution.

## Measured in the automated synthetic pilot

- Queue-to-case continuity, ownership, human review, bounded decision,
  obligation completion/waiver, M21 outcome reference, provenance and replay.
- `TIME_TO_REVIEW`, `TIME_TO_INTERVENTION`, `FOLLOW_UP_COMPLIANCE`,
  `LOST_CASE_RATE`, `RECURRENCE_RATE`, `REVIEW_ACCOUNTABILITY_RATE`,
  `DECISION_ACCOUNTABILITY_RATE`, and `NEXT_ACTION_COMPLIANCE` are produced
  through the M27 metric service over a bounded deterministic window.
- Case trace completeness and seeded accountability-gap detection are 100% in
  the deterministic fixture; tenant leak and autonomous high-impact mutation
  are both 0.
- Small-cell responses omit numerator, denominator, ratio and complements.

These are correctness observations about synthetic data, not institutional
outcomes or business-value claims.

## Requires human observation

`TIME_TO_PRIORITY_IDENTIFICATION` needs a human-operated timing instrument:
start when a rector opens the accountability experience and stop when the
target case is correctly identified. The automated harness cannot claim human
cognition or usability time.

The administrative-time instrument records task, baseline method, traditional
duration, Education OS duration, sample, role, conditions, notes and
provenance. No values are populated in M27-8. The product result remains
`NOT_COMPUTABLE`, reason `BASELINE_REQUIRED`.

## Requires a real field pilot

Institutional usefulness, adoption, workload reduction, sustained follow-up
behavior, false-attention rates with real users, and any causal intervention
outcome require an approved field design and real observation. M27 makes only
observational statements such as “after the intervention, an outcome was
observed”; it does not claim causation or rank interventions.
