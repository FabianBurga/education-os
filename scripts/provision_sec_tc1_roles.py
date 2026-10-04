"""Provision the dedicated SEC-TC1 database roles.

This administrative helper sets only role attributes and the issuer
credential. Run migrations separately after provisioning. It never prints
the issuer password or stores it in repository files.
"""

from __future__ import annotations

import os
import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

ISSUER = "education_context_issuer"
FUNCTION_OWNER = "education_context_function_owner"


def _attrs(conn: psycopg.Connection, name: str) -> tuple[bool, ...] | None:
    return conn.execute(
        """SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
                  rolinherit, rolbypassrls
           FROM pg_catalog.pg_roles WHERE rolname = %s""",
        (name,),
    ).fetchone()


def _membership_count(conn: psycopg.Connection, name: str) -> int:
    return conn.execute(
        """SELECT count(*) FROM pg_catalog.pg_auth_members am
           JOIN pg_catalog.pg_roles granted ON granted.oid = am.roleid
           JOIN pg_catalog.pg_roles member ON member.oid = am.member
           WHERE granted.rolname = %s OR member.rolname = %s""",
        (name, name),
    ).fetchone()[0]


_FUNCTION_OWNER_TABLE_GRANTS = {
    (table, "SELECT") for table in (
        "user_accounts", "institutions", "memberships", "membership_roles", "roles",
        "role_permissions", "permissions", "family_notice_receipts", "guardian_profiles",
        "guardian_student_portal_access", "staff_profiles", "teaching_assignments",
        "course_offerings", "student_section_assignments", "enrollments",
        "intervention_followups", "interventions", "accountability_obligations",
        "accountability_cases",
    )
} | {
    ("audit_logs", "INSERT"),
    ("sec_tc1_capabilities", "SELECT"),
    ("sec_tc1_capabilities", "INSERT"),
    ("sec_tc1_capabilities", "UPDATE"),
}
for _table in (
    "intervention_followup_acknowledgement_evidence_links",
    "intervention_followup_acknowledgement_evidence_corrections",
    "accountability_obligation_acknowledgement_evidence_links",
    "accountability_obligation_acknowledgement_evidence_corrections",
):
    _FUNCTION_OWNER_TABLE_GRANTS.update({(_table, "SELECT"), (_table, "INSERT")})


def _unexpected_table_grants(conn: psycopg.Connection, name: str) -> list[tuple[str, str]]:
    return conn.execute(
        """SELECT table_name, privilege_type FROM information_schema.role_table_grants
           WHERE grantee = %s AND table_schema = 'public'""",
        (name,),
    ).fetchall()


def main() -> int:
    owner_url = os.environ.get("OWNER_DATABASE_URL")
    password = os.environ.get("TRUSTED_CONTEXT_ISSUER_PASSWORD")
    if not owner_url or not password:
        print("Set OWNER_DATABASE_URL and TRUSTED_CONTEXT_ISSUER_PASSWORD in the provisioning environment.", file=sys.stderr)
        return 2
    if len(password) < 32:
        print("TRUSTED_CONTEXT_ISSUER_PASSWORD must contain at least 32 characters.", file=sys.stderr)
        return 2
    parsed_owner_url = make_url(owner_url)
    if parsed_owner_url.username != "education_owner":
        print("OWNER_DATABASE_URL must authenticate as education_owner for role provisioning.", file=sys.stderr)
        return 2
    psycopg_owner_url = parsed_owner_url.set(drivername="postgresql").render_as_string(hide_password=False)

    expected = {
        ISSUER: (True, False, False, False, False, False),
        FUNCTION_OWNER: (False, False, False, False, False, False),
    }
    stage = "connect"
    try:
        with psycopg.connect(psycopg_owner_url, autocommit=False) as conn:
            stage = "verify-owner-session"
            actor = conn.execute("SELECT current_user").fetchone()[0]
            if actor != "education_owner":
                raise RuntimeError("Connected provisioning role does not match education_owner")

            for name, attributes in expected.items():
                stage = f"inspect-role:{name}"
                if _attrs(conn, name) is None:
                    stage = f"create-role:{name}"
                    conn.execute(
                        sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS")
                        .format(sql.Identifier(name))
                        if name == ISSUER
                        else sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS")
                        .format(sql.Identifier(name))
                    )
                actual = _attrs(conn, name)
                stage = f"verify-role-attributes:{name}"
                if actual != attributes:
                    raise RuntimeError(f"Unexpected security attributes for {name}; refusing to alter role")
                stage = f"verify-role-membership:{name}"
                if _membership_count(conn, name) != 0:
                    raise RuntimeError(f"Role membership exists for {name}; refusing to provision")
                stage = f"verify-public-table-grants:{name}"
                observed_grants = set(_unexpected_table_grants(conn, name))
                permitted_grants = _FUNCTION_OWNER_TABLE_GRANTS if name == FUNCTION_OWNER else set()
                if not observed_grants.issubset(permitted_grants):
                    raise RuntimeError(f"Unexpected public table grants for {name}; refusing to provision")

            stage = "set-issuer-password"
            conn.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(ISSUER), sql.Literal(password)
                )
            )
            conn.commit()
    except (psycopg.Error, RuntimeError) as exc:
        # Report only a non-secret category and SQLSTATE; never emit the
        # exception message because drivers may include connection details.
        state = getattr(exc, "sqlstate", None)
        print(
            f"SEC-TC1 provisioning failed at {stage} ({type(exc).__name__}; SQLSTATE={state or 'n/a'}). "
            "Secret values and exception details are suppressed.",
            file=sys.stderr,
        )
        return 1
    print("SEC-TC1 roles verified and issuer credential provisioned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
