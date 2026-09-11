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


def test_automation_rule_read_is_tenant_isolated() -> None:
    org_a, org_b = uuid4(), uuid4()
    inst_a, inst_b = uuid4(), uuid4()
    rule_a, rule_b = uuid4(), uuid4()

    try:
        with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO organizations(id,name,status,created_at) VALUES(%s,%s,'ACTIVE',now())",
                (org_a, "M5 Org A"),
            )
            cur.execute(
                "INSERT INTO organizations(id,name,status,created_at) VALUES(%s,%s,'ACTIVE',now())",
                (org_b, "M5 Org B"),
            )
            cur.execute(
                """
                INSERT INTO institutions(id,organization_id,name,type,status,created_at)
                VALUES(%s,%s,%s,'PRIVATE','ACTIVE',now())
                """,
                (inst_a, org_a, "M5 Institution A"),
            )
            cur.execute(
                """
                INSERT INTO institutions(id,organization_id,name,type,status,created_at)
                VALUES(%s,%s,%s,'PRIVATE','ACTIVE',now())
                """,
                (inst_b, org_b, "M5 Institution B"),
            )
            cur.execute(
                """
                INSERT INTO automation_rules(
                    id,organization_id,institution_id,code,name,signal_type,
                    minimum_severity,assignee_role_code,task_title,due_in_hours,
                    escalate_after_hours,is_enabled,created_at
                ) VALUES(%s,%s,%s,'R-A','Rule A','ATTENDANCE_RISK',
                    'MEDIUM','INSPECTOR','Review',24,48,true,now())
                """,
                (rule_a, org_a, inst_a),
            )
            cur.execute(
                """
                INSERT INTO automation_rules(
                    id,organization_id,institution_id,code,name,signal_type,
                    minimum_severity,assignee_role_code,task_title,due_in_hours,
                    escalate_after_hours,is_enabled,created_at
                ) VALUES(%s,%s,%s,'R-B','Rule B','ACADEMIC_RISK',
                    'MEDIUM','TUTOR','Review',24,48,true,now())
                """,
                (rule_b, org_b, inst_b),
            )

        with psycopg.connect(APP_URL) as conn, conn.cursor() as cur:
            apply_context(cur, org_a, inst_a)
            cur.execute("SELECT id FROM automation_rules")
            ids = {row[0] for row in cur.fetchall()}

        assert rule_a in ids
        assert rule_b not in ids
    finally:
        with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM automation_rules WHERE id IN (%s,%s)", (rule_a, rule_b))
            cur.execute("DELETE FROM institutions WHERE id IN (%s,%s)", (inst_a, inst_b))
            cur.execute("DELETE FROM organizations WHERE id IN (%s,%s)", (org_a, org_b))
