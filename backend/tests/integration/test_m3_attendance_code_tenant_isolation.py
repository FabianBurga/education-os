import os
from uuid import uuid4

import psycopg

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)
APP_URL = os.getenv(
    "DATABASE_URL_PG",
    "postgresql://education_app:education_app_dev@localhost:5432/education_os",
)


def apply_context(cur, org_id, inst_id):
    cur.execute("SELECT set_config('app.organization_id', %s, true)", (str(org_id),))
    cur.execute("SELECT set_config('app.institution_id', %s, true)", (str(inst_id),))


def test_attendance_code_read_is_tenant_isolated() -> None:
    org_a, org_b = uuid4(), uuid4()
    inst_a, inst_b = uuid4(), uuid4()
    code_a, code_b = uuid4(), uuid4()

    try:
        with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO organizations(id,name,status,created_at) VALUES(%s,%s,'ACTIVE',now())",
                (org_a, "M3 Org A"),
            )
            cur.execute(
                "INSERT INTO organizations(id,name,status,created_at) VALUES(%s,%s,'ACTIVE',now())",
                (org_b, "M3 Org B"),
            )
            cur.execute(
                """
                INSERT INTO institutions(id,organization_id,name,type,status,created_at)
                VALUES(%s,%s,%s,'PRIVATE','ACTIVE',now())
                """,
                (inst_a, org_a, "M3 Institution A"),
            )
            cur.execute(
                """
                INSERT INTO institutions(id,organization_id,name,type,status,created_at)
                VALUES(%s,%s,%s,'PRIVATE','ACTIVE',now())
                """,
                (inst_b, org_b, "M3 Institution B"),
            )
            cur.execute(
                """
                INSERT INTO attendance_codes(
                    id,organization_id,institution_id,code,label,semantic,status,created_at
                ) VALUES(%s,%s,%s,'P','Present','PRESENT','ACTIVE',now())
                """,
                (code_a, org_a, inst_a),
            )
            cur.execute(
                """
                INSERT INTO attendance_codes(
                    id,organization_id,institution_id,code,label,semantic,status,created_at
                ) VALUES(%s,%s,%s,'A','Absent','ABSENT','ACTIVE',now())
                """,
                (code_b, org_b, inst_b),
            )

        with psycopg.connect(APP_URL) as conn, conn.cursor() as cur:
            apply_context(cur, org_a, inst_a)
            cur.execute("SELECT id FROM attendance_codes")
            ids = {row[0] for row in cur.fetchall()}

        assert code_a in ids
        assert code_b not in ids
    finally:
        with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM attendance_codes WHERE id IN (%s,%s)", (code_a, code_b))
            cur.execute("DELETE FROM institutions WHERE id IN (%s,%s)", (inst_a, inst_b))
            cur.execute("DELETE FROM organizations WHERE id IN (%s,%s)", (org_a, org_b))
