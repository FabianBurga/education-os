# M27-8 Controlled Operational Pilot

M27-8 is a rollback-contained synthetic pilot. It uses no student PII,
external providers, or `demo/investor-m26` data. The harness provisions one
deterministic tenant inside a single database transaction, exercises real M27,
M21 and M22 service boundaries, writes evidence, and rolls the tenant back.

## Reproduce

Prerequisites: local PostgreSQL, Alembic at head, Python dependencies in
`.venv`, and the base Python interpreter if the venv launcher is unavailable.

```powershell
$root = (Get-Location).Path
$base = 'C:\Users\USER\AppData\Local\Programs\Python\Python314\python.exe'
$env:PYTHONPATH = "$root\backend;$root\.venv\Lib\site-packages"
Set-Location "$root\backend"
& $base -m alembic current
& $base -m tools.m27_pilot_run
```

The expected current revision is `0042_m27_true_recurrence`; 0042 is the
forward-only correction discovered by this pilot for the frozen
`TRUE_RECURRENCE` vocabulary. Evidence is written to
`artifacts/m27_pilot_result.json`. The synthetic tenant and generated ledger
rows are rolled back after evidence collection.

## Actors and scenarios

The fixture contains SYSTEM_ADMIN, RECTOR, ACADEMIC_COORDINATOR, TEACHER A,
and TEACHER B with explicit memberships and effective permissions. It covers
queue discovery, assignment, review, decision, REQUEST_INFORMATION,
information completion and return to human review, on-time/overdue/waived
obligations, lost-vs-open, recurrence-vs-continuation, a separately created
M21 intervention outcome, small-cell suppression, provenance, replay, and
cross-boundary authorization failures. The artifact records P01-P20.

## Acceptance

Technical, operational, and value-evidence gates pass only when the artifact
reports zero tenant leakage, zero autonomous high-impact mutation, complete
critical scenarios, reproducible metric results, and no synthetic
administrative-time claim. `TIME_TO_PRIORITY_IDENTIFICATION` remains a human
observation instrument; `ADMINISTRATIVE_TIME_SAVED` is
`NOT_COMPUTABLE` with `BASELINE_REQUIRED`.
