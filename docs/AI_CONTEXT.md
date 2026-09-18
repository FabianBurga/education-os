# Education OS — AI Continuity Context

Project: Education OS, an Institutional Intelligence & Action Platform.

Authoritative committed source: `57aea73c71a403c2b85024dc0e554c011fa258a7` (`feat(m25): expand governed read-only agents`).

Current database revision: `0036_m25_run_explainer`.

Active milestone: M25-3 — Governed Evidence & Provider Integration.

Current working state is not committed:

- M25-3A Evidence Pack Foundation — PASS.
- M25-3B Provider Routing, Budget Admission, and Fake Provider — PASS.
- M25-3C `integration_run_explainer` runtime â€” PASS / technically closed.
- M25-3D fake-provider controlled pilot â€” PASS.
- M25-3E optional live-provider pilot â€” not executed; live providers remain unavailable by design.

Do not confuse the M25-2 committed source with the validated, uncommitted M25-3 worktree. The next step is the approved M25-3 source-control commit; do not claim a live-provider validation.

Before changing code, read [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md), [ARCHITECTURE.md](ARCHITECTURE.md), [CURRENT_STATE.md](CURRENT_STATE.md), [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md), and [KNOWN_ISSUES.md](KNOWN_ISSUES.md). Then verify `git status`, `git rev-parse HEAD`, `alembic heads`, and `alembic current`.

Non-negotiable boundaries: FORCE RLS, principal-derived tenant scope, effective-permission authorization, closed tool gateway, append-only audit, deterministic planner/verifier, no arbitrary SQL/shell/HTTP/tools, no raw DB-to-provider path, no persisted credentials/raw prompts/raw provider responses, and no L2+ autonomy without a future approved milestone.
