import os

import psycopg

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)

M6_TABLES = (
    "guardian_student_portal_access",
    "family_notices",
    "family_notice_receipts",
)


def test_m6_tables_force_rls() -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = ANY(%s)
            ORDER BY c.relname
            """,
            (list(M6_TABLES),),
        )
        rows = cur.fetchall()

    assert len(rows) == len(M6_TABLES)
    assert all(enabled and forced for _, enabled, forced in rows)


def test_m6_runtime_role_has_dml_privileges() -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        for table in M6_TABLES:
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                cur.execute(
                    "SELECT has_table_privilege('education_app', %s, %s)",
                    (table, privilege),
                )
                assert cur.fetchone()[0], f"{privilege} missing on {table}"


def test_m6_has_command_specific_rls_policies() -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT tablename, cmd
            FROM pg_policies
            WHERE schemaname = 'public' AND tablename = ANY(%s)
            """,
            (list(M6_TABLES),),
        )
        rows = cur.fetchall()

    commands = {}
    for table, cmd in rows:
        commands.setdefault(table, set()).add(cmd)

    for table in M6_TABLES:
        assert {"SELECT", "INSERT", "UPDATE", "DELETE"}.issubset(commands[table])
