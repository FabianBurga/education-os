from __future__ import annotations

import argparse
import os
import uuid

import psycopg

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Owner-only explicit GUARDIAN role assignment."
    )
    parser.add_argument("--login-email", required=True)
    parser.add_argument("--institution-id")
    args = parser.parse_args()

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        params: list[object] = [args.login_email.lower()]
        institution_filter = ""
        if args.institution_id:
            institution_filter = "AND m.institution_id = %s"
            params.append(uuid.UUID(args.institution_id))

        cur.execute(
            f"""
            SELECT
                m.id,
                m.institution_id,
                gp.id
            FROM user_accounts ua
            JOIN memberships m ON m.user_id = ua.id
            JOIN guardian_profiles gp
              ON gp.person_id = ua.person_id
             AND gp.institution_id = m.institution_id
             AND gp.status = 'ACTIVE'
            WHERE lower(ua.login_email) = %s
              AND ua.is_active = true
              AND m.status = 'ACTIVE'
              {institution_filter}
            ORDER BY m.created_at
            """,
            params,
        )
        rows = cur.fetchall()
        if not rows:
            raise SystemExit(
                "No active guardian membership found for that login."
            )
        if len(rows) > 1 and not args.institution_id:
            raise SystemExit(
                "More than one institution found; rerun with --institution-id."
            )

        membership_id, institution_id, guardian_profile_id = rows[0]
        cur.execute(
            """
            SELECT id
            FROM roles
            WHERE institution_id = %s
              AND key = 'GUARDIAN'
            """,
            (institution_id,),
        )
        role = cur.fetchone()
        if role is None:
            raise SystemExit("GUARDIAN role missing; migrate to 0014_m12 first.")

        cur.execute(
            """
            INSERT INTO membership_roles (membership_id, role_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (membership_id, role[0]),
        )
        conn.commit()

    print("GUARDIAN assignment: OK")
    print(f"institution_id={institution_id}")
    print(f"membership_id={membership_id}")
    print(f"guardian_profile_id={guardian_profile_id}")


if __name__ == "__main__":
    main()
