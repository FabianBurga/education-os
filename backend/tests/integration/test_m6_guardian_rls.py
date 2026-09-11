import os
from datetime import UTC, datetime
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


def context(cur, org_id, inst_id, user_id):
    cur.execute("SELECT set_config('app.organization_id', %s, true)", (str(org_id),))
    cur.execute("SELECT set_config('app.institution_id', %s, true)", (str(inst_id),))
    cur.execute("SELECT set_config('app.user_id', %s, true)", (str(user_id),))


def test_guardian_sees_only_own_portal_grant() -> None:
    org_id, inst_id = uuid4(), uuid4()
    guardian_person_a, guardian_person_b, student_person_a, student_person_b = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    user_a, user_b = uuid4(), uuid4()
    guardian_a, guardian_b, student_a, student_b = uuid4(), uuid4(), uuid4(), uuid4()
    grant_a, grant_b = uuid4(), uuid4()

    try:
        with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO organizations(id,name,status,created_at) VALUES(%s,%s,'ACTIVE',now())",
                (org_id, "M6 Org"),
            )
            cur.execute(
                """
                INSERT INTO institutions(id,organization_id,name,type,status,created_at)
                VALUES(%s,%s,%s,'PRIVATE','ACTIVE',now())
                """,
                (inst_id, org_id, "M6 Institution"),
            )
            for person_id, name in (
                (guardian_person_a, "Guardian A"),
                (guardian_person_b, "Guardian B"),
                (student_person_a, "Student A"),
                (student_person_b, "Student B"),
            ):
                cur.execute(
                    """
                    INSERT INTO persons(
                        id,organization_id,given_names,family_names,created_at
                    ) VALUES(%s,%s,%s,'Test',now())
                    """,
                    (person_id, org_id, name),
                )
            for user_id, person_id, email in (
                (user_a, guardian_person_a, "m6-a@example.test"),
                (user_b, guardian_person_b, "m6-b@example.test"),
            ):
                cur.execute(
                    """
                    INSERT INTO user_accounts(
                        id,person_id,login_email,password_hash,is_active,created_at
                    ) VALUES(%s,%s,%s,'test',true,now())
                    """,
                    (user_id, person_id, email),
                )
                cur.execute(
                    """
                    INSERT INTO memberships(
                        id,user_id,institution_id,status,created_at
                    ) VALUES(%s,%s,%s,'ACTIVE',now())
                    """,
                    (uuid4(), user_id, inst_id),
                )
            cur.execute(
                """
                INSERT INTO guardian_profiles(
                    id,organization_id,institution_id,person_id,status,created_at
                ) VALUES(%s,%s,%s,%s,'ACTIVE',now()),(%s,%s,%s,%s,'ACTIVE',now())
                """,
                (
                    guardian_a,
                    org_id,
                    inst_id,
                    guardian_person_a,
                    guardian_b,
                    org_id,
                    inst_id,
                    guardian_person_b,
                ),
            )
            cur.execute(
                """
                INSERT INTO student_profiles(
                    id,organization_id,institution_id,person_id,status,created_at,updated_at
                ) VALUES(%s,%s,%s,%s,'ACTIVE',now(),now()),(%s,%s,%s,%s,'ACTIVE',now(),now())
                """,
                (
                    student_a,
                    org_id,
                    inst_id,
                    student_person_a,
                    student_b,
                    org_id,
                    inst_id,
                    student_person_b,
                ),
            )
            cur.execute(
                """
                INSERT INTO guardian_student_portal_access(
                    id,organization_id,institution_id,guardian_profile_id,
                    student_profile_id,access_level,status,granted_at
                ) VALUES(%s,%s,%s,%s,%s,'STANDARD','ACTIVE',%s),
                        (%s,%s,%s,%s,%s,'STANDARD','ACTIVE',%s)
                """,
                (
                    grant_a,
                    org_id,
                    inst_id,
                    guardian_a,
                    student_a,
                    datetime.now(UTC),
                    grant_b,
                    org_id,
                    inst_id,
                    guardian_b,
                    student_b,
                    datetime.now(UTC),
                ),
            )

        with psycopg.connect(APP_URL) as conn, conn.cursor() as cur:
            context(cur, org_id, inst_id, user_a)
            cur.execute("SELECT id FROM guardian_student_portal_access")
            ids = {row[0] for row in cur.fetchall()}

        assert grant_a in ids
        assert grant_b not in ids
    finally:
        with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM guardian_student_portal_access WHERE id IN (%s,%s)",
                (grant_a, grant_b),
            )
            cur.execute(
                "DELETE FROM student_profiles WHERE id IN (%s,%s)",
                (student_a, student_b),
            )
            cur.execute(
                "DELETE FROM guardian_profiles WHERE id IN (%s,%s)",
                (guardian_a, guardian_b),
            )
            cur.execute("DELETE FROM memberships WHERE user_id IN (%s,%s)", (user_a, user_b))
            cur.execute("DELETE FROM user_accounts WHERE id IN (%s,%s)", (user_a, user_b))
            cur.execute(
                "DELETE FROM persons WHERE id IN (%s,%s,%s,%s)",
                (
                    guardian_person_a,
                    guardian_person_b,
                    student_person_a,
                    student_person_b,
                ),
            )
            cur.execute("DELETE FROM institutions WHERE id = %s", (inst_id,))
            cur.execute("DELETE FROM organizations WHERE id = %s", (org_id,))
