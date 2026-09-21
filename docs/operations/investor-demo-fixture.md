# Synthetic investor demo fixture

This operational fixture creates one isolated, synthetic institution for the
five staging demo aliases. It is intended for local or private staging use;
it must never target production or real institutional data.

## Safety

Provisioning requires `EDUCATION_OS_DEMO_MODE=true` and an owner-only
`OWNER_DATABASE_URL`. The API continues to run with the restricted
`DATABASE_URL`; the owner URL is used only by this setup tool. No credentials,
tokens, provider configuration, or schema objects are created. The default
state file is outside the repository at `%TEMP%\education-os-demo-fixture.json`.

The fixture creates `Education OS Demo` / `Unidad Educativa Demostración`, five
separate synthetic principals, a small class story centred on `Valentina
Demostración`, bounded source signals, and an official current M22 projection.
The Mentor runtime uses its normal governed path and deterministic fallback.

## Commands

Run from `backend` with the staging environment loaded:

```powershell
$env:EDUCATION_OS_DEMO_MODE = "true"
..\.venv\Scripts\python.exe tools\demo_fixture.py provision
..\.venv\Scripts\python.exe tools\demo_fixture.py verify
..\.venv\Scripts\python.exe tools\demo_fixture.py smoke
..\.venv\Scripts\python.exe tools\demo_fixture.py cleanup
```

`provision` is repeat-safe and refuses to overwrite an existing state file.
`verify` checks the tenant, principals, focal enrollment, signals, and current
snapshot. `smoke` exercises all five gateway aliases through the real API and
checks student and guardian isolation. `cleanup` removes only IDs recorded in
the external state file. A successful cleanup prints the removed organization
ID and leaves no fixture residue.

The gateway aliases are fixed server-side: `RECTOR`, `COORDINATION`,
`TEACHER`, `STUDENT`, and `GUARDIAN`. Browsers never provide principal IDs,
role IDs, tenant IDs, or permissions. Keep the gateway demo configuration
pointed at this synthetic tenant and fail closed if the assertion does not
hold.

## Story and privacy

The teacher sees the assigned class and attendance/academic context;
coordination sees bounded signals and follow-up context; the Rector sees only
aggregate M22/Mentor evidence; the student sees self-scoped information; and
the guardian sees the linked child only. No role receives a universal view.
RLS, FORCE RLS, permission checks, student self-scope, and guardian
relationship scope remain authoritative.

## Troubleshooting

Use `verify` before `smoke`. If provisioning refuses, confirm demo mode, the
owner connection, and that the state file is not already present. If cleanup
reports a dependency error, do not delete rows manually; inspect the exact
fixture state and rerun the tool after correcting the environment. Do not use
the tool with real data, a production owner URL, or a live provider.

This phase does not create a migration; the database remains at
`0037_m26_mentor_briefing`.
