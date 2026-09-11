# Education OS — M1

Release: v0.2.0  
Milestone: Students / Families / Enrollment  
Status: IMPLEMENTED, pending local + GitHub CI acceptance.

Included:
- student / guardian / staff profiles over canonical Person
- family households and members
- student ↔ guardian relationship
- minimal academic periods needed for enrollment
- campus-scoped enrollment lifecycle
- PostgreSQL FORCE RLS for all M1 tables
- REST API under `/api/v1`
- M1 domain-event names reserved
- synthetic-data-first; no real student/minor PII

Not included:
- grade/section/subject structures (M2)
- attendance/grades (M3)
- rector dashboard (M4)
- automation engine (M5)
- family portal (M6)
