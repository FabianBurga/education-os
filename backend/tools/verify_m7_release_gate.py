from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

CRITICAL_TABLES = {
    "student_profiles",
    "guardian_profiles",
    "staff_profiles",
    "enrollments",
    "sections",
    "attendance_records",
    "grade_entries",
    "intelligence_signals",
    "automation_cases",
    "automation_tasks",
    "guardian_student_portal_access",
    "family_notices",
    "family_notice_receipts",
    "pilot_readiness_runs",
}

EXPECTED_API_PATHS = {
    "/api/v1/students",
    "/api/v1/academics/sections",
    "/api/v1/attendance/codes",
    "/api/v1/grades/assessments",
    "/api/v1/intelligence/rector/overview",
    "/api/v1/automation/rules",
    "/api/v1/family-portal/children",
    "/api/v1/operations/security-baseline",
    "/api/v1/operations/pilot/readiness/run",
}


def owner_url() -> str:
    return os.getenv(
        "OWNER_DATABASE_URL_PG",
        "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
    )


def check_runtime_role() -> None:
    with psycopg.connect(owner_url()) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT rolsuper, rolbypassrls, rolinherit
            FROM pg_roles
            WHERE rolname = 'education_app'
            """
        )
        row = cur.fetchone()

    assert row is not None, "education_app role not found"
    assert row == (False, False, False), (
        f"education_app must be NOSUPERUSER/NOBYPASSRLS/NOINHERIT; actual={row}"
    )
    print("education_app role hardening: OK")


def check_critical_rls() -> None:
    with psycopg.connect(owner_url()) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, r.rolname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_roles r ON r.oid = c.relowner
            WHERE n.nspname = 'public'
              AND c.relname = ANY(%s)
            """,
            (list(CRITICAL_TABLES),),
        )
        rows = cur.fetchall()

    found = {row[0] for row in rows}
    assert found == CRITICAL_TABLES, (
        f"critical table mismatch; missing={sorted(CRITICAL_TABLES - found)}, "
        f"unexpected={sorted(found - CRITICAL_TABLES)}"
    )
    assert all(row[1] and row[2] for row in rows), "critical table without FORCE RLS"
    runtime_owned = [row[0] for row in rows if row[3] == "education_app"]
    assert not runtime_owned, f"runtime role owns tenant tables: {runtime_owned}"
    print("Critical FORCE RLS + ownership: OK")


def check_api_contracts() -> None:
    from app.main import app

    paths = set(app.openapi()["paths"])
    missing = EXPECTED_API_PATHS - paths
    assert not missing, f"missing API contracts: {sorted(missing)}"
    print("M1-M7 API contracts: OK")


def check_operations_staff_boundary() -> None:
    from app.api.access import require_staff_access
    from app.modules.operations.router import router

    dependency_calls = {dependency.dependency for dependency in router.dependencies}
    assert require_staff_access in dependency_calls, (
        "Operations router must require active StaffProfile"
    )
    print("M7 Operations staff boundary: OK")


def main() -> None:
    check_runtime_role()
    check_critical_rls()
    check_api_contracts()
    check_operations_staff_boundary()
    print("M7 release gate: PASSED")


if __name__ == "__main__":
    main()
