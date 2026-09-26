# M27-7 — Rector & Coordination Experience

M27-7 adds one permission-driven institutional experience at `/app/accountability`.
It is shared by Rector and Academic Coordinator contexts; effective permissions,
signed institution scope and backend services remain authoritative.

## Journey

The operational path is queue → case detail → human review → human decision →
obligation/evidence → outcome and metrics. Queue reasons, ownership, priority,
SLA/compliance, freshness and provenance are read from M27 APIs. The client does
not recalculate case identity, priority, SLA, attention reasons, authorization,
small-cell thresholds or metric ratios.

Case detail exposes minimized lineage, review/decision history, obligations,
M22 context and M21 references. Commands are idempotent and refetch after
success. A 409 is shown as a concurrency conflict and does not overwrite the
new backend state.

## Commands and authority

The thin command API wraps existing M27-3/M27-4 services:

* `POST /accountability/cases/{case_id}/owner/assign|transfer|unassign`
* `POST /accountability/cases/{case_id}/review`
* `POST /accountability/cases/{case_id}/decision`
* `POST /accountability/obligations/{obligation_id}/complete|waive`

`CREATE_INTERVENTION` records a M27 decision only; it does not create an M21
intervention. `REQUEST_INFORMATION` uses the existing service path to create an
`INFORMATION_REQUIRED` obligation. Completion requires one of the closed
evidence types supplied by M27-4. Waiver is distinct from completion and is
reasoned/audited by the backend.

## Metrics, Mentor, privacy and errors

The metrics panel presents definitions, status, freshness and policy version.
`NOT_COMPUTABLE`, `NOT_EVALUABLE`, `INSUFFICIENT_EVIDENCE` and `SUPPRESSED` are
shown as explicit states; suppressed cells never get reconstructed in the
browser. Administrative Time Saved remains `NOT_COMPUTABLE / BASELINE_REQUIRED`.

M26 Mentor remains an L0 explanation surface. It is not used for commands and
cannot assign, review, decide, complete, waive, create interventions or close
cases. The UI distinguishes 403, 404, 409, 422, stale/not-evaluable and server
errors.

The layout reuses the existing Education OS shell, cards, buttons, TanStack
Query and router. It is usable on desktop/tablet and collapses queue/detail
grids on narrow screens. Labels, status text and focusable controls do not rely
on color alone.
