from __future__ import annotations

import argparse
import os
from uuid import UUID

import psycopg

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Explicitly assign FINANCE_MANAGER to an active staff membership."
    )
    parser.add_argument("--login-email", required=True)
    parser.add_argument("--institution-id")
    args = parser.parse_args()

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        params: list[object] = [args.login_email]
        institution_filter = ""
        if args.institution_id:
            institution_filter = "AND m.institution_id = %s"
            params.append(UUID(args.institution_id))

        cur.execute(
            f"""
            SELECT
                m.id,
                m.institution_id,
                sp.id
            FROM user_accounts ua
            JOIN memberships m
              ON m.user_id = ua.id
             AND m.status = 'ACTIVE'
            JOIN staff_profiles sp
              ON sp.person_id = ua.person_id
             AND sp.institution_id = m.institution_id
             AND sp.status = 'ACTIVE'
            WHERE ua.login_email = %s
              AND ua.is_active = true
              {institution_filter}
            ORDER BY m.created_at
            """,
            params,
        )
        rows = cur.fetchall()
        if not rows:
            raise SystemExit("Active staff membership not found.")
        if len(rows) > 1 and not args.institution_id:
            raise SystemExit(
                "Multiple active staff memberships found; provide --institution-id."
            )

        membership_id, institution_id, _staff_profile_id = rows[0]
        cur.execute(
            """
            SELECT id
            FROM roles
            WHERE institution_id = %s
              AND key = 'FINANCE_MANAGER'
            """,
            (institution_id,),
        )
        role = cur.fetchone()
        if role is None:
            raise SystemExit("FINANCE_MANAGER role not found. M14 must be installed first.")

        cur.execute(
            """
            INSERT INTO membership_roles (membership_id, role_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (membership_id, role[0]),
        )
        conn.commit()

    print(
        "FINANCE_MANAGER assigned explicitly | "
        f"login={args.login_email} institution={institution_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
