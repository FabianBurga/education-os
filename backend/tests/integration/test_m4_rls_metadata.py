import os

import psycopg

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)


def test_intelligence_signals_force_rls() -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = 'intelligence_signals'
            """
        )
        row = cur.fetchone()

    assert row == (True, True)


def test_intelligence_signals_runtime_dml_privileges() -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            cur.execute(
                "SELECT has_table_privilege('education_app', 'intelligence_signals', %s)",
                (privilege,),
            )
            assert cur.fetchone()[0], f"{privilege} missing"


def test_intelligence_signals_has_runtime_tenant_policy() -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT roles
            FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = 'intelligence_signals'
              AND policyname = 'intelligence_signals_tenant_isolation'
            """
        )
        row = cur.fetchone()

    assert row is not None
    assert "education_app" in row[0]
