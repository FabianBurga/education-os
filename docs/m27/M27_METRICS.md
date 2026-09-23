# M27 — Accountability Metrics Contract

All metrics are tenant-scoped, versioned, recomputable projections. Every
result carries metric/version, window, freshness, policy/calculator version,
numerator, denominator, exclusions, minimum evidence, and provenance. Missing
denominators are `NOT_COMPUTABLE`, never zero.

| Metric | Business question | Start → end | Numerator / denominator | Window / exclusions | Evidence / freshness / provenance | Privacy / derivability |
| --- | --- | --- | --- | --- | --- | --- |
| Time to Detection | How quickly was an actionable case registered? | source event accepted → case opened | valid detection timestamps / eligible cases | exclude malformed, duplicate, test, out-of-scope sources | M22/M18 source + M27 event; ledger refresh; IDs and policy | aggregate; derived from existing sources + M27 event |
| Time to Review | How quickly was required review completed? | case opened/review-required → review completed | on-time required reviews / reviews due | exclude authorized waivers and invalid opening times | M27 case/review events and permission context | scoped aggregate; derived |
| Time to Intervention | How quickly did accepted intent reach M21? | create-intervention decision → M21 accepted creation | accepted creations in target time / eligible create decisions | exclude rejected/unauthorized/duplicate attempts | M27 decision + M21 service/event result | scoped aggregate; derived, no duplicate intervention |
| Follow-up Compliance | Were obligations completed on time? | obligation created → completion/waiver/expiry | on-time completions / obligations due or terminal | valid waivers excluded with reason; retained separately | obligation events + M21 evidence; policy freshness | aggregate; derived |
| Lost Case Rate | What proportion became unaccounted for? | case opened → observation cutoff | lost cases / eligible cases at closed cutoff | exclude invalid/test/unknown scope/incomplete window | case/review/decision/obligation ledger, cutoff, policy | aggregate with suppression; derived |
| Recurrence Rate | How often did resolved cases recur? | resolved case → new episode | true recurrences / resolved cases with full window | exclude reopen, continuation, related category, incomplete window | identity resolver + lineage; post-window refresh | aggregate; derived, versioned |
| Intervention Outcome | What was observed after intervention? | M21 creation → outcome window end | interventions with observed outcome / eligible interventions | report missingness; no causal inference | M21 intervention/outcome refs and window | aggregate/suppressed; derived |
| Decision Accountability Rate | Were required decisions recorded on time? | decision-required case → decision | on-time required decisions / decisions due | exclude policy-waived requirements | M27 case/decision events | aggregate; derived |
| Review Accountability Rate | Were required reviews completed on time? | review-required case → review | on-time reviews / reviews due | exclude authorized waivers only | M27 review events with actor/evidence | aggregate; derived |
| Next Action Compliance | Were next steps completed or waived by due date? | obligation created → completion/waiver | on-time completion/waiver / obligations due | exclude pre-due cancellation; late remains non-compliant | obligation lifecycle + evidence | aggregate; derived |
| Administrative Time Saved | Did a validated workflow reduce human time? | approved task baseline → measured completion | **NOT COMPUTABLE from existing logs** | requires pre-registered baseline, sample, task definition and consent | future human measurement model and provenance | no value until approved; new model required |

SLA-derived metric states are `NOT_EVALUABLE` when applicable M19 policy or
freshness contract is absent. Aggregate metrics reuse an applicable repository
privacy contract; otherwise M19 fail-closed policy yields `SUPPRESSED` or
`NOT_EVALUABLE`.

## Lost Case mathematical contract

For policy `p` and window `W`,

`LostCaseRate(p,W) = |L(p,W)| / |E(p,W)|`.

`E(p,W)` contains cases opened in `W` whose observation/grace window closed by
the cutoff. `L(p,W)` contains those cases with no valid completed review, no
valid bounded decision, and no valid open/complete obligation evidence by the
cutoff, except an authorized policy waiver. Invalid provenance, test data,
unknown scope, and not-yet-closed observation windows are excluded from both
sets and reported as data quality, not silently discarded. The policy version,
grace period, freshness tolerance, and cutoff identify the calculation.

## Freshness and outcomes

Stale sources produce `STALE` or `NOT_COMPUTABLE`, not zero. Provenance names
source events/snapshot hashes, permitted case/obligation refs, policy,
calculator version, scope, cutoff, and exclusions. Outcomes are temporal
associations only; M27 prohibits causal claims. Administrative Time Saved is
explicitly not inferred from audit, click, or event logs.
