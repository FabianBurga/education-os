# Efficiency policy v1

- Reuse fresh `docs/memory/` and anchor-to-HEAD delta; do not repeat M0–M28
  discovery unless memory is missing/stale/contradicted or task needs detail.
- Delegate only independent bounded work; keep A0 responsible for synthesis.
- One file, one writer per wave. Prefer read-only discovery and parallelize
  only non-overlapping work.
- Use deterministic local helpers, not LLMs or repository-wide scans, for
  preflight, context selection, test recommendations and structural checks.
- Run focused validation first; broader suites follow impact, not habit. Never
  auto-run tests from `select_tests.py`.
- Report concise evidence and scope; avoid raw logs unless needed to diagnose.
- Keep indexes optional until repeated measured discovery makes generation
  valuable. Future route/permission/event/migration/domain/schema indexes need
  their own justified tooling change.
- Future initial Skills set is capped at five: education-security-review,
  education-migration, education-test-gate, education-release-gate and
  education-memory-refresh. Create actual Skills only if local support and a
  compatible repository pattern are verified; do not invent Codex config.
- Persistent Goals are supported by this environment. A0 may use one Goal per
  substantial slice when useful; repository memory/Task Contract remains the
  source of truth. Do not emulate Goals if a future runtime lacks the feature.
