# Education OS — agent entry point

## Current canonical state

M29 — Teacher & Family Continuity, current task M29-AO — Agent Orchestration +
Project Memory + Efficiency Foundation, on `m29-teacher-family-continuity`.
M29-0 contract/discovery is PASS. M28 v0.28.0 is the
immutable published baseline: tag `m28-operational-adoption-core-v0.28.0`,
commit `c21e7c1287a8bc7abd8f355aa619e67c0beee0c4`; Alembic head
`0046_m28_attendance_perms`.

## Read first

1. `docs/memory/PROJECT_STATE.json` — machine-readable state/anchor.
2. `docs/memory/CURRENT_CONTEXT.md` — current facts, open decisions and next step.
3. `docs/memory/AUTHORITY_MAP.md` — M17–M28 ownership and earlier domain owners.
4. `docs/m29/` — current milestone contract, capability evidence and privacy boundaries.
5. `docs/agent_orchestration/ORCHESTRATION_CONTRACT_V1.md` and
   `QUALITY_GATES_V1.md` — delegation, ownership and validation rules.
6. Applicable detailed security docs: `docs/m29/M29_PRIVACY_BOUNDARY.md`,
   `docs/m28/M28_SECURITY_BOUNDARY.md`, `docs/m27/M27_SECURITY_BOUNDARY.md`,
   and M0–M20 ADRs/contracts as the task requires.

Do not reconstruct M0–M28 when canonical memory is fresh and covers the task.
Repository evidence wins if it contradicts memory. If HEAD differs from
`memory_anchor_commit`, first inspect only `git log ANCHOR..HEAD --oneline` and
`git diff --name-only ANCHOR..HEAD` before deciding on broader discovery.

## Authority and security invariants

- Preserve tenant isolation, FORCE RLS, RBAC/domain scope, least privilege,
  auditability, idempotency, transactional outbox and minor-data privacy.
- Existing M0–M28 domain authorities remain authoritative. M29 must not create
  parallel timeline, intervention, accountability, communications, event or
  offline engines.
- Human decisions remain human-controlled. No autonomous high-impact academic
  action or provider authority.
- A0 alone coordinates subagents, owns integration/memory/Git mutations and
  PASS/HOLD. Push/tag/release require explicit human approval.
- One writer per file per wave. Migrations, RLS, global permissions, canonical
  event contracts, root-locked files and cross-domain boundaries require A0
  authorization. Security review is read-only by default.
- Stop and report if product/privacy intent is unresolved or scope expands.

Use `tools/project_preflight.py`, `tools/validate_project_memory.py`,
`tools/build_task_context.py`, `tools/select_tests.py` and
`tools/check_architecture.py` as deterministic helpers, not as substitutes for
human architecture/security review. See `docs/agent_orchestration/RUNBOOK_V1.md`.
