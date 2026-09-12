# Education OS Frontend — M15 Unified Frontend Foundation

M15 formally instantiates the frontend architecture approved in the baseline:

- React
- TypeScript
- Vite
- Tailwind CSS
- local shadcn/ui-style primitives
- TanStack Router
- TanStack Query
- TanStack Table

## What M15 solves

M8–M14 proved the operational modules through server-served HTML. M15 does not
discard those consoles. Instead it introduces a single authenticated React shell
that reads the real backend context and presents only modules permitted by the
current user's effective permissions.

The foundation includes:

- unified application shell
- active institution context
- authenticated user identity
- role and permission context
- capability context
- permission-driven module navigation
- RLS-protected campus table
- responsive desktop/mobile layout
- transitional links to M8–M14 operational consoles
- one session token key for the new application

## Transitional compatibility

The new shell stores the token in:

`education_os_access_token`

During the transition, the same session token is mirrored into the old
sessionStorage keys used by the server-served consoles. This allows a user to
open a legacy operational console without retyping the same bearer token.

No token is written to localStorage.

## Development

The Vite development server proxies `/api` to FastAPI at `127.0.0.1:8000`.

Typical commands:

```text
npm install --package-lock=false
npm run typecheck
npm run test
npm run build
```

The production build is written to `frontend/dist`. FastAPI serves that build
under `/app`.

## Deliberate M15 boundary

M15 is the frontend foundation, not the complete migration of every console.

The backend remains the source of truth for:

- RLS
- permissions
- role scope
- capabilities
- student/guardian boundaries
- finance rules
- communications rules

React never recreates those rules as an alternative authorization system.
