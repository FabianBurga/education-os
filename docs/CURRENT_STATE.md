# Current State

## Formally committed

The latest committed source is `57aea73c71a403c2b85024dc0e554c011fa258a7`, `feat(m25): expand governed read-only agents`. It formally closes M25-2. Closed milestones are M20, M21, M22, M23 backend, M24, M25-1, and M25-2.

## Technically closed, pending source-control commit

M25-3 is validated in the uncommitted worktree at database revision `0036_m25_run_explainer`:

- M25-3A Evidence Pack Foundation â€” PASS / closed within M25-3.
- M25-3B Provider Routing, Budget Admission, and Fake Provider â€” PASS / closed within M25-3.
- M25-3C `integration_run_explainer` â€” technically closed.
- M25-3D controlled fake-provider pilot â€” PASS.
- M25-3E optional live-provider pilot â€” not executed.

The first provider-backed L0 agent is `integration_run_explainer`. Its fake-provider mode and mandatory deterministic fallback are both validated. Successful controlled provider run: `0f706b7f-de79-4bde-ba15-a3b0795bc67a`; it completed in `FAKE_PROVIDER` mode with one in-process call, one valid opaque citation, 30 micro-USD consumed per budget scope, and no domain mutation.

No OpenAI, Anthropic, or local provider call was made. The historical M23 live-provider HOLD EXTERNAL remains open for API-credit/HTTP-429 availability; M25-3 does not close or supersede it.

## Validation evidence

- Focused M25/M24: 70 passed.
- Focused M25 provider/explainer: 28 passed.
- Directed M21/M22/M23: 403 passed.
- Full backend: 641 passed, 1 skipped.
- Ruff, `py_compile`, Alembic source/current, and `git diff --check`: PASS.

## Next

Review and create the single approved M25-3 source-control commit. Live-provider pilot work is optional future M25-3E work and is not authorized by this closure.

## Living documentation rule

A milestone is closed only after technical closure and knowledge closure. Every closure updates this file, [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md), and `docs/project_state.json`; architecture changes also update [ARCHITECTURE.md](ARCHITECTURE.md), [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md), and applicable ADRs.
