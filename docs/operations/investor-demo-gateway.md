# Investor demo gateway — Phase 2

This is an isolated staging feature based on `m26-mentor-os-v0.26.0`
(`d0ecdcf74adceedfd297dca8b8774595a87e1437`). It does not start M27,
change the M26 release, create a demonstration dataset, or deploy anything.
The database remains at `0037_m26_mentor_briefing`.

## Activation and deployment boundary

Default: `EDUCATION_OS_DEMO_MODE=false`. Demo endpoints return 404 and the
ordinary bearer-token application remains available. No frontend build flag
or client-supplied identity can activate demo mode.

All of these server-side settings are required to enable the gateway:

| Setting | Requirement |
| --- | --- |
| `EDUCATION_OS_DEMO_MODE` | `true` |
| `APP_ENV` | exactly `staging`; production and development are rejected |
| `EDUCATION_OS_DEMO_SYNTHETIC_ONLY` | `true`, operator attestation that the dedicated database contains synthetic demo data only |
| `PUBLIC_BASE_URL` | public HTTPS origin, without an application path |
| `DATABASE_URL` | restricted PostgreSQL runtime connection; never an owner connection |
| `OWNER_DATABASE_URL` | absent, including in the runtime `.env` |
| `SECRET_KEY` | independently generated secret of at least 32 characters |
| `EDUCATION_OS_DEMO_ACCESS_CODE` | independently generated secret of at least 24 characters, distinct from `SECRET_KEY` |
| `EDUCATION_OS_DEMO_ORGANIZATION_ID` | existing synthetic organization UUID |
| `EDUCATION_OS_DEMO_INSTITUTION_ID` | existing synthetic institution UUID in that organization |
| `EDUCATION_OS_DEMO_PRINCIPALS` | server-side JSON object with exactly five distinct existing principal UUID values |

The JSON keys are `RECTOR`, `COORDINATION`, `TEACHER`, `STUDENT`, `GUARDIAN`.
The browser submits only one of these aliases. It cannot supply UUIDs, roles,
tenant scope or permissions. Keep actual configuration in the deployment
secret store, never `VITE_*` variables, Git, URLs or frontend bundles.

The application cannot infer whether arbitrary database contents represent real
people. The synthetic-only assertion is an explicit deployment prerequisite,
not an automated data-classification claim. Phase 3 must provision and verify
the isolated synthetic database and actor associations before remote exposure.

Incomplete activation configuration fails startup. Each authenticated request
also rejects a superuser/BYPASSRLS database role and revalidates the principal,
organization, institution, active account, active membership, exact persona role
and effective permission ceiling through the existing tenant/RLS context.

## Browser flow and sessions

Open `/app/`, enter the separate demo access code, then choose a profile.
The server issues an opaque, random `__Host-education_demo` cookie. It is
HttpOnly, Secure, SameSite=Strict, host-only and Path=/, with no persistent
browser expiry. The server expires each session after 900 seconds. No JWT or
cookie value is returned in JSON, rendered in the UI or stored in JavaScript.
HTTPS is required; do not disable Secure for an HTTP-only local demonstration.

The outer entrance is rate-limited globally to ten attempts per minute per
process. State-changing demo and authenticated API requests require the exact
configured Origin, and cross-site requests are rejected. Validation errors do
not echo submitted access codes. This small gateway is not a general user
authentication system and does not accept production credentials.

Only hashed cookie identifiers are held in process memory. **Run exactly one
worker and one replica.** Restart/redeployment revokes every session. This
implementation deliberately requires neither a session table nor Redis.
Multiple workers would reject each other's sessions; horizontal scaling is not
supported by this phase. A deployment edge can add further rate limiting.

Selecting another profile atomically revokes the old cookie. `POST /api/demo/exit`
revokes the persona session and returns to an entrance-only session;
`POST /api/demo/logout` revokes and clears it entirely. Frontend switching clears
bearer/bootstrap storage, React Query state and the teacher offline database,
then reloads the real unified shell. BroadcastChannel synchronizes open tabs;
restored browser-history pages reload. API responses are no-store, and the
existing service worker excludes authenticated API caching. Sessions and
bootstrap authorization are refreshed every 15 seconds while the shell is open.

The ordinary bearer path is preserved when demo mode is off. On the dedicated
demo host, bearer headers cannot bypass the demo entrance. Legacy persona
consoles use the same cookie and live authorization, hide token entry, and
return to the unified shell for profile switching. Their ordinary internal
token flow remains unchanged outside demo mode.

## Authorization and persona prerequisites

No permissions are granted by selecting a profile. Provision separate accounts,
persons, active memberships and institution-scoped roles in Phase 3. The exact
role keys are `RECTOR`, `ACADEMIC_COORDINATOR`, `TEACHER`, `STUDENT`, `GUARDIAN`.
The actor's existing permissions must be a nonempty subset of its explicit
ceiling in `app/core/demo.py`. Accounts with any extra permissions are denied;
do not reuse broad administrator or production roles.

- Rector: governed Mentor, institutional intelligence and coordination reads.
- Coordination: the same reads plus existing bounded intervention workflows.
- Teacher: existing assigned-class, attendance, grades and task workflows.
- Student: existing student profile/self-scoped console and reads.
- Guardian: existing relationship-scoped child reads and notice acknowledgement.

Create the corresponding staff/student/guardian profiles and authorized
relationships only in the later fixture phase. Existing endpoint guards and
RLS still enforce those scopes. The gateway does not fabricate module visibility
or records. Admin, control-plane mutation, finance, communications management,
integration management and live Copilot surfaces are excluded. Agent execution
is limited to the existing Mentor endpoint. Do not seed eligible live-provider
routes or provider secrets in the synthetic deployment; retain Mentor fallback.

## Validation and limits

Gateway integration tests use rollback-only authorization probes. Setup uses
the owner connection; before HTTP requests `SET LOCAL ROLE education_app`
enforces the restricted runtime role and FORCE RLS. Owner use is confined to
fixture setup/changes/cleanup. The outer transaction is never committed, and
residue is checked afterward. These probes are not the Phase 3 multirole story.

Tests cover five actual principals, exact effective permissions, student self
scope, guardian relationship scope, wrong tenant/role, excess permissions,
membership revocation, cookie expiry, CSRF, switching, logout, rate limiting,
legacy consoles and ordinary bearer authentication. No live provider is called.
Frontend tests cover entrance rendering and request/cache contracts; no claim
of a completed remote browser pilot or production penetration test is made.

Phase 2 validation: 38 gateway tests (23 unit, 15 integration); 66 combined
focused gateway/auth/role/tenant tests; frontend 63 passed; typecheck and build
passed. Full backend: 756 passed, 0 failed, 1 skipped, 128 warnings, 58.66 seconds.
The skip is the existing M21 opt-in E2E with `M21_E2E_DATABASE_URL` unset.
Warnings were not suppressed or repaired in this slice. Vite retains its bundle
size advisory. Ruff and compilation of touched Python files passed. Read-only
database verification confirmed 99 RLS tables, all 99 FORCE RLS, the restricted
application role, revision 0037, and zero rollback-fixture organization residue.

## Packaging deferred to deployment phase

No application Dockerfile is introduced here. Existing integrated hosting serves
`backend/frontend/dist` at `/app`; copy the result of `frontend/npm ci` and
`npm run build` into that directory in the future reproducible image.
From `backend`, the intended runtime command is:

```sh
python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 1
```

Use a dedicated HTTPS origin for frontend and API; no cross-origin cookie or
CORS exception is needed. Set `FRONTEND_REQUIRED_FOR_READINESS=true` and probe
`/health/ready`, which checks database connectivity and frontend availability.
Run Alembic separately as a short-lived deployment job with migration credentials;
never run owner migrations in the long-lived application process. Remote release
still requires the Phase 3 fixture, image/startup packaging, TLS, restricted
managed PostgreSQL and end-to-end smoke tests.
