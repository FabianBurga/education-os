# Education OS - AI Continuity Context

Project: Education OS, an Institutional Intelligence & Action Platform.

Authoritative committed source: `bd0fbaa719eae4884d9a6c3ab8600939e88bb433` (`feat(m25): add governed provider-backed explainer`).

Authoritative M25 release tag: `m25-governed-provider-explainer-v0.25.3`.

Current working branch: `m26-mentor-os`.

Current database revision: `0037_m26_mentor_briefing`.

Active milestone: M26 - Human Experience Layer / Mentor OS.

M26-1 is CLOSED and M26-2 governed Mentor runtime is CLOSED / PASS. M26-2
delivers the L0 `mentor_institution_briefing` v1 runtime with typed
`OVERVIEW`/`PRIORITIES`/`FOLLOW_UPS`, permission-driven `agents.use` plus
`intelligence.read`, the typed M22 snapshot boundary,
`m25.evidence.v1`, deterministic fallback, optional fake-only provider path,
deterministic verification, append-only audit, M18 lifecycle events, and
governed replay identity. Replay includes tenant/principal, agent/version,
focus, snapshot identity, M22 provenance hash, and Mentor prompt-contract hash;
a changed snapshot creates a new logical execution. No domain mutation or live
provider dependency exists. M26-3 Rector API/UI presentation is next; M26-4
controlled pilot and overall M26 closure remain pending. M26 overall is not
yet closed.

M26-2 validation: 75 targeted tests passed, including 61 M26 integration
tests; directed M25 57, M22 56, M21 282, M23 66, and M24 13 passed; full
backend 711 passed, 0 failed, 1 skipped, 116 warnings in 42.50 seconds. The
skipped test was the opt-in M21 E2E because `M21_E2E_DATABASE_URL` was unset.
Only in-process fake provider validation was used; live and external network
model calls were zero. Historical M23 live-provider HOLD EXTERNAL remains open.

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
