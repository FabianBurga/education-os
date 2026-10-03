# Current context

Current development-harness task: M29-AO — Agent Orchestration + Project
Memory + Efficiency Foundation. This adds repository tooling and process
contracts only; product behavior and schema remain untouched.

M29 — Teacher & Family Continuity. M29-0 contract/discovery is PASS on
`m29-teacher-family-continuity`, based at M28 release
`m28-operational-adoption-core-v0.28.0` /
`c21e7c1287a8bc7abd8f355aa619e67c0beee0c4`. M28 Alembic head:
`0046_m28_attendance_perms`. The M29-0 accepted context anchor is
`ba371604a588a9093987e8b636ba9b4e570d9b0c`; it intentionally identifies the
project baseline this memory describes, not the commit containing later
memory edits. If HEAD differs, inspect only `git log ANCHOR..HEAD --oneline`
and `git diff --name-only ANCHOR..HEAD` before deciding on broader discovery.

M29-0 confirmed existing teacher/student/guardian/family and M13 communication
capabilities. Guardian/student access uses explicit grants; family receives
curated attendance/results, notices and acknowledgement. General family
response, communication-to-M21 follow-up / M27 obligation linkage, a unified
teacher-family continuity view and family-safe M21 timeline projection were
not verified. M13 release scope is in-app; SMS/email/WhatsApp/push are not
included. Offline clients must not dispatch family messages. Evidence and
privacy constraints: `docs/m29/M29_CAPABILITY_INVENTORY.md`,
`M29_CONTINUITY_MAP.md`, `M29_PRIVACY_BOUNDARY.md`, and `M29_EVENT_CONTINUITY.md`.

Unresolved product/privacy decisions: family response semantics,
contact/consent preferences, retention, guardian disputes and response
moderation. Do not decide these silently. Escalate implementation dependency
to A0 and obtain human approval where needed.

Next: human review of M29-0 contract, then one bounded M29-1 Task Contract.
Do not reconstruct M0–M28 when the anchor is fresh and memory covers the task;
repository evidence wins when it contradicts memory.

Development harness: native delegated subagents are available to the root
agent; A0 owns coordination, with at most three active delegates and no nested
agents. Persistent Goals are available in this environment but are optional;
repository memory and the Task Contract remain authoritative.
