import os

import psycopg

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)

CRITICAL = {
    "family_notices",
    "pilot_readiness_runs",
    "automation_cases",
    "guardian_profiles",
    "automation_tasks",
    "attendance_records",
    "automation_rules",
    "student_profiles",
    "guardian_student_portal_access",
    "enrollments",
    "sections",
    "staff_profiles",
    "intelligence_signals",
    "family_notice_receipts",
    "grade_entries",
}


def test_critical_tables_keep_force_rls() -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = ANY(%s)
            """,
            (list(CRITICAL),),
        )
        rows = cur.fetchall()

    assert {row[0] for row in rows} == CRITICAL
    assert all(enabled and forced for _, enabled, forced in rows)
