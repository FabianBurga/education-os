# ADR 0017 — Installable version uploads

Status: Accepted for v0.2.0.

Each milestone/patch is distributed as an incremental ZIP:
`Education_OS_<milestone>_v<semver>_Installable.zip`.

Every package contains `INSTALL.ps1`, `VERIFY.ps1`, a payload, manifest and SHA256 sums.
Installers validate, overlay, migrate and test, but do not rewrite Git history and do not push.
