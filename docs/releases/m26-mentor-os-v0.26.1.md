# M26 Mentor OS — v0.26.1 Freeze Candidate

- **Milestone:** M26 — Mentor OS
- **Target release:** `m26-mentor-os-v0.26.1`
- **Branch:** `demo/investor-m26`
- **Previous deployed baseline:** `5abf42be5a0f5b5c7e68f47b4fee47ea3a1547c6`
- **Database head:** `0037_m26_mentor_briefing`
- **Public demo:** https://education-os-investor-demo.onrender.com/app/

## Gate evidence

- M26-C1 real authenticated E2E: PASS
- M26-C2 remote RBAC/RLS isolation: PASS
- M26-C3 Rector Mentor journey: PASS
- M26-C4 security closeout: PASS
- M26-C5 F1 pre-freeze audit: PASS

The deployed runtime uses the restricted PostgreSQL role `education_app`.
The `education_owner` role is `NOLOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`,
`NOCREATEDB`, `NOCREATEROLE`, and `NOINHERIT`. The demo startup invariant
rejects `OWNER_DATABASE_URL` and rejects a runtime `DATABASE_URL` containing
`education_owner`.

M26 Mentor remains an L0, aggregate institutional-intelligence experience
using the governed deterministic-fallback or fake-provider path. Human review
remains mandatory and no autonomous domain action is introduced.

C1–C4 provide deployed-runtime evidence for the final security model. Some
legacy integration tests use `OWNER_DATABASE_URL` for transactional fixture
bootstrap; those tests are incompatible with the final `education_owner`
`NOLOGIN` state and must never justify re-enabling that role.

This is a freeze candidate only. It is not a production `v1.0.0` declaration.
