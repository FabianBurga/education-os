# Agent orchestration contract v1

## Runtime and topology

Use one VS Code window, one Codex terminal and one root agent A0. Native
delegated subagents are available in this environment. A0 may coordinate at
most three concurrently active delegates (the four-agent total includes A0).
Nested delegation is prohibited. Do not add Codex App, Agents API, external
orchestrators, Redis, queues, extra terminals/windows or worktrees.

Only A0 decomposes work, chooses context, activates agents, grants temporary
file ownership, coordinates integration, authorizes migrations, runs Git
mutations, publishes canonical memory and makes PASS/HOLD decisions. A0 must
obtain explicit human approval before push/tag/release.

## Root locks and migration lock

Root-locked by default: `AGENTS.md`; `docs/ROADMAP.md`,
`docs/CURRENT_STATE.md`, `docs/PROJECT_HANDOFF.md`, `docs/AI_CONTEXT.md`,
`docs/project_state.json`; `docs/memory/**`; Alembic migrations/config; CI/CD,
environment config and dependency lockfiles; global permission definitions,
canonical event contracts and cross-domain authority contracts. Only A0 edits
these unless a Task Contract grants explicit temporary ownership.

Migration concurrency is one. Sequence: detect/report need → A0 evaluates
authority → A0 appoints one migration owner → implement → A3 reviews security
impact → A4 validates → A0 integrates. Never allow competing Alembic heads.

## Delegation gate

Delegate only when tasks are independent, parallel work saves time, context is
bounded and write scopes do not overlap. Keep trivial/sequential tasks with A0.
Pick only agents needed for the wave; never fill the concurrency limit as a
target. Do not allow a child agent to spawn another agent.

Every assignment uses `TASK_CONTRACT_TEMPLATE_V1.md`. Stop an agent if it needs
files outside its WRITE_SCOPE. At wave boundaries A0 reconciles evidence and
locks; security-sensitive product decisions return to A0/human rather than
being inferred by a delegate.

## Memory and evidence

Canonical memory lives under `docs/memory/`; code truth remains Git/repository
evidence. A0 alone edits memory. Delegates report compact `MEMORY_DELTA` with
NEW_FACT, NEW_DECISION, NEW_DEBT, INVALIDATED_FACT and VALIDATION_DELTA.
Repository evidence wins on contradiction. If memory is fresh and sufficient,
do not reconstruct M0–M28.

Use `tools/build_task_context.py` for bounded task context,
`tools/project_preflight.py` for initial state and
`tools/validate_project_memory.py` / `tools/check_architecture.py` for cheap
gates. These helpers are deterministic aids, not authorization or security
approval.
