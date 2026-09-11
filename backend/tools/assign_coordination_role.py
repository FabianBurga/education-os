from __future__ import annotations

import argparse
import os
import uuid

import psycopg

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)

ALLOWED_ROLES = {"RECTOR", "ACADEMIC_COORDINATOR"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Owner-only explicit Rector / Academic Coordinator assignment."
    )
    parser.add_argument("--login-email", required=True)
    parser.add_argument(
        "--role",
        choices=sorted(ALLOWED_ROLES),
        required=True,
    )
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
            SELECT m.id, m.institution_id
            FROM user_accounts ua
            JOIN memberships m ON m.user_id = ua.id
            JOIN staff_profiles sp
              ON sp.person_id = ua.person_id
             AND sp.institution_id = m.institution_id
             AND sp.status = 'ACTIVE'
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
            raise SystemExit("No active staff membership found for that login.")
        if len(rows) > 1 and not args.institution_id:
            raise SystemExit(
                "More than one institution found; rerun with --institution-id."
            )

        membership_id, institution_id = rows[0]
        cur.execute(
            """
            SELECT id
            FROM roles
            WHERE institution_id = %s
              AND key = %s
            """,
            (institution_id, args.role),
        )
        role = cur.fetchone()
        if role is None:
            raise SystemExit(
                f"{args.role} role is missing; migrate to 0011_m9 first."
            )

        cur.execute(
            """
            INSERT INTO membership_roles (membership_id, role_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (membership_id, role[0]),
        )
        conn.commit()

    print(f"{args.role} assignment: OK")
    print(f"institution_id={institution_id}")
    print(f"membership_id={membership_id}")


if __name__ == "__main__":
    main()
