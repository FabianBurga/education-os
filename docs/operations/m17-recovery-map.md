# Education OS Recovery Map

## Known-good checkpoints

A checkpoint is valid only when source tag, database compatibility and CI
evidence agree.

Current recovery baseline before M17:

- code tag: `v1.0.0-rc6`
- commit: `e418feb1244862107d7a9d6c9f805dbef37fe792`
- database revision: `0016_m14`
- main CI: passed
- tag CI: passed
- M16 backup/restore drill: passed

## Incident decision tree

Application unavailable:
`liveness -> process/container -> configuration -> dependency/network`

Application alive but not ready:
`readiness -> PostgreSQL -> frontend build requirement -> deployment config`

Authorization problem:
`request ID -> role/permission -> membership -> tenant context -> RLS`

Regression after deployment:
`current tag -> previous frozen tag -> git compare -> affected verifier`

Suspected data issue:
`stop destructive actions -> preserve evidence -> fresh backup -> clone ->
validate -> repair/restore`

## Recovery evidence

Every recovery must preserve:

- incident timestamp
- running release ID
- database revision
- backup SHA-256
- action taken
- validation result
- final release ID

The recovery process is considered complete only after readiness, relevant
domain verifier and full-system smoke checks pass.
