# Education OS - AI Continuity Context

Project: Education OS, an Institutional Intelligence & Action Platform.

Authoritative committed source: `bd0fbaa719eae4884d9a6c3ab8600939e88bb433` (`feat(m25): add governed provider-backed explainer`).

Authoritative M25 release tag: `m25-governed-provider-explainer-v0.25.3`.

Current working branch: `m26-mentor-os`.

Current database revision: `0037_m26_mentor_briefing`.

Active milestone: M26 - Human Experience Layer / Mentor OS.

M26-1 is CLOSED. It adds the persisted L0 `mentor_institution_briefing` v1
configuration only: `mentor.institution.brief`,
`m22.intelligence_snapshot.inspect`, `M26_INSTITUTION_BRIEFING`,
`agents.use` + `intelligence.read`, and
`PROVIDER_OPTIONAL_WITH_DETERMINISTIC_FALLBACK`. No Mentor runtime, UI, or
M26 model/provider configuration exists yet. Next task: M26-2 governed Mentor
runtime.

M25 - Agentic Control Plane is CLOSED and remotely backed up to `origin` (`FabianBurga/education-os`).

- M25-1 - CLOSED.
- M25-2 - CLOSED.
- M25-3A Evidence Pack Foundation - PASS.
- M25-3B Provider Routing, Budget Admission, and Fake Provider - PASS.
- M25-3C `integration_run_explainer` runtime - PASS / CLOSED.
- M25-3D fake-provider controlled pilot - PASS.
- M25-3E optional live-provider pilot - OPTIONAL / NOT EXECUTED.

Only the in-process fake provider was validated. Do not claim live-provider validation: the historical M23 live-provider HOLD EXTERNAL remains open.

Before changing code, read [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md), [ARCHITECTURE.md](ARCHITECTURE.md), [CURRENT_STATE.md](CURRENT_STATE.md), [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md), and [KNOWN_ISSUES.md](KNOWN_ISSUES.md). Then verify `git status`, `git rev-parse HEAD`, `alembic heads`, and `alembic current`.

Non-negotiable boundaries: FORCE RLS, principal-derived tenant scope, effective-permission authorization, closed tool gateway, append-only audit, deterministic planner/verifier, no arbitrary SQL/shell/HTTP/tools, no raw DB-to-provider path, no persisted credentials/raw prompts/raw provider responses, and no L2+ autonomy without a future approved milestone.
