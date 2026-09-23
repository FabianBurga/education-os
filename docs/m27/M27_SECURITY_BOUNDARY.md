# M27 — Security and Governance Boundary

## Authorization

Visibility is the intersection of effective permissions, tenant context, and
subject/institution scope. Nominal role names are insufficient. The principal,
organization, institution, permitted subject scope, and effective permission
set are resolved before evidence assembly and remain bound through projection
and metrics.

| Role | Default posture (still permission and scope checked) |
| --- | --- |
| SYSTEM_ADMIN | tenant/institution accountability management within explicit scope |
| RECTOR | institution queue, review, decision, and metrics within assigned institution |
| ACADEMIC_COORDINATOR | assigned academic/institution scope where granted |
| TEACHER | assigned subject/class scope only; no institution-wide queue |
| STUDENT | own scope only if a future policy explicitly grants it |
| GUARDIAN | permitted ward scope only if explicitly granted |

Candidate M19 capabilities are `accountability.view`, `.review`, `.decide`,
`.manage`, and `.audit.read`; review and decision remain distinct. They must be
registered/versioned by the Control Plane and never inferred from role labels.

## Tenant, RLS, and disclosure

Future persistence must preserve FORCE RLS, composite tenant links,
application-role restrictions, and bounded grants. Out-of-scope or cross-tenant
objects use existing non-disclosure/404 conventions. Counts apply the same
scope filter as rows. Cross-institution aggregation requires explicit policy.

Institution views expose aggregate evidence, category, freshness, SLA state,
and opaque provenance; they suppress unnecessary student/guardian PII, small
cells, sensitive free text, provider internals, credentials, raw prompts, and
hidden reasoning. Subject views inherit source authorization.

Aggregate privacy reuses an applicable repository threshold. If no applicable
threshold exists, M19 must provide a versioned fail-closed policy; the result
is `SUPPRESSED` or `NOT_EVALUABLE`, never an exposed small cell.

## Human control and governed agents

M27 has no autonomous high-impact authority. M25/M26 agents may explain only
authorized Evidence Packs under their closed gateway, deterministic planner and
verifier, budget, audit, and tenant boundaries. Providers cannot choose tenant,
permission, identity, owner, policy, event, or domain mutation. A
`CREATE_INTERVENTION` decision must pass the existing human approval and M21
authoritative service path.

## Provenance and policy

Reviews and decisions record actor, time, effective permission context, evidence
lineage, disposition, next step, policy version, and provenance. M27 events are
append-only in M18; projections reveal calculation/projection version and
freshness. M19 versions SLA targets/grace, recurrence/reopen window, lost-case
definition, freshness tolerance, metric calculators, priority/queue ordering,
capability rollout, evidence minima, privacy suppression, and waivers.

## Rejected threat paths

Reject client-supplied tenant/scope fields, fabricated lineage, unbacked
citations, cross-tenant source IDs, duplicate event transitions, replayed
decisions, unauthorized owner changes, and stale evidence beyond policy
tolerance. No generic SQL, shell, browser, unrestricted HTTP/tool, or raw
database-to-model path is introduced.
