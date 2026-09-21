"""Provision, verify and remove the isolated synthetic investor demo.

This tool is deliberately owner-only and refuses to run unless the operator has
explicitly enabled staging demo mode.  It creates no schema and never creates
credentials or a provider configuration.  The state file contains only IDs and
is written outside the repository by default.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text
from sqlmodel import Session

from app.core import demo
from app.core.config import settings
from app.core.security import hash_password
from app.modules.intelligence.projector import project_institution_intelligence

# Load every router/model before the official M22 projector performs ORM
# queries, so all foreign-key targets are registered in SQLModel metadata. Do
# not leave this import-time bootstrap flag enabled for callers that only
# import the tool (for example, unit tests).
_configured_demo_mode = settings.EDUCATION_OS_DEMO_MODE
settings.EDUCATION_OS_DEMO_MODE = False

_application = importlib.import_module("app.main").app
settings.EDUCATION_OS_DEMO_MODE = _configured_demo_mode

ORG_NAME = "Education OS Demo"
INSTITUTION_NAME = "Unidad Educativa Demostración"
STATE_FILE = Path(
    os.environ.get(
        "EDUCATION_OS_DEMO_STATE_FILE",
        Path(os.environ.get("TEMP", ".")) / "education-os-demo-fixture.json",
    )
)
ALIASES = ("RECTOR", "COORDINATION", "TEACHER", "STUDENT", "GUARDIAN")
ROLE_KEYS = {
    "RECTOR": "RECTOR",
    "COORDINATION": "ACADEMIC_COORDINATOR",
    "TEACHER": "TEACHER",
    "STUDENT": "STUDENT",
    "GUARDIAN": "GUARDIAN",
}
PERMISSIONS = {
    "RECTOR": {
        "agents.use",
        "agents.view",
        "intelligence.read",
        "coord.console.access",
        "coord.analytics.view",
        "student_timeline.read",
        "student_timeline.read_restricted",
        "intervention.read",
        "intervention.suggestion.read",
    },
    "COORDINATION": {
        "agents.use",
        "agents.view",
        "intelligence.read",
        "coord.console.access",
        "coord.analytics.view",
        "student_timeline.read",
        "student_timeline.read_restricted",
        "intervention.read",
        "intervention.suggestion.read",
        "coord.signals.manage",
        "coord.cases.manage",
        "intervention.create",
        "intervention.update",
        "intervention.assign",
        "intervention.resolve",
        "intervention.close",
        "intervention.action.manage",
        "intervention.followup.create",
        "intervention.suggestion.review",
        "intervention.suggestion.generate",
    },
    "TEACHER": {
        "teacher.console.access",
        "teacher.classes.view",
        "teacher.attendance.manage",
        "teacher.grades.manage",
        "teacher.tasks.manage",
        "student_timeline.read",
        "intervention.read",
        "intelligence.read",
    },
    "STUDENT": {
        "student.console.access",
        "student.profile.view",
        "student.classes.view",
        "student.schedule.view",
        "student.attendance.view",
        "student.grades.view",
        "student.progress.view",
        "student.notices.view",
    },
    "GUARDIAN": {
        "guardian.console.access",
        "guardian.students.view",
        "guardian.schedule.view",
        "guardian.attendance.view",
        "guardian.grades.view",
        "guardian.progress.view",
        "guardian.notices.view",
        "guardian.notices.acknowledge",
    },
}


def _require_demo_mode() -> None:
    if (
        os.environ.get("EDUCATION_OS_DEMO_MODE", "").lower() != "true"
        or not settings.EDUCATION_OS_DEMO_MODE
    ):
        raise RuntimeError("Refusing fixture operation: set EDUCATION_OS_DEMO_MODE=true")
    if settings.OWNER_DATABASE_URL is None:
        raise RuntimeError("OWNER_DATABASE_URL is required only for fixture operations")


def _insert(session: Session, table: str, values: dict[str, object]) -> None:
    columns = ", ".join(values)
    bind = ", ".join(f":{key}" for key in values)
    session.exec(text(f"INSERT INTO {table} ({columns}) VALUES ({bind})"), params=values)


def _delete_org(session: Session, org_id: UUID) -> None:
    # Explicit reverse dependency order keeps this safe if a future FK adds a
    # cascade unexpectedly.  No other organization can match this ID.
    session.exec(
        text(
            "DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE institution_id IN (SELECT id FROM institutions WHERE organization_id=CAST(:org AS uuid)))"
        ),
        params={"org": str(org_id)},
    )
    session.exec(
        text(
            "DELETE FROM membership_roles WHERE membership_id IN (SELECT id FROM memberships WHERE institution_id IN (SELECT id FROM institutions WHERE organization_id=CAST(:org AS uuid)))"
        ),
        params={"org": str(org_id)},
    )
    session.exec(
        text("DELETE FROM memberships WHERE institution_id IN (SELECT id FROM institutions WHERE organization_id=CAST(:org AS uuid))"),
        params={"org": str(org_id)},
    )
    session.exec(
        text("DELETE FROM roles WHERE institution_id IN (SELECT id FROM institutions WHERE organization_id=CAST(:org AS uuid))"),
        params={"org": str(org_id)},
    )
    session.exec(
        text("DELETE FROM audit_logs WHERE institution_id IN (SELECT id FROM institutions WHERE organization_id=CAST(:org AS uuid))"),
        params={"org": str(org_id)},
    )
    session.exec(
        text("DELETE FROM event_ledger WHERE organization_id=CAST(:org AS uuid)"),
        params={"org": str(org_id)},
    )
    tables = [
        "agent_budget_events",
        "agent_evidence_refs",
        "agent_tool_calls",
        "agent_run_events",
        "agent_run_steps",
        "agent_provider_calls",
        "agent_runs",
        "agent_policy_versions",
        "agent_definitions",
        "student_timeline_entries",
        "intervention_followups",
        "intervention_actions",
        "interventions",
        "institution_intelligence_daily",
        "cohort_intelligence_daily",
        "student_intelligence_snapshots",
        "intelligence_signals",
        "family_notices",
        "guardian_student_portal_access",
        "student_guardian_relationships",
        "guardian_profiles",
        "attendance_records",
        "class_sessions",
        "attendance_codes",
        "grade_entries",
        "assessments",
        "assessment_categories",
        "grading_periods",
        "grading_scales",
        "student_section_assignments",
        "enrollments",
        "teaching_assignments",
        "course_offerings",
        "schedule_slots",
        "sections",
        "subjects",
        "grade_levels",
        "academic_levels",
        "academic_periods",
        "student_profiles",
        "staff_profiles",
    ]
    for table in tables:
        session.exec(
            text(f"DELETE FROM {table} WHERE organization_id = CAST(:org AS uuid)"),
            params={"org": str(org_id)},
        )
    session.exec(
        text("DELETE FROM campuses WHERE institution_id IN (SELECT id FROM institutions WHERE organization_id=CAST(:org AS uuid))"),
        params={"org": str(org_id)},
    )
    session.exec(
        text("DELETE FROM outbox_events WHERE institution_id IN (SELECT id FROM institutions WHERE organization_id=CAST(:org AS uuid))"),
        params={"org": str(org_id)},
    )
    session.exec(
        text("DELETE FROM institutions WHERE organization_id=CAST(:org AS uuid)"),
        params={"org": str(org_id)},
    )
    session.exec(
        text("DELETE FROM user_accounts WHERE person_id IN (SELECT id FROM persons WHERE organization_id=CAST(:org AS uuid))"),
        params={"org": str(org_id)},
    )
    session.exec(
        text("DELETE FROM persons WHERE organization_id=CAST(:org AS uuid)"),
        params={"org": str(org_id)},
    )
    session.exec(
        text("DELETE FROM organizations WHERE id=CAST(:org AS uuid)"),
        params={"org": str(org_id)},
    )


def _existing(session: Session) -> UUID | None:
    row = session.exec(
        text("SELECT id FROM organizations WHERE name=:name ORDER BY created_at DESC LIMIT 1"),
        params={"name": ORG_NAME},
    ).first()
    return row[0] if row else None


def provision() -> dict[str, object]:
    _require_demo_mode()
    engine = create_engine(settings.OWNER_DATABASE_URL)
    try:
        with Session(engine) as session:
            if _existing(session):
                raise RuntimeError("Education OS Demo already exists; run cleanup first")
            now = datetime.now(UTC)
            today = datetime.now(UTC).date()
            org, inst, campus, period, level, grade, subject, section = (uuid4() for _ in range(8))
            _insert(
                session,
                "organizations",
                {"id": org, "name": ORG_NAME, "status": "ACTIVE", "created_at": now},
            )
            _insert(
                session,
                "institutions",
                {
                    "id": inst,
                    "organization_id": org,
                    "name": INSTITUTION_NAME,
                    "type": "PRIVATE",
                    "status": "ACTIVE",
                    "created_at": now,
                },
            )
            _insert(
                session,
                "campuses",
                {
                    "id": campus,
                    "institution_id": inst,
                    "name": "Campus Demostración",
                    "created_at": now,
                },
            )
            _insert(
                session,
                "academic_periods",
                {
                    "id": period,
                    "organization_id": org,
                    "institution_id": inst,
                    "code": "DEMO-2026",
                    "name": "Año lectivo demostración",
                    "starts_on": date(today.year, 8, 1),
                    "ends_on": date(today.year + 1, 6, 30),
                    "status": "ACTIVE",
                    "created_at": now,
                },
            )
            _insert(
                session,
                "academic_levels",
                {
                    "id": level,
                    "organization_id": org,
                    "institution_id": inst,
                    "code": "BASIC",
                    "name": "Educación básica",
                    "sort_order": 1,
                    "status": "ACTIVE",
                    "created_at": now,
                },
            )
            _insert(
                session,
                "grade_levels",
                {
                    "id": grade,
                    "organization_id": org,
                    "institution_id": inst,
                    "academic_level_id": level,
                    "code": "8EGB",
                    "name": "Octavo de básica",
                    "sort_order": 8,
                    "status": "ACTIVE",
                    "created_at": now,
                },
            )
            _insert(
                session,
                "subjects",
                {
                    "id": subject,
                    "organization_id": org,
                    "institution_id": inst,
                    "code": "MAT-DEMO",
                    "name": "Matemática",
                    "area": "Ciencias exactas",
                    "status": "ACTIVE",
                    "created_at": now,
                },
            )
            _insert(
                session,
                "sections",
                {
                    "id": section,
                    "organization_id": org,
                    "institution_id": inst,
                    "academic_period_id": period,
                    "campus_id": campus,
                    "grade_level_id": grade,
                    "code": "A",
                    "name": "Octavo A",
                    "shift": "MORNING",
                    "capacity": 30,
                    "status": "ACTIVE",
                    "created_at": now,
                },
            )
            course, slot = uuid4(), uuid4()
            _insert(
                session,
                "course_offerings",
                {
                    "id": course,
                    "organization_id": org,
                    "institution_id": inst,
                    "academic_period_id": period,
                    "section_id": section,
                    "subject_id": subject,
                    "status": "ACTIVE",
                    "created_at": now,
                },
            )
            _insert(
                session,
                "schedule_slots",
                {
                    "id": slot,
                    "organization_id": org,
                    "institution_id": inst,
                    "course_offering_id": course,
                    "weekday": 2,
                    "starts_at": time(8),
                    "ends_at": time(9),
                    "room_label": "Aula Demo 1",
                    "created_at": now,
                },
            )
            gp, scale, category = uuid4(), uuid4(), uuid4()
            _insert(
                session,
                "grading_periods",
                {
                    "id": gp,
                    "organization_id": org,
                    "institution_id": inst,
                    "academic_period_id": period,
                    "code": "Q1",
                    "name": "Primer quimestre",
                    "starts_on": date(today.year, 8, 1),
                    "ends_on": date(today.year, 12, 20),
                    "sequence": 1,
                    "status": "ACTIVE",
                    "created_at": now,
                },
            )
            _insert(
                session,
                "grading_scales",
                {
                    "id": scale,
                    "organization_id": org,
                    "institution_id": inst,
                    "code": "TEN",
                    "name": "Escala sobre diez",
                    "minimum_score": 0,
                    "maximum_score": 10,
                    "status": "ACTIVE",
                    "created_at": now,
                },
            )
            _insert(
                session,
                "assessment_categories",
                {
                    "id": category,
                    "organization_id": org,
                    "institution_id": inst,
                    "section_id": section,
                    "course_offering_id": course,
                    "grading_period_id": gp,
                    "code": "CLASSWORK",
                    "name": "Trabajo de clase",
                    "weight_percent": 100,
                    "created_at": now,
                },
            )
            assessment, missing_assessment = uuid4(), uuid4()
            for aid, code, title, due in (
                (assessment, "EVAL-01", "Evaluación de fundamentos", today - timedelta(days=8)),
                (missing_assessment, "TASK-01", "Práctica de refuerzo", today + timedelta(days=5)),
            ):
                _insert(
                    session,
                    "assessments",
                    {
                        "id": aid,
                        "organization_id": org,
                        "institution_id": inst,
                        "section_id": section,
                        "course_offering_id": course,
                        "grading_period_id": gp,
                        "assessment_category_id": category,
                        "code": code,
                        "title": title,
                        "max_score": 10,
                        "due_on": due,
                        "status": "PUBLISHED",
                    },
                )
            codes = {}
            for code, label, semantic, present, absent, late in (
                ("P", "Presente", "PRESENT", True, False, False),
                ("A", "Ausente", "ABSENT", False, True, False),
                ("L", "Atraso", "LATE", False, False, True),
            ):
                codes[code] = uuid4()
                _insert(
                    session,
                    "attendance_codes",
                    {
                        "id": codes[code],
                        "organization_id": org,
                        "institution_id": inst,
                        "code": code,
                        "label": label,
                        "semantic": semantic,
                        "counts_as_present": present,
                        "counts_as_absent": absent,
                        "counts_as_late": late,
                        "status": "ACTIVE",
                        "created_at": now,
                    },
                )

            principals: dict[str, UUID] = {}
            profiles: dict[str, UUID] = {}
            role_ids: dict[str, UUID] = {}
            permission_ids = dict(session.exec(text("SELECT key,id FROM permissions")).all())
            staff_aliases = ("RECTOR", "COORDINATION", "TEACHER")
            for alias in ALIASES:
                person, user, membership, role = uuid4(), uuid4(), uuid4(), uuid4()
                first = {
                    "RECTOR": "Rector",
                    "COORDINATION": "Coordinador",
                    "TEACHER": "Docente",
                    "STUDENT": "Estudiante",
                    "GUARDIAN": "Representante",
                }[alias]
                last = "Demostración"
                _insert(
                    session,
                    "persons",
                    {
                        "id": person,
                        "organization_id": org,
                        "given_names": first,
                        "family_names": last,
                        "primary_email": f"{alias.lower()}@demo.education.invalid",
                        "created_at": now,
                    },
                )
                _insert(
                    session,
                    "user_accounts",
                    {
                        "id": user,
                        "person_id": person,
                        "login_email": f"{alias.lower()}@demo.education.invalid",
                        "password_hash": hash_password("disabled-demo-password"),
                        "is_active": True,
                        "created_at": now,
                    },
                )
                _insert(
                    session,
                    "memberships",
                    {
                        "id": membership,
                        "user_id": user,
                        "institution_id": inst,
                        "status": "ACTIVE",
                        "created_at": now,
                    },
                )
                _insert(
                    session,
                    "roles",
                    {"id": role, "institution_id": inst, "key": ROLE_KEYS[alias], "name": first},
                )
                _insert(session, "membership_roles", {"membership_id": membership, "role_id": role})
                for permission in PERMISSIONS[alias]:
                    _insert(
                        session,
                        "role_permissions",
                        {"role_id": role, "permission_id": permission_ids[permission]},
                    )
                principals[alias] = user
                role_ids[alias] = role
                if alias in staff_aliases:
                    profile = uuid4()
                    profiles[alias] = profile
                    _insert(
                        session,
                        "staff_profiles",
                        {
                            "id": profile,
                            "organization_id": org,
                            "institution_id": inst,
                            "person_id": person,
                            "staff_code": f"DEMO-{alias}",
                            "status": "ACTIVE",
                            "created_at": now,
                        },
                    )
                elif alias == "STUDENT":
                    profile = uuid4()
                    profiles[alias] = profile
                    _insert(
                        session,
                        "student_profiles",
                        {
                            "id": profile,
                            "organization_id": org,
                            "institution_id": inst,
                            "person_id": person,
                            "student_code": "DEMO-STUDENT-01",
                            "status": "ACTIVE",
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                else:
                    profile = uuid4()
                    profiles[alias] = profile
                    _insert(
                        session,
                        "guardian_profiles",
                        {
                            "id": profile,
                            "organization_id": org,
                            "institution_id": inst,
                            "person_id": person,
                            "guardian_code": "DEMO-GUARDIAN-01",
                            "status": "ACTIVE",
                            "created_at": now,
                        },
                    )
            student_profiles = []
            for index in range(10):
                person, profile = uuid4(), uuid4()
                focal = index == 0
                given = "Valentina" if focal else f"Estudiante{index + 1}"
                _insert(
                    session,
                    "persons",
                    {
                        "id": person,
                        "organization_id": org,
                        "given_names": given,
                        "family_names": "Demostración",
                        "primary_email": None,
                        "created_at": now,
                    },
                )
                if focal:
                    profile = profiles["STUDENT"]
                    session.exec(
                        text("UPDATE student_profiles SET person_id=:person WHERE id=:profile"),
                        params={"person": person, "profile": profile},
                    )
                    session.exec(
                        text("UPDATE user_accounts SET person_id=:person WHERE id=CAST(:user AS uuid)"),
                        params={"person": person, "user": str(principals["STUDENT"])},
                    )
                else:
                    _insert(
                        session,
                        "student_profiles",
                        {
                            "id": profile,
                            "organization_id": org,
                            "institution_id": inst,
                            "person_id": person,
                            "student_code": f"DEMO-STUDENT-{index + 1:02d}",
                            "status": "ACTIVE",
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                student_profiles.append(profile)
            _insert(
                session,
                "student_guardian_relationships",
                {
                    "id": uuid4(),
                    "organization_id": org,
                    "institution_id": inst,
                    "student_profile_id": profiles["STUDENT"],
                    "guardian_profile_id": profiles["GUARDIAN"],
                    "relationship_type": "REPRESENTATIVE",
                    "is_legal_guardian": True,
                    "is_primary_contact": True,
                    "lives_with_student": True,
                    "pickup_authorized": True,
                    "emergency_contact": True,
                    "created_at": now,
                },
            )
            _insert(
                session,
                "guardian_student_portal_access",
                {
                    "id": uuid4(),
                    "organization_id": org,
                    "institution_id": inst,
                    "guardian_profile_id": profiles["GUARDIAN"],
                    "student_profile_id": profiles["STUDENT"],
                    "access_level": "STANDARD",
                    "status": "ACTIVE",
                    "granted_at": now,
                },
            )
            assignments = {}
            for student in student_profiles:
                enrollment, assignment = uuid4(), uuid4()
                assignments[student] = assignment
                _insert(
                    session,
                    "enrollments",
                    {
                        "id": enrollment,
                        "organization_id": org,
                        "institution_id": inst,
                        "student_profile_id": student,
                        "academic_period_id": period,
                        "campus_id": campus,
                        "enrollment_number": f"DEMO-{str(student)[:8]}",
                        "status": "ACTIVE",
                        "enrolled_on": date(today.year, 8, 15),
                        "created_at": now,
                        "updated_at": now,
                    },
                )
                _insert(
                    session,
                    "student_section_assignments",
                    {
                        "id": assignment,
                        "organization_id": org,
                        "institution_id": inst,
                        "academic_period_id": period,
                        "enrollment_id": enrollment,
                        "section_id": section,
                        "status": "ACTIVE",
                        "assigned_on": date(today.year, 8, 15),
                        "created_at": now,
                    },
                )
            _insert(
                session,
                "teaching_assignments",
                {
                    "id": uuid4(),
                    "organization_id": org,
                    "institution_id": inst,
                    "course_offering_id": course,
                    "staff_profile_id": profiles["TEACHER"],
                    "assignment_role": "LEAD",
                    "starts_on": date(today.year, 8, 15),
                    "created_at": now,
                },
            )
            for n in range(5):
                session_id = uuid4()
                day = today - timedelta(days=10 - n * 2)
                _insert(
                    session,
                    "class_sessions",
                    {
                        "id": session_id,
                        "organization_id": org,
                        "institution_id": inst,
                        "course_offering_id": course,
                        "section_id": section,
                        "schedule_slot_id": slot,
                        "session_date": day,
                        "starts_at": time(8),
                        "ends_at": time(9),
                        "status": "CLOSED",
                        "created_at": now,
                    },
                )
                for student in student_profiles:
                    code = (
                        "A"
                        if student == profiles["STUDENT"] and n in (1, 3)
                        else "L"
                        if student == profiles["STUDENT"] and n == 4
                        else "P"
                    )
                    _insert(
                        session,
                        "attendance_records",
                        {
                            "id": uuid4(),
                            "organization_id": org,
                            "institution_id": inst,
                            "section_id": section,
                            "class_session_id": session_id,
                            "student_section_assignment_id": assignments[student],
                            "attendance_code_id": codes[code],
                            "minutes_late": 8 if code == "L" else 0,
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
            for student in student_profiles:
                score = 5.8 if student == profiles["STUDENT"] else 8.7
                _insert(
                    session,
                    "grade_entries",
                    {
                        "id": uuid4(),
                        "organization_id": org,
                        "institution_id": inst,
                        "section_id": section,
                        "assessment_id": assessment,
                        "student_section_assignment_id": assignments[student],
                        "score": score,
                        "status": "GRADED",
                        "feedback": "Revisar fundamentos y practicar con acompañamiento."
                        if student == profiles["STUDENT"]
                        else "Buen avance.",
                        "created_at": now,
                        "updated_at": now,
                    },
                )
                _insert(
                    session,
                    "grade_entries",
                    {
                        "id": uuid4(),
                        "organization_id": org,
                        "institution_id": inst,
                        "section_id": section,
                        "assessment_id": missing_assessment,
                        "student_section_assignment_id": assignments[student],
                        "score": None if student == profiles["STUDENT"] else 8.5,
                        "status": "MISSING" if student == profiles["STUDENT"] else "GRADED",
                        "feedback": None,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
            signal_actor = principals["COORDINATION"]
            _insert(
                session,
                "interventions",
                {
                    "id": uuid4(),
                    "organization_id": org,
                    "institution_id": inst,
                    "student_profile_id": profiles["STUDENT"],
                    "academic_period_id": period,
                    "section_id": section,
                    "intervention_type": "ACADEMIC_SUPPORT",
                    "severity": "MEDIUM",
                    "status": "IN_PROGRESS",
                    "sensitivity": "GENERAL",
                    "title": "Acompañamiento académico",
                    "reason": "Revisión humana de asistencia y progreso académico.",
                    "objective": "Acordar próximos pasos de acompañamiento.",
                    "origin_type": "HUMAN",
                    "opened_by_user_id": signal_actor,
                    "assigned_role_code": "ACADEMIC_COORDINATOR",
                    "assigned_user_id": signal_actor,
                    "opened_at": now - timedelta(days=4),
                    "target_at": now + timedelta(days=14),
                    "created_at": now,
                    "updated_at": now,
                },
            )
            # The official M22 mechanisms derive open signals and institutional
            # snapshots from this academic evidence; no snapshot is hand-made.
            session.flush()
            period_check = session.exec(
                text(
                    "SELECT count(*) FROM academic_periods WHERE id=CAST(:period AS uuid) AND institution_id=CAST(:inst AS uuid)"
                ),
                params={"period": str(period), "inst": str(inst)},
            ).one()[0]
            if period_check != 1:
                raise RuntimeError(
                    "Fixture academic period was not persisted before M22 generation"
                )
            for signal_type, severity, metric, threshold, summary in (
                (
                    "ATTENDANCE_RISK",
                    "HIGH",
                    40.0,
                    20.0,
                    "Ausencias repetidas en registros recientes.",
                ),
                (
                    "ACADEMIC_RISK",
                    "MEDIUM",
                    58.0,
                    70.0,
                    "Promedio académico por debajo del umbral institucional.",
                ),
                ("MISSING_WORK", "LOW", 1.0, 1.0, "Trabajo pendiente para revisión humana."),
            ):
                _insert(
                    session,
                    "intelligence_signals",
                    {
                        "id": uuid4(),
                        "organization_id": org,
                        "institution_id": inst,
                        "academic_period_id": period,
                        "section_id": section,
                        "student_profile_id": profiles["STUDENT"],
                        "signal_type": signal_type,
                        "severity": severity,
                        "metric_value": metric,
                        "threshold_value": threshold,
                        "summary": summary,
                        "status": "OPEN",
                        "detected_at": now - timedelta(days=2),
                        "last_seen_at": now,
                    },
                )
            project_institution_intelligence(
                session,
                organization_id=org,
                institution_id=inst,
                academic_period_id=period,
                snapshot_date=today,
                window_start=datetime.combine(today - timedelta(days=30), time.min, UTC),
                window_end=datetime.combine(today, time.max, UTC),
            )
            definition = uuid4()
            policy = uuid4()
            _insert(
                session,
                "agent_definitions",
                {
                    "id": definition,
                    "organization_id": org,
                    "institution_id": inst,
                    "agent_key": "mentor_institution_briefing",
                    "version": 1,
                    "status": "ENABLED",
                    "capability_keys_json": json.dumps(["mentor.institution.brief"]),
                    "tool_keys_json": json.dumps(["m22.intelligence_snapshot.inspect"]),
                    "max_autonomy_level": "L0",
                    "config_json": json.dumps(
                        {
                            "briefing_focus_values": ["OVERVIEW", "PRIORITIES", "FOLLOW_UPS"],
                            "deterministic_fallback_required": True,
                            "evidence_required": True,
                            "provider_required": False,
                            "request_type": "M26_INSTITUTION_BRIEFING",
                            "required_permissions": ["agents.use", "intelligence.read"],
                            "side_effect_class": "NONE",
                            "verifier_required": True,
                        }
                    ),
                    "created_by_user_id": principals["RECTOR"],
                    "created_at": now,
                },
            )
            _insert(
                session,
                "agent_policy_versions",
                {
                    "id": policy,
                    "organization_id": org,
                    "institution_id": inst,
                    "policy_key": "mentor_institution_briefing",
                    "version": 1,
                    "status": "ENABLED",
                    "max_autonomy_level": "L0",
                    "max_steps": 4,
                    "max_tool_calls": 1,
                    "provider_policy": "PROVIDER_OPTIONAL_WITH_DETERMINISTIC_FALLBACK",
                    "config_json": json.dumps(
                        {
                            "allowed_capabilities": ["mentor.institution.brief"],
                            "allowed_tools": ["m22.intelligence_snapshot.inspect"],
                            "budget_admission_required": True,
                            "deterministic_fallback_required": True,
                            "evidence_required": True,
                            "provider_router_required": True,
                            "required_permissions": ["agents.use", "intelligence.read"],
                            "side_effect_class": "NONE",
                            "verifier_required": True,
                        }
                    ),
                    "created_by_user_id": principals["RECTOR"],
                    "created_at": now,
                },
            )
            session.commit()
            state = {
                "organization_id": str(org),
                "institution_id": str(inst),
                "period_id": str(period),
                "section_id": str(section),
                "focal_student_id": str(profiles["STUDENT"]),
                "guardian_profile_id": str(profiles["GUARDIAN"]),
                "teacher_profile_id": str(profiles["TEACHER"]),
                "principals": {key: str(value) for key, value in principals.items()},
                "organization_name": ORG_NAME,
                "institution_name": INSTITUTION_NAME,
            }
            STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
            return state
    finally:
        engine.dispose()


def verify() -> dict[str, object]:
    _require_demo_mode()
    if not STATE_FILE.is_file():
        raise RuntimeError(f"State file not found: {STATE_FILE}")
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    engine = create_engine(settings.OWNER_DATABASE_URL)
    try:
        with Session(engine) as session:
            checks = {
                "organization": session.exec(
                    text(
                        "SELECT count(*) FROM organizations WHERE id=CAST(:id AS uuid) AND name=:name"
                    ),
                    params={"id": state["organization_id"], "name": ORG_NAME},
                ).one()[0]
                == 1,
                "institution": session.exec(
                    text(
                        "SELECT count(*) FROM institutions WHERE id=CAST(:id AS uuid) AND organization_id=CAST(:org AS uuid)"
                    ),
                    params={"id": state["institution_id"], "org": state["organization_id"]},
                ).one()[0]
                == 1,
                "principals": session.exec(
                    text(
                        "SELECT count(*) FROM user_accounts u JOIN persons p ON p.id=u.person_id WHERE u.id = ANY(CAST(:ids AS uuid[])) AND p.organization_id=CAST(:org AS uuid)"
                    ),
                    params={
                        "ids": list(state["principals"].values()),
                        "org": state["organization_id"],
                    },
                ).one()[0]
                == 5,
                "focal_enrollment": session.exec(
                    text(
                        "SELECT count(*) FROM enrollments WHERE student_profile_id=CAST(:student AS uuid) AND status='ACTIVE'"
                    ),
                    params={"student": state["focal_student_id"]},
                ).one()[0]
                == 1,
                "signals": session.exec(
                    text(
                        "SELECT count(*) FROM intelligence_signals WHERE organization_id=CAST(:org AS uuid) AND status='OPEN'"
                    ),
                    params={"org": state["organization_id"]},
                ).one()[0]
                >= 2,
                "snapshot": session.exec(
                    text(
                        "SELECT count(*) FROM institution_intelligence_daily WHERE institution_id=CAST(:inst AS uuid) AND snapshot_date=CURRENT_DATE"
                    ),
                    params={"inst": state["institution_id"]},
                ).one()[0]
                == 1,
            }
            if not all(checks.values()):
                raise RuntimeError(f"Fixture verification failed: {checks}")
            result = {"ok": True, "checks": checks, "state_file": str(STATE_FILE)}
            print(json.dumps(result, indent=2))
            return result
    finally:
        engine.dispose()


def cleanup() -> None:
    _require_demo_mode()
    if not STATE_FILE.is_file():
        raise RuntimeError(f"State file not found: {STATE_FILE}")
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    engine = create_engine(settings.OWNER_DATABASE_URL)
    try:
        with Session(engine) as session:
            _delete_org(session, UUID(state["organization_id"]))
            session.commit()
        STATE_FILE.unlink(missing_ok=True)
        print(json.dumps({"cleaned": True, "organization_id": state["organization_id"]}))
    finally:
        engine.dispose()


def smoke() -> dict[str, object]:
    _require_demo_mode()
    if not STATE_FILE.is_file():
        raise RuntimeError(f"State file not found: {STATE_FILE}")
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    settings.APP_ENV = "staging"
    settings.EDUCATION_OS_DEMO_SYNTHETIC_ONLY = True
    settings.PUBLIC_BASE_URL = "https://demo.example.test"
    settings.EDUCATION_OS_DEMO_ACCESS_CODE = os.environ.get(
        "EDUCATION_OS_DEMO_ACCESS_CODE", "local-demo-access-code-not-for-deployment"
    )
    settings.EDUCATION_OS_DEMO_ORGANIZATION_ID = state["organization_id"]
    settings.EDUCATION_OS_DEMO_INSTITUTION_ID = state["institution_id"]
    settings.EDUCATION_OS_DEMO_PRINCIPALS = state["principals"]
    settings.EDUCATION_OS_DEMO_MODE = True
    demo.store = demo.SessionStore()
    from fastapi.testclient import TestClient

    from app.main import app

    statuses: dict[str, object] = {}
    with TestClient(
        app,
        base_url=settings.PUBLIC_BASE_URL,
        headers={"Origin": settings.PUBLIC_BASE_URL},
    ) as client:
        entrance = client.post(
            "/api/demo/entrance",
            json={"code": settings.EDUCATION_OS_DEMO_ACCESS_CODE},
        )
        if entrance.status_code != 200:
            raise RuntimeError(f"Demo entrance failed: {entrance.status_code}")
        checks = {
            "RECTOR": ("/api/v1/ui/bootstrap", "/api/v1/agents/mentor_institution_briefing/runs"),
            "COORDINATION": ("/api/v1/coordination/summary", "/api/v1/intelligence/signals"),
            "TEACHER": ("/api/v1/teacher/summary", "/api/v1/teacher/classes"),
            "STUDENT": ("/api/v1/student/me", "/api/v1/student/progress"),
            "GUARDIAN": ("/api/v1/guardian/students", "/api/v1/guardian/me"),
        }
        for alias, (primary_path, secondary_path) in checks.items():
            selected = client.post("/api/demo/session", json={"alias": alias})
            if selected.status_code != 200:
                raise RuntimeError(f"{alias} session failed: {selected.status_code}")
            primary = client.get(primary_path)
            statuses[f"{alias}_primary"] = primary.status_code
            if primary.status_code != 200:
                raise RuntimeError(f"{alias} primary failed: {primary.status_code} {primary.text}")
            if alias == "RECTOR":
                for focus in ("OVERVIEW", "PRIORITIES", "FOLLOW_UPS"):
                    response = client.post(secondary_path, json={"briefing_focus": focus})
                    statuses[f"RECTOR_{focus}"] = response.status_code
                    if response.status_code not in (200, 201) or "Valentina" in response.text:
                        raise RuntimeError(
                            f"Rector Mentor failed/privacy leak: {response.status_code}"
                        )
            else:
                secondary = client.get(secondary_path)
                statuses[f"{alias}_secondary"] = secondary.status_code
        client.post("/api/demo/session", json={"alias": "STUDENT"})
        statuses["student_intelligence_denied"] = client.get(
            "/api/v1/intelligence/signals"
        ).status_code
        client.post("/api/demo/session", json={"alias": "GUARDIAN"})
        statuses["guardian_unrelated_child_denied"] = client.get(
            f"/api/v1/guardian/students/{uuid4()}/summary"
        ).status_code
    result = {"ok": True, "statuses": statuses}
    print(json.dumps(result, indent=2))
    return statuses


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("provision", "verify", "smoke", "cleanup"))
    args = parser.parse_args()
    result = (
        provision()
        if args.command == "provision"
        else verify()
        if args.command == "verify"
        else smoke()
        if args.command == "smoke"
        else cleanup()
    )
    if args.command == "provision":
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
