# M26 Investor Demo Runbook

## Runtime

- Render service: `education-os-investor-demo`
- One Uvicorn worker only; demo sessions are process-local.
- Staging demo mode with a synthetic-only dataset.
- Runtime database role: `education_app`.
- Never inject `OWNER_DATABASE_URL` into the long-running web service.

## Health

Both endpoints must return HTTP 200:

- `GET /health/live`
- `GET /health/ready`

The responses expose the configured `RELEASE_ID` for release verification.

## Deployment procedure

1. Verify the exact freeze commit and clean working tree.
2. Verify migration source head `0037_m26_mentor_briefing`.
3. Build and validate the frontend.
4. Run the backend release tests.
5. Push the exact freeze commit.
6. Configure `RELEASE_ID` to the exact freeze SHA.
7. Deploy that exact commit.
8. Verify `/health/live` reports the freeze SHA.
9. Verify `/health/ready` reports the freeze SHA.
10. Run the remote release smoke checks.
11. Create the annotated release tag only after all checks pass.

## Rollback

This M26 freeze introduces no migration beyond `0037_m26_mentor_briefing`.
If a deployment containing only validation artifacts and documentation fails,
redeploy the previous verified application commit:

`5abf42be5a0f5b5c7e68f47b4fee47ea3a1547c6`

Do not downgrade PostgreSQL for a code/runtime rollback. Do not re-enable
`education_owner` and do not inject `OWNER_DATABASE_URL` into runtime.
If database state is suspected, stop deployment and investigate before any
destructive migration action.

## Security handling

Never log or commit the demo access code, database URLs, passwords, cookies,
tokens, or student PII. Keep the database owner credential limited to
temporary administrative bootstrap and absent from the web service runtime.
