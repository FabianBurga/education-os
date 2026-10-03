# Runbook v1

1. Verify `git status --short`, branch and HEAD. A non-clean/unexpected base is
   HOLD until reconciled with the user/task contract.
2. Run `tools/project_preflight.py`. If memory is fresh, inspect only the
   anchor-to-HEAD log/name-only diff before deciding on more discovery.
3. Validate memory and architecture; choose the smallest required context.
4. A0 writes Task Contracts, selects independent tasks and assigns exact
   READ_SCOPE/WRITE_SCOPE. Enforce one write owner per file per wave.
5. Discovery wave is read-only. A0 reconciles findings, authority, risks and
   human decisions before assigning implementation.
6. Implementation owners stay within scope. Escalate migration/RLS/shared
   permissions/events/root-locked files and unresolved product/privacy choices.
7. Validate in focused → directed → security/integration → impact/full order.
   A4 independently reports bounded evidence when assigned.
8. A0 reviews diffs for product scope, tenant/privacy boundaries, source vs
   generated artifacts, validation evidence and memory delta.
9. Only A0 mutates Git or publishes accepted memory. Verify clean state after
   commit. Push/tag/release require explicit human approval.

Stop/report on a dirty unexpected base, scope expansion, overlapping writes,
unclear authority, sensitive product decision, security boundary change,
migration need without approval, native delegation unavailable, or any helper
that proposes an uncertain narrow test set.
