import json
from datetime import UTC, datetime

from sqlalchemy import text
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.operations.models import PilotReadinessRun
from app.modules.operations.schemas import (
    PilotDataSummary,
    PilotReadinessResult,
    ReadinessCheck,
    SecurityBaseline,
)

CRITICAL_TABLES = (
    "student_profiles",
    "guardian_profiles",
    "staff_profiles",
    "enrollments",
    "sections",
    "attendance_records",
    "grade_entries",
    "intelligence_signals",
    "automation_rules",
    "automation_cases",
    "automation_tasks",
    "guardian_student_portal_access",
    "family_notices",
    "family_notice_receipts",
    "communication_templates",
    "communications",
    "communication_targets",
    "communication_recipients",
    "billing_concepts",
    "billing_accounts",
    "billing_charges",
    "billing_payments",
    "billing_allocations",
    "pilot_readiness_runs",
)
CRITICAL_TABLES_SQL = (
    "'student_profiles', 'guardian_profiles', 'staff_profiles', "
    "'enrollments', 'sections', 'attendance_records', 'grade_entries', "
    "'intelligence_signals', 'automation_rules', 'automation_cases', "
    "'automation_tasks', 'guardian_student_portal_access', 'family_notices', "
    "'family_notice_receipts', 'communication_templates', 'communications', "
    "'communication_targets', 'communication_recipients', 'billing_concepts', "
    "'billing_accounts', 'billing_charges', 'billing_payments', "
    "'billing_allocations', 'pilot_readiness_runs'"
)


def _scalar(session: Session, sql: str):
    row = session.exec(text(sql)).first()
    if row is None:
        return None
    return row[0]


def security_baseline(session: Session) -> SecurityBaseline:
    role = session.exec(
        text(
            """
            SELECT rolname, rolsuper, rolbypassrls, rolinherit
            FROM pg_roles
            WHERE rolname = 'education_app'
            """
        )
    ).first()

    rows = session.exec(
        text(
            f"""
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, r.rolname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_roles r ON r.oid = c.relowner
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              AND c.relname IN ({CRITICAL_TABLES_SQL})
            """
        )
    ).all()

    force_rls = sum(
        1
        for _, enabled, forced, _ in rows
        if enabled and forced
    )
    runtime_owned = sum(
        1
        for _, _, _, owner in rows
        if owner == "education_app"
    )

    return SecurityBaseline(
        runtime_role="education_app",
        runtime_nosuperuser=bool(role is not None and not role[1]),
        runtime_nobypassrls=bool(role is not None and not role[2]),
        runtime_noinherit=bool(role is not None and not role[3]),
        critical_tables_total=len(CRITICAL_TABLES),
        critical_tables_force_rls=force_rls,
        critical_tables_runtime_owned=runtime_owned,
    )


def pilot_data_summary(session: Session) -> PilotDataSummary:
    def count(sql: str) -> int:
        return int(_scalar(session, sql) or 0)

    return PilotDataSummary(
        active_students=count(
            "SELECT COUNT(*) FROM student_profiles WHERE status = 'ACTIVE'"
        ),
        active_guardians=count(
            "SELECT COUNT(*) FROM guardian_profiles WHERE status = 'ACTIVE'"
        ),
        active_staff=count(
            "SELECT COUNT(*) FROM staff_profiles WHERE status = 'ACTIVE'"
        ),
        active_sections=count(
            "SELECT COUNT(*) FROM sections WHERE status = 'ACTIVE'"
        ),
        attendance_records=count(
            "SELECT COUNT(*) FROM attendance_records"
        ),
        grade_entries=count(
            "SELECT COUNT(*) FROM grade_entries"
        ),
        open_intelligence_signals=count(
            "SELECT COUNT(*) FROM intelligence_signals WHERE status = 'OPEN'"
        ),
        open_automation_cases=count(
            "SELECT COUNT(*) FROM automation_cases WHERE status = 'OPEN'"
        ),
    )


def _migration_check(session: Session) -> ReadinessCheck:
    revision = _scalar(
        session,
        "SELECT version_num FROM alembic_version",
    )
    return ReadinessCheck(
        code="ALEMBIC_HEAD",
        passed=revision == "0016_m14",
        detail=f"database revision={revision}",
    )


def _role_checks(session: Session) -> list[ReadinessCheck]:
    baseline = security_baseline(session)
    return [
        ReadinessCheck(
            code="RUNTIME_NOSUPERUSER",
            passed=baseline.runtime_nosuperuser,
            detail="education_app must not be superuser",
        ),
        ReadinessCheck(
            code="RUNTIME_NOBYPASSRLS",
            passed=baseline.runtime_nobypassrls,
            detail="education_app must not bypass RLS",
        ),
        ReadinessCheck(
            code="RUNTIME_NOINHERIT",
            passed=baseline.runtime_noinherit,
            detail="education_app must not inherit elevated capabilities",
        ),
        ReadinessCheck(
            code="RUNTIME_NOT_TABLE_OWNER",
            passed=baseline.critical_tables_runtime_owned == 0,
            detail=(
                "runtime-owned critical tables="
                f"{baseline.critical_tables_runtime_owned}"
            ),
        ),
    ]


def _rls_check(session: Session) -> ReadinessCheck:
    baseline = security_baseline(session)
    passed = (
        baseline.critical_tables_force_rls
        == baseline.critical_tables_total
    )
    return ReadinessCheck(
        code="CRITICAL_FORCE_RLS",
        passed=passed,
        detail=(
            f"force_rls={baseline.critical_tables_force_rls}/"
            f"{baseline.critical_tables_total}"
        ),
    )


def run_pilot_readiness(
    session: Session,
    principal: CurrentPrincipal,
) -> PilotReadinessResult:
    executed_at = datetime.now(UTC)
    checks = [
        _migration_check(session),
        *_role_checks(session),
        _rls_check(session),
    ]

    passed = sum(1 for item in checks if item.passed)
    failed = len(checks) - passed
    status = "PASS" if failed == 0 else "FAIL"

    report = json.dumps(
        {
            "status": status,
            "checks": [item.model_dump() for item in checks],
        },
        ensure_ascii=False,
        default=str,
    )

    entity = PilotReadinessRun(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        executed_by_user_id=principal.user_id,
        status=status,
        checks_total=len(checks),
        checks_passed=passed,
        checks_failed=failed,
        report_json=report,
        executed_at=executed_at,
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)

    return PilotReadinessResult(
        run_id=entity.id,
        status=status,
        checks_total=len(checks),
        checks_passed=passed,
        checks_failed=failed,
        checks=checks,
        executed_at=executed_at,
    )


def latest_pilot_readiness(session: Session):
    return session.exec(
        select(PilotReadinessRun).order_by(
            PilotReadinessRun.executed_at.desc()
        )
    ).first()
