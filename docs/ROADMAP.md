# Roadmap

## Current baseline

M28 — Operational Adoption Core v0.28.0 is CLOSED / PUBLISHED / CANONICAL at
`c21e7c1287a8bc7abd8f355aa619e67c0beee0c4`, tag
`m28-operational-adoption-core-v0.28.0`. M29 — Teacher & Family Continuity is
CURRENT; M29-0 and M29-AO are PASS, and M29-1 Family Acknowledgement Evidence
Bridge / SEC-TC1 Phase 1 is CLOSED / PASS locally at Alembic head
`0047_sec_tc1_m29_ack_bridge`. See [M29 scope](m29/M29_SCOPE.md),
[M29-1 closeout](m29/M29_1_ACKNOWLEDGEMENT_EVIDENCE_BRIDGE.md), and
`docs/agent_orchestration/`.

This is direction, not implementation status.

- M25 - Agentic Control Plane. CLOSED.
- M26 - Human Experience Layer / Mentor OS. CLOSED / PASS.
- M27 - Institutional Decision & Accountability OS. CLOSED / PASS. M27-1
  through M27-8 are complete; technical and synthetic operational validation
  passed, with value evidence limited by required human observation.
- M28 - Operational Adoption Core v0.28.0. CLOSED / PUBLISHED / CANONICAL;
  immutable release tag and commit are recorded above.
- M29 - Teacher & Family Continuity. CURRENT; M29-0 contract freeze PASS and
  M29-AO harness PASS; M29-1 evidence bridge and SEC-TC1 first consumer
  CLOSED / PASS. The next slice requires a separate contract freeze.
- M30+ - Future roadmap topics require separate discovery and approval.

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
