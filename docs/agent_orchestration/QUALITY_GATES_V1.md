# Quality gates v1

## Gate order

1. `git diff --check`, memory validation and architecture check.
2. Ruff on changed Python; `py_compile` on changed Python.
3. Focused tests for changed modules.
4. Directed regression across affected authorities.
5. Security/integration validation with real FastAPI and application-role RLS
   behavior where authorization/tenant behavior changes.
6. Impact assessment; full suite when changes affect shared authority,
   migration, RLS, authentication, permissions, M18, M21, M27, cross-module
   services or otherwise uncertain shared behavior.

Localized frontend changes: focused frontend tests, typecheck and production
build. Documentation-only changes: diff check, JSON/reference validation; do
not run product regression solely for docs.

Cheap failure means stop and diagnose before expensive regression. Do not run
tests automatically from impact tooling. Never weaken tests/security contracts
to obtain PASS. Reports identify command, exit code, passed/failed/skipped
counts, warnings, tested and untested scope, and distinguish focused, directed,
security, integration and full validation. Apply repository engineering rules for provider fakes,
rollback-contained DB fixtures, no real model calls and residue checks.
