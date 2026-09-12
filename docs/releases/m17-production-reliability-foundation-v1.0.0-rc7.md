# Education OS — M17 Production Reliability Foundation / v1.0.0-rc7

## Frozen base

M17 starts from the formally frozen full-system release candidate:

- tag: `v1.0.0-rc6`
- commit: `e418feb1244862107d7a9d6c9f805dbef37fe792`
- database head: `0016_m14`

M17 introduces **no database migration** and no educational-domain behavior
change.

The intended next release-candidate tag, only after all gates pass, is:

`v1.0.0-rc7`

Production `v1.0.0` remains unreleased.

## Purpose

M16 proved that the product works end to end. M17 makes that product easier to
operate, diagnose and recover safely.

M17 establishes five permanent foundations:

1. Runtime liveness and readiness probes.
2. Privacy-minimized structured request logging and correlation IDs.
3. Low-cardinality runtime metrics.
4. Production configuration safety rules with runtime/migration credential
   separation.
5. A reusable acceptance harness for M18 and later milestones.

## Compatibility

The frozen `/health` contract remains unchanged and still returns milestone
`M15` because M15 and M16 acceptance tooling depends on it.

M17 adds:

- `GET /health/live`
- `GET /health/ready`
- `GET /metrics`

The new M17 routes are additive.

## Production credential separation

`OWNER_DATABASE_URL` becomes optional for the runtime settings model.

The runtime application must use only the restricted application database role.
Owner credentials are required only when Alembic is executed.

The production runtime guard rejects:

- default or short `SECRET_KEY`
- non-PostgreSQL runtime database URLs
- owner credentials in `DATABASE_URL`
- known development credentials
- non-HTTPS public base URLs
- production readiness with the frontend check disabled
- owner database credentials injected into the runtime process

## Observability privacy boundary

Request logs deliberately do not contain:

- bearer tokens
- request bodies
- query strings
- student identifiers
- user identifiers
- organization identifiers
- institution identifiers

The middleware records only operational metadata such as request ID, HTTP
method, route template, status, duration, release and environment.

Metrics avoid path labels and tenant/user labels to keep cardinality bounded and
reduce disclosure risk.

## Reliability acceptance

M17 acceptance must prove:

- full M0–M16 regression chain remains green
- DB remains `0016_m14`
- legacy `/health` compatibility remains intact
- liveness works
- readiness proves runtime PostgreSQL connectivity
- every HTTP response carries an `X-Request-ID`
- valid request IDs are preserved and invalid values are replaced
- metrics expose 2xx/4xx request classes without high-cardinality path labels
- structured JSON request logs are produced
- unmatched request paths are logged as `UNMATCHED`, not raw identifiers
- unified frontend still loads in real Microsoft Edge
- backup/restore recovery still succeeds
- PRIMARY is unchanged

## Freeze rule

M17 is only locally accepted when all local gates pass.

It becomes formally frozen only after:

1. local acceptance
2. commit
3. push to `main`
4. main CI success
5. annotated tag `v1.0.0-rc7`
6. tag CI success
