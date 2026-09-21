# Investor demo staging on Render

This runbook packages the synthetic five-persona demo as one Render web
service backed by one Render PostgreSQL database. It is separate from the M26
release tag and does not run migrations or fixture provisioning when the web
container starts.

## Service shape

`render.yaml` describes one Docker web service on branch `demo/investor-m26`.
Auto deploy is disabled, the health check is `/health/ready`, and the process
uses exactly one Uvicorn worker because demo sessions are process-local. Render
terminates HTTPS; `PUBLIC_BASE_URL` must be the final `https://...onrender.com`
origin. The frontend is built into the image and served by FastAPI under `/app`.

The free web plan may cold-start after inactivity. That affects first-load
latency, not the security or one-instance design.

## Runtime environment

Set the variables in `.env.render.example` in the Render service. Use a unique
secret for `SECRET_KEY`, the restricted `education_app` connection for
`DATABASE_URL`, and a separate long random demo entrance code. The
`EDUCATION_OS_DEMO_PRINCIPALS` value is one JSON object with the five aliases.
Do not set `OWNER_DATABASE_URL` on the web service. Do not put any secret in
the repository, a URL, or frontend JavaScript.

The organization, institution, and principal values come from fixture
verification. They must all belong to the same synthetic institution.
`RELEASE_ID` should be the exact commit SHA deployed.

## Fresh database bootstrap

Create the Render PostgreSQL database manually in the same region as the web
service. Use a temporary/admin connection only from the operator workstation,
with TLS required by the provider. Do not add that connection to Render web
service environment variables.

From a checked-out deployment commit, set temporary local variables:

```powershell
$env:APP_ENV = "staging"
$env:DATABASE_URL = "<restricted-runtime-url>"
$env:OWNER_DATABASE_URL = "<temporary-owner-url>"
$env:EDUCATION_OS_DEMO_MODE = "true"
$env:EDUCATION_OS_DEMO_SYNTHETIC_ONLY = "true"
```

The provider/bootstrap procedure is:

1. Create `education_owner` and `education_app` with the repository's managed
   database bootstrap mechanism, preserving FORCE RLS and restricted runtime
   grants. Keep the owner connection temporary.
2. From `backend`, run
   `..\.venv\Scripts\python.exe -m alembic upgrade head` with only
   `OWNER_DATABASE_URL` available to the migration process.
3. Verify the revision is `0037_m26_mentor_briefing`, RLS and FORCE RLS remain
   enabled, and `education_app` is neither superuser nor BYPASSRLS.
4. Provision the synthetic institution with
   `EDUCATION_OS_DEMO_MODE=true` and the temporary owner connection:
   `..\.venv\Scripts\python.exe tools\demo_fixture.py provision`.
5. Verify it and capture the printed IDs for the demo environment values:
   `..\.venv\Scripts\python.exe tools\demo_fixture.py verify`.
6. Set the Render service's restricted `DATABASE_URL`, demo IDs/principals,
   HTTPS `PUBLIC_BASE_URL`, and secrets. Omit `OWNER_DATABASE_URL` entirely.
7. Restart the web service and verify `/health/live`, `/health/ready`, `/app/`,
   the entrance gate, and at least Rector and Teacher journeys.
8. Remove the temporary owner credential from the operator environment and
   restrict or disable public database access after bootstrap.

The fixture tool refuses to run unless demo mode is enabled and writes its ID
state outside the repository. It never creates credentials or schema.

## Fixture lifecycle

Run these commands from `backend` with the temporary owner connection only:

```powershell
..\.venv\Scripts\python.exe tools\demo_fixture.py provision
..\.venv\Scripts\python.exe tools\demo_fixture.py verify
..\.venv\Scripts\python.exe tools\demo_fixture.py cleanup
```

After cleanup, verify zero fixture residue before reprovisioning. Never point
these commands at a production tenant. The public service uses the captured
IDs only through server-side environment variables; the browser selects only
the fixed aliases `RECTOR`, `COORDINATION`, `TEACHER`, `STUDENT`, and
`GUARDIAN`.

## Release and rollback

Keep Render auto deploy disabled. In the Render dashboard, deploy the exact
commit recorded in `RELEASE_ID`. For rollback, redeploy the previous approved
commit and keep the same database only when its schema and fixture contract
are compatible. Never downgrade a valid migration to roll back an application
image. No release tag is created by this packaging phase.

## Local checks

Build and run the same image locally with a temporary staging `.env` and a
local PostgreSQL database:

```powershell
docker build -t education-os-investor-demo:<commit-sha> .
docker run --rm --env-file .env.render.local -p 8000:10000 education-os-investor-demo:<commit-sha>
```

Check `/health/live`, `/health/ready`, `/app/`, and the demo entrance. Keep
`.env.render.local` outside Git and delete it after the check.
