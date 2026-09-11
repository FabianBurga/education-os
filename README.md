# Education OS — M0 Foundation Package v0.1

**Status:** Implementation package derived from the approved Architecture Baseline v0.1  
**Milestone:** `M0 — Foundation & Tenant Isolation`  
**Initial market:** Private Education Edition (Ecuador)  
**Core prepared for:** Public and Fiscomisional Editions

## Goal

M0 proves the technical foundations before building the definitive dashboard:

1. Multi-tenant organization / institution / campus model
2. Identity, memberships, roles and permissions
3. PostgreSQL Row Level Security (RLS)
4. Application DB role that is **not** table owner
5. Transactional event outbox baseline
6. Audit log baseline
7. Alembic migrations
8. Automated tenant-isolation tests
9. CI pipeline with PostgreSQL
10. Stable ADRs and domain contracts

## What is intentionally NOT in M0

- Full student/enrollment domain
- Academic schedules, attendance, grades
- Finance
- DECE / sensitive wellbeing records
- Final dashboards
- WhatsApp / SMS production integrations
- AI decisioning

Those belong to M1+ after the isolation/security gate passes.

## Local quick start

Requirements:

- Python 3.14+
- Docker / Docker Compose

```bash
cp .env.example .env
docker compose up -d postgres
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
pytest -q
fastapi dev app/main.py
```

API health:

`GET http://localhost:8000/health`

OpenAPI:

`http://localhost:8000/docs`

## Critical M0 gate

M0 is **not complete** until the integration tests prove:

- Tenant A cannot read Tenant B
- Tenant A cannot update Tenant B
- A request without tenant context cannot read institution-scoped rows
- The application role cannot bypass RLS
- Outbox writes can share a transaction with domain writes
- Audit events record actor, institution and entity context

See `docs/product/M0_ACCEPTANCE_GATE.md`.

## Foundation reference

Approved audited upstream technical reference:

- `fastapi/full-stack-fastapi-template`
- pinned audit commit: `cb740b656d7a0a6c5e12c7bf8e50343ec94ee9c7`
- license: MIT

This M0 package is an original Education OS scaffold. It does **not** copy code from GPL projects or unlicensed school ERP repositories. Those remain functional/architectural references only.

## Next milestone after M0

`M1 — Students / Families / Enrollment`
