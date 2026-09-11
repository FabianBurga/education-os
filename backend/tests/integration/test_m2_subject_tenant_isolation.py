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


@pytest.fixture
def two_subject_tenants():
    org_a, org_b = uuid4(), uuid4()
    inst_a, inst_b = uuid4(), uuid4()
    subject_a, subject_b = uuid4(), uuid4()

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO organizations(id,name,status,created_at) VALUES(%s,%s,'ACTIVE',now())",
            (org_a, "M2 Tenant A"),
        )
        cur.execute(
            "INSERT INTO organizations(id,name,status,created_at) VALUES(%s,%s,'ACTIVE',now())",
            (org_b, "M2 Tenant B"),
        )
        cur.execute(
            """
            INSERT INTO institutions(id,organization_id,name,type,status,created_at)
            VALUES(%s,%s,%s,'PRIVATE','ACTIVE',now())
            """,
            (inst_a, org_a, "M2 Institution A"),
        )
        cur.execute(
            """
            INSERT INTO institutions(id,organization_id,name,type,status,created_at)
            VALUES(%s,%s,%s,'PRIVATE','ACTIVE',now())
            """,
            (inst_b, org_b, "M2 Institution B"),
        )
        cur.execute(
            """
            INSERT INTO subjects(
                id,organization_id,institution_id,code,name,status,created_at
            ) VALUES(%s,%s,%s,'SUB-A','Subject A','ACTIVE',now())
            """,
            (subject_a, org_a, inst_a),
        )
        cur.execute(
            """
            INSERT INTO subjects(
                id,organization_id,institution_id,code,name,status,created_at
            ) VALUES(%s,%s,%s,'SUB-B','Subject B','ACTIVE',now())
            """,
            (subject_b, org_b, inst_b),
        )

    yield {
        "org_a": org_a,
        "org_b": org_b,
        "inst_a": inst_a,
        "inst_b": inst_b,
        "subject_a": subject_a,
        "subject_b": subject_b,
    }

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM subjects WHERE id IN (%s,%s)", (subject_a, subject_b))
        cur.execute("DELETE FROM institutions WHERE id IN (%s,%s)", (inst_a, inst_b))
        cur.execute("DELETE FROM organizations WHERE id IN (%s,%s)", (org_a, org_b))


def apply_context(cur, organization_id, institution_id):
    cur.execute(
        "SELECT set_config('app.organization_id', %s, true)",
        (str(organization_id),),
    )
    cur.execute(
        "SELECT set_config('app.institution_id', %s, true)",
        (str(institution_id),),
    )


def test_subject_read_is_tenant_isolated(two_subject_tenants) -> None:
    tenant = two_subject_tenants
    with psycopg.connect(APP_URL) as conn, conn.cursor() as cur:
        apply_context(cur, tenant["org_a"], tenant["inst_a"])
        cur.execute("SELECT id FROM subjects ORDER BY id")
        ids = {row[0] for row in cur.fetchall()}

    assert tenant["subject_a"] in ids
    assert tenant["subject_b"] not in ids


def test_subject_cross_tenant_insert_is_blocked(two_subject_tenants) -> None:
    tenant = two_subject_tenants
    with psycopg.connect(APP_URL) as conn, conn.cursor() as cur:
        apply_context(cur, tenant["org_a"], tenant["inst_a"])
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                """
                INSERT INTO subjects(
                    id,organization_id,institution_id,code,name,status,created_at
                ) VALUES(%s,%s,%s,'ILLEGAL','Illegal','ACTIVE',now())
                """,
                (uuid4(), tenant["org_b"], tenant["inst_b"]),
            )
