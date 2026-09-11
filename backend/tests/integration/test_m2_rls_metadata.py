import os

import psycopg

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)

M2_TABLES = (
    "academic_levels",
    "grade_levels",
    "subjects",
    "sections",
    "curriculum_plans",
    "curriculum_subjects",
    "course_offerings",
    "teaching_assignments",
    "student_section_assignments",
    "schedule_slots",
)


def test_m2_tables_force_rls() -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = ANY(%s)
            ORDER BY c.relname
            """,
            (list(M2_TABLES),),
        )
        rows = cur.fetchall()

    assert len(rows) == len(M2_TABLES)
    assert all(enabled and forced for _, enabled, forced in rows)


def test_m2_runtime_role_has_dml_privileges() -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        for table in M2_TABLES:
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                cur.execute(
                    "SELECT has_table_privilege('education_app', %s, %s)",
                    (table, privilege),
                )
                assert cur.fetchone()[0], f"{privilege} missing on {table}"


def test_m2_tables_have_runtime_tenant_policy() -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT tablename, roles
            FROM pg_policies
            WHERE schemaname = 'public' AND tablename = ANY(%s)
            """,
            (list(M2_TABLES),),
        )
        rows = cur.fetchall()

    covered = {table for table, roles in rows if "education_app" in roles}
    assert covered == set(M2_TABLES)
