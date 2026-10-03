# Task Contract template v1

Copy and fill one contract per delegate/task. Keep scope bounded.

```text
TASK_ID:
OWNER: A1 | A2 | A3 | A4
OBJECTIVE:
DEPENDENCIES:
MEMORY_REFS:
READ_SCOPE:
WRITE_SCOPE:
ROOT_LOCKED_FILES:
MUST_REUSE:
MUST_NOT_CREATE:
SECURITY_REQUIREMENTS:
TEST_EXPECTATIONS:
EXPECTED_OUTPUT:
STOP_CONDITIONS:
DO_NOT_REDISCOVER:
```

`WRITE_SCOPE` must list exact files/directories and must not overlap another
active task. Use read-only scope by default. Any unlisted needed file triggers
STOP_AND_REPORT_TO_A0. Migrations, root-locked files and cross-domain contracts
need explicit A0 ownership/authorization.

Expected return format:

```text
AGENT:
TASK_ID:
STATUS: PASS | HOLD | BLOCKED
SUMMARY:
FILES_READ:
FILES_MODIFIED:
TESTS_RUN:
EVIDENCE:
SECURITY_NOTES:
RISKS:
BLOCKERS:
REQUESTED_ROOT_LOCKS:
MEMORY_DELTA:
RECOMMENDED_NEXT_ACTION:
```

Keep reports concise and logs summarized unless raw output is requested.
