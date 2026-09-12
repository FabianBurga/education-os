# Education OS — M15 Unified Frontend Foundation v0.15.0

## Frozen base

- Base tag: `m14-finance-billing-core-v0.14.0`
- Base commit: `212231eec1d68196c0070b8e04e47d3f4daed119`
- Database revision before and after M15: `0016_m14`

M15 intentionally introduces **no database migration**. It is an application
foundation milestone layered on the formally frozen M14 backend.

## Purpose

M8–M14 proved the major Education OS domains through server-served operational
HTML consoles. M15 converts the approved frontend architecture from a README
into a real application foundation.

The new user experience is one application shell:

`Sesión → Contexto institucional → Navegación por permisos → Espacio de trabajo`

## Frontend stack instantiated

M15 creates a real `frontend/` application using:

- React
- TypeScript
- Vite
- Tailwind CSS
- local shadcn/ui-style reusable primitives
- TanStack Router
- TanStack Query
- TanStack Table

The architecture baseline is therefore no longer only aspirational.

## Unified authenticated shell

The React application is served by FastAPI under:

`/app`

The shell obtains its identity and access context from:

`GET /api/v1/ui/bootstrap`

That endpoint returns:

- authenticated user identity
- organization/institution context
- effective roles
- effective permissions
- institution capabilities
- whether the person has active staff/student/guardian profiles

The frontend does **not** become an authorization authority. It only uses this
backend-issued context to decide which navigation entries to display. Every
operational API remains protected by its existing backend rules.

## Permission-driven navigation

M15 maps existing frozen console permissions to a shared navigation shell:

- `admin.console.access`
- `coord.console.access`
- `teacher.console.access`
- `student.console.access`
- `guardian.console.access`
- `communications.console.access`
- `finance.console.access`

A roleless authenticated actor can enter the shell but sees no module that the
backend has not granted.

Finance remains visible to an authorized finance actor even if
`finance.billing` is disabled, allowing the UI to explain the capability state
rather than pretending the module does not exist.

## RLS proof inside the new frontend

The home screen loads:

`GET /api/v1/campuses`

and renders the result with TanStack Table. This is deliberately retained as a
simple end-to-end proof that the React shell operates on the same RLS-isolated
backend context.

## Transitional preservation of M8–M14

M15 does not delete or rewrite the operational HTML consoles from M8–M14.

Each permitted workspace shows the new unified shell and provides a transition
button to the existing operational console. The unified bearer token is stored
in `sessionStorage` and mirrored into the old console session keys so the user
does not need to retype the same token during migration.

No token is written to `localStorage`.

## FastAPI SPA serving

FastAPI serves the Vite build under `/app`. Deep links such as:

`/app/workspace/administration`

fall back to `frontend/dist/index.html`, while real compiled assets are served
directly.

If the frontend has not been built, `/app` returns a clear 503 instead of
silently serving a broken page.

## CI

The repository CI now has two independent jobs:

### Backend

- Python install
- Ruff
- Alembic migration
- pytest

### Frontend

- Node 22
- npm install without package-lock generation
- TypeScript typecheck
- Vitest
- Vite production build

## Deliberate boundaries

M15 does not yet fully migrate every M8–M14 operational screen into React.

It does not change:

- RLS policies
- finance accounting rules
- communications rules
- student/guardian visibility
- automation behavior
- grading behavior
- attendance behavior
- existing role definitions or permission grants

It also does not introduce a username/password login screen. The acceptance
shell continues to use an existing signed bearer token, now through one unified
session entry point.

## Acceptance gate

The installer must verify:

- exact frozen M14 commit and tag
- PRIMARY still at `0016_m14`
- exact M15 overlay scope
- backend Ruff
- frontend Node toolchain (host Node or Docker Node fallback)
- frontend TypeScript typecheck
- frontend Vitest
- frontend production build
- full backend pytest
- M7 release gate
- M8/M9/M10 regression
- M11 native verifier at `0013_m11`
- M12 native verifier at `0014_m12`
- M13 native verifier at `0015_m13`
- M14 finance verifier at `0016_m14`
- M15 UI bootstrap HTTP verification
- FastAPI `/app` and SPA deep-link verification
- real Microsoft Edge rendering and navigation
- PRIMARY revision and domain row counts unchanged
- exact final source scope and diff hygiene

M15 is not formally frozen until local acceptance, commit/push, main CI,
annotated tag and tag CI are all green.
