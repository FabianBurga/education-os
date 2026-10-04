# Memory changelog

- M29-AO: established compact machine/human project memory from verified
  M29-0 state; anchor semantics point to accepted M29-0 commit
  `ba371604a588a9093987e8b636ba9b4e570d9b0c`. M28 release facts and M29-0
  capability/privacy findings are linked to canonical milestone evidence.
- M29-1 / SEC-TC1: accepted the database-issued one-time capability boundary
  as the first SEC-TC1 consumer; closed the guardian acknowledgement source
  boundary and M21/M27 evidence bridge on migration
  `0047_sec_tc1_m29_ack_bridge`. Local backend/security validation passed;
  details and bounded debt are in `CURRENT_CONTEXT.md` and
  `VALIDATION_BASELINE.md`.
- M29-2: accepted the bounded, read-only Teacher Continuity Workspace on
  migration `0048_m29_batch_ack_reads`. Added domain-specific SEC-TC1 batch
  purposes with target-set digest binding; target authorization precedes
  evidence; no new permission, event, projection or M29 persistence. Local
  backend/frontend, migration and ACL/RLS validation passed. See the M29-2
  closeout and validation baseline.
- Memory updates are A0-owned. Delegated agents return `MEMORY_DELTA`; A0
  validates it against repository evidence before publishing.
- Advance `memory_anchor_commit` only when a project-context baseline is
  accepted. Do not make a commit self-referential or create follow-up commits
  solely to point memory at its containing commit.
