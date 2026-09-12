# M17 Production Readiness Runbook

## Runtime topology

Education OS production is operated as separate trust zones:

- application runtime: restricted `education_app` database role
- migration job: short-lived owner credential
- PostgreSQL: private network only
- reverse proxy / load balancer: TLS termination
- application health probes: `/health/live` and `/health/ready`
- metrics collector: `/metrics` from the private operations network

Do not expose database owner credentials to the long-running application
process.

## Deployment sequence

1. Verify the exact source tag and commit.
2. Create a fresh database backup and SHA-256 manifest.
3. Run the production migration environment validator.
4. Execute Alembic with the migration credential.
5. Remove the migration credential from the deployment context.
6. Build the frontend production bundle.
7. Run the runtime environment validator.
8. Start the application with only the restricted runtime DB credential.
9. Require `/health/live` = 200.
10. Require `/health/ready` = 200.
11. Run smoke/API/security acceptance.
12. Observe metrics and error logs before increasing traffic.

## Rollback rule

Code rollback and database rollback are separate decisions.

If only application code changed and no migration occurred, return traffic to
the last frozen tag.

If a database migration occurred, do not blindly execute Alembic downgrade on
production data. Prefer restoring the pre-deployment backup into a clean
database and validating it before switching traffic.

## Runtime signals

Every operational incident should begin with:

- release ID
- request ID
- endpoint route template
- HTTP status
- elapsed time
- relevant database/worker health
- recent deployment or migration

Never paste access tokens or personal student data into incident logs.

## M17 baseline

- source base: `v1.0.0-rc6`
- M17 candidate: `v1.0.0-rc7`
- DB revision: `0016_m14`
- production v1.0.0: not yet released
