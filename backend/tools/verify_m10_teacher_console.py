from __future__ import annotations

import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.security import create_access_token, hash_password  # noqa: E402

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)


def bootstrap_teacher_context() -> dict:
    suffix = uuid4().hex[:8].upper()

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                co.id,
                co.section_id,
                co.academic_period_id,
                co.organization_id,
                co.institution_id,
                ssa.id,
                e.student_profile_id,
                candidate.signal_type
            FROM course_offerings co
            JOIN student_section_assignments ssa
              ON ssa.section_id = co.section_id
             AND ssa.status = 'ACTIVE'
            JOIN enrollments e
              ON e.id = ssa.enrollment_id
             AND e.status = 'ACTIVE'
            JOIN student_profiles sp
              ON sp.id = e.student_profile_id
             AND sp.status = 'ACTIVE'
            CROSS JOIN LATERAL (
                SELECT allowed.signal_type
                FROM (
                    VALUES
                        ('ATTENDANCE_RISK'),
                        ('REPEATED_LATE'),
                        ('ACADEMIC_RISK'),
                        ('MISSING_WORK')
                ) AS allowed(signal_type)
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM intelligence_signals sig
                    WHERE sig.student_profile_id = e.student_profile_id
                      AND sig.academic_period_id = co.academic_period_id
                      AND sig.signal_type = allowed.signal_type
                      AND sig.status = 'OPEN'
                )
                ORDER BY allowed.signal_type
                LIMIT 1
            ) AS candidate
            WHERE co.status = 'ACTIVE'
            ORDER BY co.created_at
            LIMIT 1
            """
        )
        offering = cur.fetchone()
        assert offering is not None, (
            "active course offering with roster and one available "
            "valid OPEN signal_type required"
        )
        (
            course_offering_id,
            section_id,
            academic_period_id,
            organization_id,
            institution_id,
            student_section_assignment_id,
            student_profile_id,
            signal_type,
        ) = offering

        cur.execute(
            """
            SELECT id
            FROM roles
            WHERE institution_id = %s
              AND key = 'TEACHER'
            """,
            (institution_id,),
        )
        teacher_role = cur.fetchone()
        assert teacher_role is not None, "TEACHER role missing after M10 migration"

        person_id = uuid4()
        user_id = uuid4()
        membership_id = uuid4()
        staff_profile_id = uuid4()
        teacher_login = f"m10-teacher-{suffix.lower()}@education-os.internal"

        cur.execute(
            """
            INSERT INTO persons (
                id, organization_id, given_names, family_names,
                primary_email, created_at
            )
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (
                person_id,
                organization_id,
                "Docente",
                f"Automatico M10 {suffix}",
                f"m10-teacher-{suffix.lower()}@example.invalid",
            ),
        )
        cur.execute(
            """
            INSERT INTO user_accounts (
                id, person_id, login_email, password_hash, is_active, created_at
            )
            VALUES (%s, %s, %s, %s, true, NOW())
            """,
            (
                user_id,
                person_id,
                teacher_login,
                hash_password("M10-Teacher-Temporary-2026!"),
            ),
        )
        cur.execute(
            """
            INSERT INTO memberships (
                id, user_id, institution_id, status, created_at
            )
            VALUES (%s, %s, %s, 'ACTIVE', NOW())
            """,
            (membership_id, user_id, institution_id),
        )
        cur.execute(
            """
            INSERT INTO staff_profiles (
                id, organization_id, institution_id, person_id,
                staff_code, status, created_at
            )
            VALUES (%s, %s, %s, %s, %s, 'ACTIVE', NOW())
            """,
            (
                staff_profile_id,
                organization_id,
                institution_id,
                person_id,
                f"M10-TEA-{suffix}",
            ),
        )
        cur.execute(
            """
            INSERT INTO membership_roles (membership_id, role_id)
            VALUES (%s, %s)
            """,
            (membership_id, teacher_role[0]),
        )
        cur.execute(
            """
            INSERT INTO teaching_assignments (
                id, organization_id, institution_id, course_offering_id,
                staff_profile_id, assignment_role, starts_on, ends_on, created_at
            )
            VALUES (%s, %s, %s, %s, %s, 'LEAD', NULL, NULL, NOW())
            """,
            (
                uuid4(),
                organization_id,
                institution_id,
                course_offering_id,
                staff_profile_id,
            ),
        )

        non_person_id = uuid4()
        non_user_id = uuid4()
        non_membership_id = uuid4()
        non_staff_id = uuid4()
        cur.execute(
            """
            INSERT INTO persons (
                id, organization_id, given_names, family_names,
                primary_email, created_at
            )
            VALUES (%s, %s, 'M10', 'Non Teacher', %s, NOW())
            """,
            (
                non_person_id,
                organization_id,
                f"m10-nonteacher-{suffix.lower()}@example.invalid",
            ),
        )
        cur.execute(
            """
            INSERT INTO user_accounts (
                id, person_id, login_email, password_hash, is_active, created_at
            )
            VALUES (%s, %s, %s, %s, true, NOW())
            """,
            (
                non_user_id,
                non_person_id,
                f"m10-nonteacher-{suffix.lower()}@education-os.internal",
                hash_password("M10-NonTeacher-Temporary-2026!"),
            ),
        )
        cur.execute(
            """
            INSERT INTO memberships (
                id, user_id, institution_id, status, created_at
            )
            VALUES (%s, %s, %s, 'ACTIVE', NOW())
            """,
            (non_membership_id, non_user_id, institution_id),
        )
        cur.execute(
            """
            INSERT INTO staff_profiles (
                id, organization_id, institution_id, person_id,
                staff_code, status, created_at
            )
            VALUES (%s, %s, %s, %s, %s, 'ACTIVE', NOW())
            """,
            (
                non_staff_id,
                organization_id,
                institution_id,
                non_person_id,
                f"M10-NON-{suffix}",
            ),
        )

        cur.execute(
            """
            SELECT id
            FROM grading_periods
            WHERE academic_period_id = %s
            ORDER BY sequence
            LIMIT 1
            """,
            (academic_period_id,),
        )
        grading_period = cur.fetchone()
        if grading_period is None:
            cur.execute(
                """
                SELECT starts_on, ends_on
                FROM academic_periods
                WHERE id = %s
                """,
                (academic_period_id,),
            )
            period_dates = cur.fetchone()
            assert period_dates is not None
            grading_period_id = uuid4()
            cur.execute(
                """
                INSERT INTO grading_periods (
                    id, organization_id, institution_id, academic_period_id,
                    code, name, starts_on, ends_on, sequence, status, created_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, 99, 'ACTIVE', NOW()
                )
                """,
                (
                    grading_period_id,
                    organization_id,
                    institution_id,
                    academic_period_id,
                    f"M10GP-{suffix}",
                    f"M10 Grading Period {suffix}",
                    period_dates[0],
                    period_dates[1],
                ),
            )
        else:
            grading_period_id = grading_period[0]

        cur.execute(
            """
            SELECT id
            FROM attendance_codes
            WHERE institution_id = %s
              AND status = 'ACTIVE'
            ORDER BY code
            LIMIT 1
            """,
            (institution_id,),
        )
        code = cur.fetchone()
        if code is None:
            attendance_code_id = uuid4()
            cur.execute(
                """
                INSERT INTO attendance_codes (
                    id, organization_id, institution_id, code, label, semantic,
                    counts_as_present, counts_as_absent, counts_as_late,
                    status, created_at
                )
                VALUES (
                    %s, %s, %s, %s, 'Presente M10', 'PRESENT',
                    true, false, false, 'ACTIVE', NOW()
                )
                """,
                (
                    attendance_code_id,
                    organization_id,
                    institution_id,
                    f"P{suffix[:6]}",
                ),
            )
        else:
            attendance_code_id = code[0]

        signal_id = uuid4()
        rule_id = uuid4()
        case_id = uuid4()
        task_id = uuid4()

        cur.execute(
            """
            INSERT INTO intelligence_signals (
                id, organization_id, institution_id, academic_period_id,
                section_id, student_profile_id, signal_type, severity,
                metric_value, threshold_value, summary, status,
                detected_at, last_seen_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, 'MEDIUM',
                1.0, 1.0, %s, 'OPEN', NOW(), NOW()
            )
            """,
            (
                signal_id,
                organization_id,
                institution_id,
                academic_period_id,
                section_id,
                student_profile_id,
                signal_type,
                f"M10 teacher scoped alert {suffix}",
            ),
        )
        cur.execute(
            """
            INSERT INTO automation_rules (
                id, organization_id, institution_id, code, name, signal_type,
                minimum_severity, assignee_role_code, task_title,
                due_in_hours, escalate_after_hours, is_enabled, created_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, 'MEDIUM', 'TEACHER', %s,
                24, 48, true, NOW()
            )
            """,
            (
                rule_id,
                organization_id,
                institution_id,
                f"M10_RULE_{suffix}",
                f"M10 Teacher verifier rule {suffix}",
                signal_type,
                f"M10 follow-up {suffix}",
            ),
        )
        cur.execute(
            """
            INSERT INTO automation_cases (
                id, organization_id, institution_id, intelligence_signal_id,
                automation_rule_id, student_profile_id, section_id,
                status, opened_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, 'OPEN', NOW()
            )
            """,
            (
                case_id,
                organization_id,
                institution_id,
                signal_id,
                rule_id,
                student_profile_id,
                section_id,
            ),
        )
        cur.execute(
            """
            INSERT INTO automation_tasks (
                id, organization_id, institution_id, automation_case_id,
                assigned_role_code, task_type, title, description, status,
                due_at, escalate_at, created_at
            )
            VALUES (
                %s, %s, %s, %s, 'TEACHER', 'REVIEW', %s, %s, 'OPEN',
                %s, %s, NOW()
            )
            """,
            (
                task_id,
                organization_id,
                institution_id,
                case_id,
                f"M10 teacher task {suffix}",
                f"M10 scoped task description {suffix}",
                datetime.now(UTC) + timedelta(hours=24),
                datetime.now(UTC) + timedelta(hours=48),
            ),
        )

        conn.commit()

    return {
        "suffix": suffix,
        "organization_id": organization_id,
        "institution_id": institution_id,
        "user_id": user_id,
        "non_user_id": non_user_id,
        "teacher_login": teacher_login,
        "course_offering_id": course_offering_id,
        "section_id": section_id,
        "academic_period_id": academic_period_id,
        "student_section_assignment_id": student_section_assignment_id,
        "student_profile_id": student_profile_id,
        "grading_period_id": grading_period_id,
        "attendance_code_id": attendance_code_id,
        "task_id": task_id,
        "signal_id": signal_id,
    }


def main() -> None:
    ctx = bootstrap_teacher_context()
    token = create_access_token(
        user_id=UUID(str(ctx["user_id"])),
        organization_id=UUID(str(ctx["organization_id"])),
        institution_id=UUID(str(ctx["institution_id"])),
    )
    non_token = create_access_token(
        user_id=UUID(str(ctx["non_user_id"])),
        organization_id=UUID(str(ctx["organization_id"])),
        institution_id=UUID(str(ctx["institution_id"])),
    )

    from app.main import app

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    non_headers = {"Authorization": f"Bearer {non_token}"}

    dashboard = client.get("/api/v1/teacher/dashboard")
    assert dashboard.status_code == 200
    assert "Teacher Console" in dashboard.text
    assert "Calificaciones" in dashboard.text
    print("M10 Teacher dashboard HTML: PASSED")

    for path in (
        "/api/v1/teacher/summary",
        "/api/v1/teacher/classes",
        "/api/v1/teacher/alerts",
        "/api/v1/teacher/attendance/codes",
        "/api/v1/teacher/tasks",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 200, (
            f"{path}: {response.status_code} {response.text}"
        )
    print("M10 protected read surface: PASSED")

    classes = client.get("/api/v1/teacher/classes", headers=headers).json()
    assert len(classes) == 1
    assert classes[0]["course_offering_id"] == str(ctx["course_offering_id"])

    roster = client.get(
        f"/api/v1/teacher/classes/{ctx['course_offering_id']}/roster",
        headers=headers,
    )
    assert roster.status_code == 200, roster.text
    roster_body = roster.json()
    assert any(
        row["student_section_assignment_id"]
        == str(ctx["student_section_assignment_id"])
        for row in roster_body
    )
    print("Teaching-assignment class / roster scope: PASSED")

    denied_paths = (
        "/api/v1/students",
        "/api/v1/academics/sections",
        "/api/v1/attendance/codes",
        "/api/v1/grades/assessments",
        "/api/v1/automation/cases",
        "/api/v1/operations/security-baseline",
        "/api/v1/intelligence/rector/overview",
        "/api/v1/admin/summary",
        "/api/v1/coordination/summary",
    )
    for path in denied_paths:
        response = client.get(path, headers=headers)
        assert response.status_code == 403, (
            f"teacher legacy/elevated boundary {path}: "
            f"{response.status_code} {response.text}"
        )

    family_admin = client.post(
        "/api/v1/family-admin/access/bootstrap",
        headers=headers,
    )
    assert family_admin.status_code == 403, family_admin.text
    print("Teacher-only broad/elevated API boundary: PASSED")

    non_teacher = client.get(
        "/api/v1/teacher/summary",
        headers=non_headers,
    )
    assert non_teacher.status_code == 403, non_teacher.text
    print("Non-teacher negative Teacher Console boundary: PASSED")

    minute = int(ctx["suffix"][:2], 16) % 40
    starts_at = f"22:{minute:02d}:00"
    ends_at = f"22:{minute + 15:02d}:00"
    session_create = client.post(
        f"/api/v1/teacher/classes/{ctx['course_offering_id']}/sessions",
        headers=headers,
        json={
            "session_date": str(date.today()),
            "starts_at": starts_at,
            "ends_at": ends_at,
            "schedule_slot_id": None,
        },
    )
    assert session_create.status_code == 201, session_create.text
    class_session_id = session_create.json()["id"]

    attendance = client.put(
        f"/api/v1/teacher/sessions/{class_session_id}/attendance",
        headers=headers,
        json={
            "student_section_assignment_id": str(
                ctx["student_section_assignment_id"]
            ),
            "attendance_code_id": str(ctx["attendance_code_id"]),
            "minutes_late": 0,
            "note": "M10 verifier attendance.",
        },
    )
    assert attendance.status_code == 200, attendance.text

    attendance_rows = client.get(
        f"/api/v1/teacher/sessions/{class_session_id}/attendance",
        headers=headers,
    )
    assert attendance_rows.status_code == 200
    assert any(
        row["attendance_record_id"] is not None
        and row["student_section_assignment_id"]
        == str(ctx["student_section_assignment_id"])
        for row in attendance_rows.json()
    )
    print("Teacher attendance lifecycle: PASSED")

    category = client.post(
        f"/api/v1/teacher/classes/{ctx['course_offering_id']}/categories",
        headers=headers,
        json={
            "grading_period_id": str(ctx["grading_period_id"]),
            "code": f"M10C{ctx['suffix'][:6]}",
            "name": f"M10 Category {ctx['suffix']}",
            "weight_percent": 100.0,
        },
    )
    assert category.status_code == 201, category.text
    category_id = category.json()["id"]

    assessment = client.post(
        f"/api/v1/teacher/classes/{ctx['course_offering_id']}/assessments",
        headers=headers,
        json={
            "grading_period_id": str(ctx["grading_period_id"]),
            "assessment_category_id": category_id,
            "code": f"M10A{ctx['suffix'][:6]}",
            "title": f"M10 Assessment {ctx['suffix']}",
            "max_score": 10.0,
            "due_on": str(date.today()),
        },
    )
    assert assessment.status_code == 201, assessment.text
    assessment_id = assessment.json()["id"]

    grade = client.put(
        f"/api/v1/teacher/assessments/{assessment_id}/grades",
        headers=headers,
        json={
            "student_section_assignment_id": str(
                ctx["student_section_assignment_id"]
            ),
            "score": 8.5,
            "status": "GRADED",
            "feedback": "M10 verifier feedback.",
        },
    )
    assert grade.status_code == 200, grade.text

    grade_rows = client.get(
        f"/api/v1/teacher/assessments/{assessment_id}/grades",
        headers=headers,
    )
    assert grade_rows.status_code == 200
    assert any(
        row["score"] == 8.5
        and row["status"] == "GRADED"
        for row in grade_rows.json()
    )
    print("Teacher assessment / grading lifecycle: PASSED")

    alerts = client.get("/api/v1/teacher/alerts", headers=headers)
    assert alerts.status_code == 200
    assert any(
        row["signal_id"] == str(ctx["signal_id"])
        for row in alerts.json()
    )

    tasks = client.get("/api/v1/teacher/tasks", headers=headers)
    assert tasks.status_code == 200
    assert any(row["id"] == str(ctx["task_id"]) for row in tasks.json())

    ack = client.post(
        f"/api/v1/teacher/tasks/{ctx['task_id']}/acknowledge",
        headers=headers,
    )
    assert ack.status_code == 200, ack.text
    assert ack.json()["status"] == "ACKNOWLEDGED"

    complete = client.post(
        f"/api/v1/teacher/tasks/{ctx['task_id']}/complete",
        headers=headers,
        json={
            "completion_note": (
                "M10 verifier: teacher follow-up completed in clone."
            )
        },
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "COMPLETED"
    print("Teacher alert / task lifecycle: PASSED")

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT key
            FROM permissions
            WHERE key = ANY(%s)
            ORDER BY key
            """,
            (
                [
                    "teacher.attendance.manage",
                    "teacher.classes.view",
                    "teacher.console.access",
                    "teacher.grades.manage",
                    "teacher.tasks.manage",
                ],
            ),
        )
        permission_keys = [row[0] for row in cur.fetchall()]
        assert permission_keys == [
            "teacher.attendance.manage",
            "teacher.classes.view",
            "teacher.console.access",
            "teacher.grades.manage",
            "teacher.tasks.manage",
        ]

        cur.execute(
            """
            SELECT key
            FROM roles
            WHERE institution_id = %s
              AND key = 'TEACHER'
            """,
            (ctx["institution_id"],),
        )
        assert cur.fetchone() == ("TEACHER",)

        expected_audits = (
            "TEACHER_SESSION_CREATED",
            "TEACHER_ATTENDANCE_MARKED",
            "TEACHER_CATEGORY_CREATED",
            "TEACHER_ASSESSMENT_CREATED",
            "TEACHER_GRADE_RECORDED",
            "TEACHER_TASK_ACKNOWLEDGED",
            "TEACHER_TASK_COMPLETED",
        )
        cur.execute(
            """
            SELECT action, COUNT(*)
            FROM audit_logs
            WHERE institution_id = %s
              AND action = ANY(%s)
            GROUP BY action
            """,
            (ctx["institution_id"], list(expected_audits)),
        )
        counts = dict(cur.fetchall())
        for action in expected_audits:
            assert int(counts.get(action, 0)) >= 1, action

    print("M10 role / permission / audit catalog: PASSED")
    print(f"Teacher verifier login={ctx['teacher_login']}")
    print("M10 Teacher Console verifier: PASSED")


if __name__ == "__main__":
    main()
