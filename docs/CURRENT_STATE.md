# Current State

## Formally closed

M25 - Agentic Control Plane is CLOSED at `bd0fbaa719eae4884d9a6c3ab8600939e88bb433`, `feat(m25): add governed provider-backed explainer`. It is tagged `m25-governed-provider-explainer-v0.25.3` and remotely backed up and verified on `origin` (`FabianBurga/education-os`). The database revision is `0036_m25_run_explainer`.

M25 status:

- M25-1 - CLOSED.
- M25-2 - CLOSED.
- M25-3A Evidence Pack Foundation - PASS.
- M25-3B Provider Routing, Budget Admission, and Fake Provider - PASS.
- M25-3C `integration_run_explainer` - PASS / CLOSED.
- M25-3D controlled fake-provider pilot - PASS.
- M25-3E optional live-provider pilot - OPTIONAL / NOT EXECUTED.

The first provider-backed L0 agent is `integration_run_explainer`. Its fake-provider mode and mandatory deterministic fallback are both validated. Successful controlled provider run: `0f706b7f-de79-4bde-ba15-a3b0795bc67a`; it completed in `FAKE_PROVIDER` mode with one in-process call, one valid opaque citation, 30 micro-USD consumed per budget scope, and no domain mutation.

No OpenAI, Anthropic, or local provider call was made. The historical M23 live-provider HOLD EXTERNAL remains open for API-credit/HTTP-429 availability; M25 does not close or supersede it.

## Validation evidence

- Focused M25/M24: 70 passed.
- Focused M25 provider/explainer: 28 passed.
- Directed M21/M22/M23: 403 passed.
- Full backend: 641 passed, 1 skipped.
- Ruff, `py_compile`, Alembic source/current, and `git diff --check`: PASS.

## Active milestone

M26 - Human Experience Layer / Mentor OS is active on `m26-mentor-os`.

M26-1 - Mentor institution-briefing contract and configuration is CLOSED at
database revision `0037_m26_mentor_briefing`. It seeds
`mentor_institution_briefing` v1 for the controlled tenants with L0 autonomy,
`mentor.institution.brief`, `m22.intelligence_snapshot.inspect`, request type
`M26_INSTITUTION_BRIEFING`, `agents.use` + `intelligence.read`, and
`PROVIDER_OPTIONAL_WITH_DETERMINISTIC_FALLBACK`.

No Mentor runtime, UI, or M26 provider/model configuration has been
implemented. Next task: M26-2 governed Mentor runtime. Live-provider pilot
work remains optional M25-3E work and is not authorized by M25 closure.

## Living documentation rule

A milestone is closed only after technical closure and knowledge closure. Every closure updates this file, [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md), and `docs/project_state.json`; architecture changes also update [ARCHITECTURE.md](ARCHITECTURE.md), [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md), and applicable ADRs.
