import os
from uuid import uuid4

import psycopg
import pytest

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)
APP_URL = os.getenv(
    "DATABASE_URL_PG",
    "postgresql://education_app:education_app_dev@localhost:5432/education_os",
)


@pytest.fixture()
def tenants():
    org_a, org_b = uuid4(), uuid4()
    inst_a, inst_b = uuid4(), uuid4()
    campus_a, campus_b = uuid4(), uuid4()

    with psycopg.connect(OWNER_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO organizations(id,name,status,created_at) VALUES(%s,'Org A','ACTIVE',now())",
                (org_a,),
            )
            cur.execute(
                "INSERT INTO organizations(id,name,status,created_at) VALUES(%s,'Org B','ACTIVE',now())",
                (org_b,),
            )
            cur.execute(
                """INSERT INTO institutions(id,organization_id,name,type,status,created_at)
                   VALUES(%s,%s,'School A','PRIVATE','ACTIVE',now())""",
                (inst_a, org_a),
            )
            cur.execute(
                """INSERT INTO institutions(id,organization_id,name,type,status,created_at)
                   VALUES(%s,%s,'School B','PRIVATE','ACTIVE',now())""",
                (inst_b, org_b),
            )
            cur.execute(
                "INSERT INTO campuses(id,institution_id,name,created_at) VALUES(%s,%s,'Campus A',now())",
                (campus_a, inst_a),
            )
            cur.execute(
                "INSERT INTO campuses(id,institution_id,name,created_at) VALUES(%s,%s,'Campus B',now())",
                (campus_b, inst_b),
            )
        conn.commit()

    yield {
        "org_a": org_a,
        "org_b": org_b,
        "inst_a": inst_a,
        "inst_b": inst_b,
        "campus_a": campus_a,
        "campus_b": campus_b,
    }

    with psycopg.connect(OWNER_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM campuses WHERE id IN (%s,%s)", (campus_a, campus_b))
            cur.execute("DELETE FROM institutions WHERE id IN (%s,%s)", (inst_a, inst_b))
            cur.execute("DELETE FROM organizations WHERE id IN (%s,%s)", (org_a, org_b))
        conn.commit()


def set_context(cur, org_id, inst_id, user_id=None):
    cur.execute("SELECT set_config('app.organization_id', %s, true)", (str(org_id),))
    cur.execute("SELECT set_config('app.institution_id', %s, true)", (str(inst_id),))
    cur.execute(
        "SELECT set_config('app.user_id', %s, true)",
        (str(user_id or uuid4()),),
    )


def test_runtime_role_cannot_bypass_rls():
    with psycopg.connect(OWNER_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls
                FROM pg_roles
                WHERE rolname = 'education_app'
                """
            )
            assert cur.fetchone() == (False, False, False, False)


def test_campuses_rls_is_enabled_and_forced():
    with psycopg.connect(OWNER_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT relrowsecurity, relforcerowsecurity
                FROM pg_class
                WHERE relname = 'campuses'
                """
            )
            assert cur.fetchone() == (True, True)


def test_no_context_returns_no_institution_rows(tenants):
    with psycopg.connect(APP_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM campuses")
            assert cur.fetchall() == []


def test_tenant_a_can_only_read_a(tenants):
    with psycopg.connect(APP_URL) as conn:
        with conn.cursor() as cur:
            set_context(cur, tenants["org_a"], tenants["inst_a"])
            cur.execute("SELECT id FROM campuses ORDER BY name")
            assert cur.fetchall() == [(tenants["campus_a"],)]


def test_tenant_b_can_only_read_b(tenants):
    with psycopg.connect(APP_URL) as conn:
        with conn.cursor() as cur:
            set_context(cur, tenants["org_b"], tenants["inst_b"])
            cur.execute("SELECT id FROM campuses ORDER BY name")
            assert cur.fetchall() == [(tenants["campus_b"],)]


def test_cross_tenant_insert_is_denied(tenants):
    with psycopg.connect(APP_URL) as conn:
        with conn.cursor() as cur:
            set_context(cur, tenants["org_a"], tenants["inst_a"])
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(
                    "INSERT INTO campuses(id,institution_id,name,created_at) VALUES(%s,%s,'Illegal',now())",
                    (uuid4(), tenants["inst_b"]),
                )


def test_cross_tenant_update_changes_zero_rows(tenants):
    with psycopg.connect(APP_URL) as conn:
        with conn.cursor() as cur:
            set_context(cur, tenants["org_a"], tenants["inst_a"])
            cur.execute(
                "UPDATE campuses SET name='Illegal update' WHERE id=%s",
                (tenants["campus_b"],),
            )
            assert cur.rowcount == 0


def test_cross_tenant_delete_changes_zero_rows(tenants):
    with psycopg.connect(APP_URL) as conn:
        with conn.cursor() as cur:
            set_context(cur, tenants["org_a"], tenants["inst_a"])
            cur.execute(
                "DELETE FROM campuses WHERE id=%s",
                (tenants["campus_b"],),
            )
            assert cur.rowcount == 0
