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
- M29-2V remediation: corrected the existing 0048 batch-validator runtime
  ambiguity and accepted issuer-backed permanent coverage (24 focused passed;
  full backend 810 passed, 2 optional M21 E2E skips). No architecture,
  permission, event, or persistence change was introduced.
- M29-3: accepted the curated family continuity DESIGN_A composition in the
  existing Guardian Console surface. The bounded notice card preserves
  actor-specific M13 acknowledgement semantics and keeps M21, M27, and M22
  invisible to family users. Frontend 84 passed and issuer-backed backend 810
  passed with the two optional M21 E2E skips; A3/A4 passed.
- M29-4: accepted the synthetic controlled institutional pilot across M13,
  M21, M27, M29-1, M29-2, M29-3, and SEC-TC1. Full issuer-backed backend was
  810 passed with two optional M21 E2E skips; frontend was 84 passed; A3/A4
  passed; release blockers were none. No product capability or schema change
  was introduced.
- Memory updates are A0-owned. Delegated agents return `MEMORY_DELTA`; A0
  validates it against repository evidence before publishing.
- Advance `memory_anchor_commit` only when a project-context baseline is
  accepted. Do not make a commit self-referential or create follow-up commits
  solely to point memory at its containing commit.
