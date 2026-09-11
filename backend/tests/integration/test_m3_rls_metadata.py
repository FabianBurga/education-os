import os

import psycopg

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)

M3_TABLES = (
    "attendance_codes",
    "class_sessions",
    "attendance_records",
    "grading_periods",
    "grading_scales",
    "grading_scale_bands",
    "assessment_categories",
    "assessments",
    "grade_entries",
)


def test_m3_tables_force_rls() -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = ANY(%s)
            ORDER BY c.relname
            """,
            (list(M3_TABLES),),
        )
        rows = cur.fetchall()

    assert len(rows) == len(M3_TABLES)
    assert all(enabled and forced for _, enabled, forced in rows)


def test_m3_runtime_role_has_dml_privileges() -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        for table in M3_TABLES:
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                cur.execute(
                    "SELECT has_table_privilege('education_app', %s, %s)",
                    (table, privilege),
                )
                assert cur.fetchone()[0], f"{privilege} missing on {table}"


def test_m3_tables_have_runtime_tenant_policies() -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT tablename, roles
            FROM pg_policies
            WHERE schemaname = 'public' AND tablename = ANY(%s)
            """,
            (list(M3_TABLES),),
        )
        rows = cur.fetchall()

    covered = {table for table, roles in rows if "education_app" in roles}
    assert covered == set(M3_TABLES)
