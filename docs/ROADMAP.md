# Roadmap

This is direction, not implementation status.

- M25 - Agentic Control Plane. CLOSED.
- M26 - Human Experience Layer / Mentor OS. CLOSED / PASS.
- M27 - Institutional Intelligence Agents.
- M28 - Autonomous Data Operations.
- M29 - Preventive Intelligence / Sentinel.
- M30 - Family Experience.
- M31 - Autonomous Operations.
- M32 - Self-Healing Platform.

Future milestones do not authorize autonomous mutation, generic tool access, browser automation, SQL, shell, credentials, or provider-driven decisions. Each requires a separately frozen contract and closure evidence.

## M25 closure classification

- M25-1: CLOSED.
- M25-2: CLOSED.
- M25-3A Evidence Pack Foundation: PASS.
- M25-3B Provider Registry, Router, and Budget: PASS.
- M25-3C First provider-backed L0 advisor: PASS / CLOSED.
- M25-3D Controlled fake-provider pilot: PASS.
- M25-3E Optional live-provider pilot: OPTIONAL / NOT EXECUTED; external and not required for M25 closure.

## M26 delivery slices

- M26-1 Mentor institution-briefing contract and persisted configuration: CLOSED.
- M26-2 Governed runtime, Evidence Pack, deterministic fallback, and verifier: CLOSED / PASS.
- M26-3 Rector API/UI presentation: CLOSED / PASS.
- M26-4 Controlled synthetic pilot, manual visual gate, and milestone closure: CLOSED / PASS.

M26-2 closure evidence: 75 targeted tests passed, including 61 M26 integration
tests; directed M25 57, M22 56, M21 282, M23 66, and M24 13 passed; full
backend 711 passed, 0 failed, 1 skipped, 116 warnings in 42.50 seconds. The
skipped test was the opt-in M21 E2E because `M21_E2E_DATABASE_URL` was unset.
RLS and FORCE RLS remained intact, application-role restrictions and tenant
isolation passed, test residue was zero, and live/external provider calls were
zero. M26 overall is CLOSED / PASS. Final regression passed 718 backend tests
with 0 failures, 1 configured opt-in M21 E2E skip, and 126 warnings; frontend
tests, typecheck, production build, Ruff, `py_compile`, and `git diff --check`
passed.
