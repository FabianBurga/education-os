import os

import psycopg

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)


def test_runtime_role_remains_hardened() -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT rolsuper, rolbypassrls, rolinherit
            FROM pg_roles
            WHERE rolname = 'education_app'
            """
        )
        row = cur.fetchone()

    assert row == (False, False, False)


def test_pilot_readiness_runs_force_rls_and_runtime_policy() -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relrowsecurity, c.relforcerowsecurity, r.rolname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_roles r ON r.oid = c.relowner
            WHERE n.nspname = 'public'
              AND c.relname = 'pilot_readiness_runs'
            """
        )
        table = cur.fetchone()

        cur.execute(
            """
            SELECT roles
            FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = 'pilot_readiness_runs'
              AND policyname = 'pilot_readiness_runs_tenant_isolation'
            """
        )
        policy = cur.fetchone()

    assert table is not None
    assert table[0] is True
    assert table[1] is True
    assert table[2] != "education_app"
    assert policy is not None
    assert "education_app" in policy[0]
