# ADR 0016 — M1 identity/profile/family/enrollment model

Status: Accepted for v0.2.0.

`persons` remains the canonical human identity. Student, guardian and staff are institution-scoped
profiles over Person, so the platform follows **one person → one record → multiple processes**.

Enrollment references StudentProfile + AcademicPeriod + Campus. Grade and section assignment are
deliberately deferred to M2 Academic Core.

Every M1 operational table stores `organization_id` and `institution_id`. This is intentional
denormalization for explicit, auditable PostgreSQL RLS policies.
