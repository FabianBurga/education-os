"""Rollback-contained synthetic institutional journey for M28-8."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_session
from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import engine as app_engine
from app.db.tenant_context import TenantContext, apply_tenant_context
from app.main import app
from app.modules.accountability.ledger_service import (
    assign_case_owner,
    record_case_decision,
    record_case_review,
)
from app.modules.accountability.obligation_service import (
    complete_accountability_obligation,
    create_accountability_obligation,
)
from app.modules.accountability.projection import (
    CaseProjectionInput,
    CaseSourceInput,
    project_case,
)
from app.modules.events.projection_service import ingest_outbox_events
from app.modules.families.models import StaffProfile
from app.modules.identity.models import (
    Membership,
    MembershipRole,
    Person,
    Role,
    RolePermission,
    UserAccount,
)
from app.modules.intelligence.service import refresh_signals
from app.modules.student_timeline.projector import project_student_timeline
from app.modules.teacher_console.schemas import TeacherAttendanceMark
from app.modules.teacher_offline.schemas import (
    TeacherOfflineAttendanceBase,
    TeacherOfflineAttendanceOperation,
    TeacherOfflineSyncBatch,
)
from app.modules.tenancy.models import Campus, Institution, Organization

PERMISSIONS = {
    "manager": {
        "students.read", "students.manage", "enrollments.read",
        "enrollments.manage", "admin.people.manage", "academics.read",
        "academics.manage", "academics.assign", "attendance.read",
        "attendance.manage", "attendance.correct", "intelligence.read",
        "intelligence.manage", "accountability.view", "accountability.manage", "accountability.review",
        "accountability.decide", "accountability.ownership.manage",
        "accountability.obligation.create", "accountability.obligation.complete",
        "accountability.obligation.waive", "integrations.run",
    },
    "coordinator": {
        "students.read", "enrollments.read", "academics.read",
        "intelligence.read", "intelligence.manage", "accountability.view",
        "accountability.manage", "accountability.review", "accountability.decide",
        "accountability.ownership.manage", "accountability.obligation.create",
        "accountability.obligation.complete",
    },
    "teacher": {
        "teacher.classes.view", "teacher.attendance.manage", "teacher.grades.manage",
    },
    "system_admin": {"admin.console.access", "student_timeline.read"},
    "unauthorized": set(),
}


def _headers(actor: dict[str, UUID], organization_id: UUID, institution_id: UUID):
    token = create_access_token(
        user_id=actor["user_id"],
        organization_id=organization_id,
        institution_id=institution_id,
    )
    return {"Authorization": f"Bearer {token}"}


def _assert(response, status: int):
    assert response.status_code == status, f"{response.status_code}: {response.text}"
    return response.json() if response.content else None


@contextmanager
def _synthetic_institution():
    assert settings.OWNER_DATABASE_URL
    owner_engine = create_engine(settings.OWNER_DATABASE_URL, pool_pre_ping=True)
    owner = Session(owner_engine)
    organization_id, institution_id, campus_id = uuid4(), uuid4(), uuid4()
    actors: dict[str, dict[str, UUID]] = {}
    actor_person_ids: list[UUID] = []
    student_person_ids: list[UUID] = []
    role_ids: dict[str, UUID] = {}
    roles_created: list[UUID] = []
    app_connection = None
    app_transaction = None
    pilot_session = None

    try:
        owner.add(Organization(
            id=organization_id,
            name=f"M28-8 SYNTHETIC ORGANIZATION {organization_id.hex[:10]}",
            status="ACTIVE",
        ))
        owner.flush()
        owner.add(Institution(
            id=institution_id,
            organization_id=organization_id,
            name=f"M28-8 SYNTHETIC SCHOOL {institution_id.hex[:10]}",
            type="PRIVATE",
            status="ACTIVE",
        ))
        owner.flush()
        owner.add(Campus(id=campus_id, institution_id=institution_id, name="Synthetic campus"))

        all_keys = set().union(*PERMISSIONS.values())
        permission_rows = owner.exec(
            text("SELECT id, key FROM permissions WHERE key=ANY(CAST(:keys AS text[]))"),
            params={"keys": sorted(all_keys)},
        ).all()
        permission_ids = {key: permission_id for permission_id, key in permission_rows}
        assert all_keys <= permission_ids.keys(), f"missing permission seeds: {all_keys - permission_ids.keys()}"

        role_for_actor = {
            "manager": "RECTOR",
            "coordinator": "ACADEMIC_COORDINATOR",
            "teacher_a": "TEACHER",
            "teacher_b": "TEACHER",
            "system_admin": "SYSTEM_ADMIN",
            "unauthorized": "PILOT_UNAUTHORIZED",
        }
        for role_key in set(role_for_actor.values()):
            role = Role(
                institution_id=institution_id,
                key=role_key,
                name=f"M28-8 synthetic {role_key}",
            )
            owner.add(role)
            owner.flush()
            role_ids[role_key] = role.id
            roles_created.append(role.id)
        for actor_key, role_key in role_for_actor.items():
            nonce = uuid4().hex
            person = Person(
                organization_id=organization_id,
                given_names="Synthetic",
                family_names=f"M28-8 {actor_key}",
            )
            owner.add(person)
            owner.flush()
            actor_person_ids.append(person.id)
            user = UserAccount(
                person_id=person.id,
                login_email=f"m28-8-{actor_key}-{nonce}@test.invalid",
                password_hash="synthetic-pilot-not-a-credential",
                is_active=True,
            )
            owner.add(user)
            owner.flush()
            membership = Membership(user_id=user.id, institution_id=institution_id, status="ACTIVE")
            owner.add(membership)
            staff = StaffProfile(
                organization_id=organization_id,
                institution_id=institution_id,
                person_id=person.id,
                staff_code=f"M28-8-{actor_key}-{nonce[:8]}",
            )
            owner.add(staff)
            owner.flush()
            owner.add(MembershipRole(membership_id=membership.id, role_id=role_ids[role_key]))
            actors[actor_key] = {
                "user_id": user.id,
                "person_id": person.id,
                "membership_id": membership.id,
                "staff_id": staff.id,
                "role_id": role_ids[role_key],
            }

        # The two teachers share the established TEACHER role; add its effective
        # permissions once. Rector/coordinator/system-admin remain distinct.
        for role_key, permission_group in (
            ("RECTOR", "manager"),
            ("ACADEMIC_COORDINATOR", "coordinator"),
            ("TEACHER", "teacher"),
            ("SYSTEM_ADMIN", "system_admin"),
        ):
            for key in PERMISSIONS[permission_group]:
                owner.add(RolePermission(role_id=role_ids[role_key], permission_id=permission_ids[key]))

        # Ten fully synthetic people are bootstrapped; profile and every academic
        # record are created through the normal application APIs below.
        for index in range(10):
            person = Person(
                organization_id=organization_id,
                given_names=f"Synthetic Student {index + 1:02d}",
                family_names="M28-8 Pilot",
            )
            owner.add(person)
            owner.flush()
            student_person_ids.append(person.id)
        owner.exec(
            text("INSERT INTO institution_capabilities(institution_id, capability_key, enabled) VALUES (:id,'teacher.offline_pwa',true)"),
            params={"id": institution_id},
        )
        owner.commit()

        app_connection = app_engine.connect()
        app_transaction = app_connection.begin()
        pilot_session = Session(bind=app_connection, join_transaction_mode="create_savepoint")

        def override_session():
            yield pilot_session

        app.dependency_overrides[get_session] = override_session
        yield {
            "owner": owner,
            "client": TestClient(app, raise_server_exceptions=False),
            "session": pilot_session,
            "organization_id": organization_id,
            "institution_id": institution_id,
            "campus_id": campus_id,
            "actors": actors,
            "student_person_ids": student_person_ids,
        }
    finally:
        app.dependency_overrides.pop(get_session, None)
        if pilot_session is not None:
            pilot_session.close()
        if app_transaction is not None:
            app_transaction.rollback()
        if app_connection is not None:
            app_connection.close()
        owner.rollback()
        owner.exec(text("DELETE FROM institution_capabilities WHERE institution_id=:id"), params={"id": institution_id})
        for role_id in roles_created:
            owner.exec(text("DELETE FROM membership_roles WHERE role_id=:id"), params={"id": role_id})
            owner.exec(text("DELETE FROM role_permissions WHERE role_id=:id"), params={"id": role_id})
        for actor in actors.values():
            owner.exec(text("DELETE FROM memberships WHERE id=:id"), params={"id": actor["membership_id"]})
            owner.exec(text("DELETE FROM staff_profiles WHERE id=:id"), params={"id": actor["staff_id"]})
            owner.exec(text("DELETE FROM user_accounts WHERE id=:id"), params={"id": actor["user_id"]})
        if roles_created:
            owner.exec(text("DELETE FROM roles WHERE id=ANY(CAST(:ids AS uuid[]))"), params={"ids": roles_created})
        person_ids = actor_person_ids + student_person_ids
        if person_ids:
            owner.exec(text("DELETE FROM persons WHERE id=ANY(CAST(:ids AS uuid[]))"), params={"ids": person_ids})
        owner.exec(text("DELETE FROM campuses WHERE id=:id"), params={"id": campus_id})
        owner.exec(text("DELETE FROM institutions WHERE id=:id"), params={"id": institution_id})
        owner.exec(text("DELETE FROM organizations WHERE id=:id"), params={"id": organization_id})
        owner.commit()
        owner.close()
        owner_engine.dispose()


def test_m28_synthetic_institution_operational_journey():
    today = date.today()
    yesterday = today - timedelta(days=1)
    with _synthetic_institution() as pilot:
        client = pilot["client"]
        org, institution, campus = (
            pilot["organization_id"], pilot["institution_id"], pilot["campus_id"]
        )
        actors = pilot["actors"]
        headers = {
            key: _headers(actors[key], org, institution)
            for key in actors
        }
        manager = headers["manager"]
        teacher_a, teacher_b = headers["teacher_a"], headers["teacher_b"]
        system_admin, unauthorized = headers["system_admin"], headers["unauthorized"]
        assert client.get("/api/v1/students/records", headers=unauthorized).status_code == 403
        assert client.get("/api/v1/academics/levels", headers=teacher_a).status_code == 403
        assert client.get("/api/v1/academics/levels", headers=system_admin).status_code == 403
        assert client.get("/api/v1/attendance/codes", headers=teacher_a).status_code == 403

        students: list[dict[str, str]] = []
        for index, person_id in enumerate(pilot["student_person_ids"], start=1):
            created = _assert(client.post("/api/v1/students", headers=manager, json={
                "person_id": str(person_id), "student_code": f"M28-8-{index:02d}",
            }), 201)
            assert set(created) == {"id", "display_name", "student_code", "status", "updated_at"}
            students.append(created)
        assert len(students) == 10
        student0 = client.get(f"/api/v1/students/{students[0]['id']}", headers=manager)
        _assert(student0, 200)
        _assert(client.patch(
            f"/api/v1/students/{students[0]['id']}", headers=manager,
            json={"student_code": "M28-8-01-U", "expected_updated_at": student0.json()["updated_at"]},
        ), 200)
        stale = client.patch(
            f"/api/v1/students/{students[0]['id']}", headers=manager,
            json={"student_code": "M28-8-01-STALE", "expected_updated_at": student0.json()["updated_at"]},
        )
        assert stale.status_code == 409
        assert client.get(f"/api/v1/students/{students[0]['id']}", headers=unauthorized).status_code == 403

        period = _assert(client.post("/api/v1/academic-periods", headers=manager, json={
            "code": f"M28-8-{uuid4().hex[:10]}", "name": "Synthetic operational cycle",
            "starts_on": (today - timedelta(days=30)).isoformat(),
            "ends_on": (today + timedelta(days=90)).isoformat(),
        }), 201)
        period_id = period["id"]
        wrong_tenant_headers = _headers(
            actors["manager"], uuid4(), uuid4(),
        )
        wrong_tenant_read = client.get(
            f"/api/v1/students/{students[0]['id']}", headers=wrong_tenant_headers,
        )
        assert wrong_tenant_read.status_code in {403, 404}
        foreign_student_enrollment = client.post("/api/v1/enrollments", headers=manager, json={
            "student_profile_id": str(uuid4()), "academic_period_id": period_id,
            "campus_id": str(campus), "enrollment_number": f"M28-8-FOREIGN-{uuid4().hex[:6]}",
            "status": "PENDING", "enrolled_on": None,
        })
        assert foreign_student_enrollment.status_code == 404
        _assert(client.patch(f"/api/v1/academic-periods/{period_id}/status", headers=manager, json={
            "expected_status": "PLANNED", "status": "ACTIVE",
        }), 200)
        levels, grades, sections = [], [], []
        for index in (1, 2):
            level = _assert(client.post("/api/v1/academics/levels", headers=manager, json={
                "code": f"M28-8-L{index}-{uuid4().hex[:5]}", "name": f"Synthetic level {index}", "sort_order": index,
            }), 201)
            grade = _assert(client.post("/api/v1/academics/grades", headers=manager, json={
                "academic_level_id": level["id"], "code": f"M28-8-G{index}-{uuid4().hex[:5]}",
                "name": f"Synthetic grade {index}", "sort_order": index,
            }), 201)
            levels.append(level)
            grades.append(grade)
            section = _assert(client.post("/api/v1/academics/sections", headers=manager, json={
                "academic_period_id": period_id, "campus_id": str(campus),
                "grade_level_id": grade["id"], "code": f"M28-8-S{index}-{uuid4().hex[:5]}",
                "name": f"Synthetic section {index}", "capacity": 30,
            }), 201)
            sections.append(section)
        subjects, plans, offerings = [], [], []
        for index in (1, 2):
            subject = _assert(client.post("/api/v1/academics/subjects", headers=manager, json={
                "code": f"M28-8-SUB{index}-{uuid4().hex[:5]}", "name": f"Synthetic subject {index}",
            }), 201)
            subjects.append(subject)
            for grade_index, grade in enumerate(grades, start=1):
                plan = _assert(client.post("/api/v1/academics/curriculum-plans", headers=manager, json={
                    "academic_period_id": period_id, "grade_level_id": grade["id"],
                    "code": f"M28-8-CP{index}{grade_index}-{uuid4().hex[:5]}",
                    "name": f"Synthetic curriculum {index}.{grade_index}",
                }), 201)
                plans.append(plan)
                curriculum_subject = _assert(client.post(
                    f"/api/v1/academics/curriculum-plans/{plan['id']}/subjects",
                    headers=manager, json={"subject_id": subject["id"], "weekly_periods": 3},
                ), 201)
                section = sections[grade_index - 1]
                offering = _assert(client.post("/api/v1/academics/course-offerings", headers=manager, json={
                    "section_id": section["id"], "subject_id": subject["id"],
                    "curriculum_subject_id": curriculum_subject["id"],
                }), 201)
                offerings.append(offering)
        assignment_map: dict[str, list[dict[str, str]]] = {"teacher_a": [], "teacher_b": []}
        for offering in offerings:
            actor = "teacher_a" if offering["section_id"] == sections[0]["id"] else "teacher_b"
            assignment = _assert(client.post("/api/v1/academics/teaching-assignments", headers=manager, json={
                "course_offering_id": offering["id"], "staff_profile_id": str(actors[actor]["staff_id"]),
                "starts_on": (today - timedelta(days=30)).isoformat(),
                "ends_on": (today + timedelta(days=90)).isoformat(),
            }), 201)
            assignment_map[actor].append(assignment)
        assert len(offerings) == 4 and len(assignment_map["teacher_a"]) == 2 and len(assignment_map["teacher_b"]) == 2

        enrollments: list[str] = []
        placements: list[str] = []
        for index, student in enumerate(students):
            pending = _assert(client.post("/api/v1/enrollments", headers=manager, json={
                "student_profile_id": student["id"], "academic_period_id": period_id,
                "campus_id": str(campus), "enrollment_number": f"M28-8-ENR-{index + 1:02d}",
                "status": "PENDING", "enrolled_on": None,
            }), 201)
            active = _assert(client.patch(f"/api/v1/enrollments/{pending['id']}/status", headers=manager, json={
                "status": "ACTIVE", "expected_updated_at": pending["updated_at"],
                "effective_on": (today - timedelta(days=30)).isoformat(),
            }), 200)
            enrollments.append(active["id"])
            section = sections[0 if index < 5 else 1]
            placement = _assert(client.post("/api/v1/academics/student-section-assignments", headers=manager, json={
                "enrollment_id": active["id"], "section_id": section["id"],
                "assigned_on": (today - timedelta(days=30)).isoformat(),
            }), 201)
            placements.append(placement["id"])

        teacher_a_roster = _assert(client.get(
            f"/api/v1/teacher/classes/{offerings[0]['id']}/roster", headers=teacher_a,
        ), 200)
        teacher_b_roster = _assert(client.get(
            f"/api/v1/teacher/classes/{offerings[1]['id']}/roster", headers=teacher_b,
        ), 200)
        assert len(teacher_a_roster) == len(teacher_b_roster) == 5
        assert client.get(f"/api/v1/teacher/classes/{offerings[1]['id']}/roster", headers=teacher_a).status_code == 403
        assert client.get(f"/api/v1/teacher/classes/{offerings[0]['id']}/roster", headers=teacher_b).status_code == 403

        grading_period = _assert(client.post("/api/v1/grades/periods", headers=manager, json={
            "academic_period_id": period_id, "code": f"M28-8-GP-{uuid4().hex[:6]}",
            "name": "Synthetic grading period", "starts_on": (today - timedelta(days=15)).isoformat(),
            "ends_on": (today + timedelta(days=60)).isoformat(), "sequence": 1,
        }), 201)
        assert client.patch(
            f"/api/v1/grades/periods/{grading_period['id']}/status", headers=teacher_a,
            json={"expected_status": "PLANNED", "status": "ACTIVE"},
        ).status_code == 403
        grading_period = _assert(client.patch(
            f"/api/v1/grades/periods/{grading_period['id']}/status", headers=manager,
            json={"expected_status": "PLANNED", "status": "ACTIVE"},
        ), 200)
        assessments = []
        entries_by_assessment: list[list[dict[str, str]]] = []
        for offering, teacher_headers in ((offerings[0], teacher_a), (offerings[1], teacher_b)):
            category = _assert(client.post(
                f"/api/v1/teacher/classes/{offering['id']}/categories", headers=teacher_headers,
                json={"grading_period_id": grading_period["id"], "code": "PILOT", "name": "Pilot assessment"},
            ), 201)
            assessment = _assert(client.post(
                f"/api/v1/teacher/classes/{offering['id']}/assessments", headers=teacher_headers,
                json={"grading_period_id": grading_period["id"], "assessment_category_id": category["id"],
                      "code": f"M28-8-AS-{uuid4().hex[:6]}", "title": "Synthetic assessed work",
                      "max_score": 20, "due_on": yesterday.isoformat(), "operation_id": str(uuid4())},
            ), 201)
            assessment = _assert(client.patch(
                f"/api/v1/teacher/assessments/{assessment['id']}/status", headers=teacher_headers,
                json={"expected_status": "DRAFT", "status": "PUBLISHED", "operation_id": str(uuid4())},
            ), 200)
            assessments.append(assessment)
            roster = _assert(client.get(f"/api/v1/teacher/assessments/{assessment['id']}/grades", headers=teacher_headers), 200)
            entries = []
            for row_index, grade_row in enumerate(roster):
                status = "MISSING" if row_index == 4 else "GRADED"
                score = None if status == "MISSING" else (0 if row_index == 0 else 14.5)
                result = _assert(client.put(
                    f"/api/v1/teacher/assessments/{assessment['id']}/grades", headers=teacher_headers,
                    json={"student_section_assignment_id": grade_row["student_section_assignment_id"],
                          "score": score, "status": status, "expected_revision": 0,
                          "operation_id": str(uuid4())},
                ), 200)
                if row_index == 4:
                    assert result["status"] == "MISSING" and result["score"] is None
                if row_index == 0:
                    assert result["status"] == "GRADED" and result["score"] == 0.0
                entries.append(result)
            entries_by_assessment.append(entries)
        assert sum(map(len, entries_by_assessment)) == 10
        first_entry = entries_by_assessment[0][0]
        correction = _assert(client.put(
            f"/api/v1/teacher/assessments/{assessments[0]['id']}/grades", headers=teacher_a,
            json={"student_section_assignment_id": first_entry["student_section_assignment_id"],
                  "score": 12.125, "status": "GRADED", "expected_revision": 1,
                  "operation_id": str(uuid4()), "correction_reason": "EVIDENCE_CORRECTION"},
        ), 200)
        assert correction["revision"] == 2
        conflict = client.put(
            f"/api/v1/teacher/assessments/{assessments[0]['id']}/grades", headers=teacher_a,
            json={"student_section_assignment_id": first_entry["student_section_assignment_id"],
                  "score": 11, "status": "GRADED", "expected_revision": 1,
                  "operation_id": str(uuid4()), "correction_reason": "DATA_ENTRY_ERROR"},
        )
        assert conflict.status_code == 409
        history = _assert(client.get(
            f"/api/v1/teacher/assessments/{assessments[0]['id']}/grades/{first_entry['student_section_assignment_id']}/history",
            headers=teacher_a,
        ), 200)
        assert history[0]["new_value"]["score"] == "0.000"
        assert history[1]["new_value"]["score"] == "12.125"
        _assert(client.patch(
            f"/api/v1/teacher/assessments/{assessments[0]['id']}/status", headers=teacher_a,
            json={"expected_status": "PUBLISHED", "status": "CLOSED", "operation_id": str(uuid4())},
        ), 200)
        _assert(client.patch(
            f"/api/v1/grades/periods/{grading_period['id']}/status", headers=manager,
            json={"expected_status": "ACTIVE", "status": "CLOSED"},
        ), 200)

        present_code = _assert(client.post("/api/v1/attendance/codes", headers=manager, json={
            "code": f"M28-8-P-{uuid4().hex[:6]}", "label": "Synthetic present", "semantic": "PRESENT",
            "counts_as_present": True,
        }), 201)
        absent_code = _assert(client.post("/api/v1/attendance/codes", headers=manager, json={
            "code": f"M28-8-A-{uuid4().hex[:6]}", "label": "Synthetic absent", "semantic": "ABSENT",
            "counts_as_absent": True,
        }), 201)
        sessions = []
        for session_index in range(5):
            created = _assert(client.post(f"/api/v1/teacher/classes/{offerings[0]['id']}/sessions", headers=teacher_a, json={
                "session_date": (yesterday - timedelta(days=2 * session_index)).isoformat(),
                "starts_at": "09:00", "ends_at": "09:45",
            }), 201)
            sessions.append(created)
        online_attendance_id = None
        for session_index, class_session in enumerate(sessions):
            for student_index in range(5):
                if session_index == 0 and student_index == 0:
                    continue
                code = absent_code if session_index < 3 and student_index == 0 else present_code
                result = _assert(client.put(
                    f"/api/v1/teacher/sessions/{class_session['id']}/attendance", headers=teacher_a,
                    json={"student_section_assignment_id": placements[student_index],
                          "attendance_code_id": code["id"], "minutes_late": 0},
                ), 200)
                if session_index == 0 and student_index == 1:
                    online_attendance_id = result["id"]
        assert online_attendance_id
        first_session = sessions[0]
        rows = _assert(client.get(f"/api/v1/teacher/sessions/{first_session['id']}/attendance", headers=teacher_a), 200)
        correction_row = next(row for row in rows if str(row["student_section_assignment_id"]) == placements[1])
        corrected_attendance = _assert(client.put(
            f"/api/v1/teacher/sessions/{first_session['id']}/attendance", headers=teacher_a,
            json={"student_section_assignment_id": placements[1], "attendance_code_id": absent_code["id"],
                  "minutes_late": 1,
                  "expected_state": {"attendance_record_id": correction_row["attendance_record_id"],
                                     "attendance_code_id": correction_row["attendance_code_id"],
                                     "minutes_late": correction_row["minutes_late"], "note": None},
                  "correction_reason": "EVIDENCE_CORRECTION"},
        ), 200)
        assert corrected_attendance["minutes_late"] == 1

        offline_op = TeacherOfflineSyncBatch(operations=[TeacherOfflineAttendanceOperation(
            operation_id=uuid4(), class_session_id=first_session["id"],
            base=TeacherOfflineAttendanceBase(),
            desired=TeacherAttendanceMark(student_section_assignment_id=UUID(placements[0]),
                                           attendance_code_id=UUID(present_code["id"]), minutes_late=0),
        )])
        offline_result = _assert(client.post(
            "/api/v1/teacher/offline/sync", headers=teacher_a,
            json=offline_op.model_dump(mode="json"),
        ), 200)["results"][0]
        assert offline_result["status"] == "APPLIED"
        replay = _assert(client.post(
            "/api/v1/teacher/offline/sync", headers=teacher_a,
            json=offline_op.model_dump(mode="json"),
        ), 200)["results"][0]
        assert replay["status"] == "REPLAYED"
        stale_offline = offline_op.model_copy(update={
            "operations": [offline_op.operations[0].model_copy(update={"operation_id": uuid4()})],
        })
        stale_result = _assert(client.post(
            "/api/v1/teacher/offline/sync", headers=teacher_a,
            json=stale_offline.model_dump(mode="json"),
        ), 200)["results"][0]
        assert stale_result["status"] == "CONFLICT"

        # Reuse the operation ID against a different, still-authorized class
        # after the original assignment is revoked.  The mismatch must not
        # disclose the original target's attendance state.
        alternate_session = _assert(client.post(
            f"/api/v1/teacher/classes/{offerings[2]['id']}/sessions", headers=teacher_a, json={
                "session_date": today.isoformat(), "starts_at": "10:00", "ends_at": "10:45",
            },
        ), 201)
        before_mismatch_records = pilot["session"].exec(text(
            "SELECT count(*) FROM attendance_records WHERE class_session_id IN (:original, :alternate)"
        ), params={"original": first_session["id"], "alternate": alternate_session["id"]}).one()[0]
        before_mismatch_events = pilot["session"].exec(text(
            "SELECT count(*) FROM outbox_events WHERE event_type LIKE 'student.attendance.%'"
        )).one()[0]
        original_assignment = assignment_map["teacher_a"][0]
        _assert(client.patch(
            f"/api/v1/academics/teaching-assignments/{original_assignment['id']}", headers=manager,
            json={"expected_ends_on": original_assignment["ends_on"], "ends_on": (today - timedelta(days=2)).isoformat()},
        ), 200)
        mismatch_after_revocation = offline_op.model_copy(update={
            "operations": [offline_op.operations[0].model_copy(update={
                "class_session_id": UUID(alternate_session["id"]),
                "desired": offline_op.operations[0].desired.model_copy(update={
                    "student_section_assignment_id": UUID(placements[1]),
                }),
            })],
        })
        mismatch = _assert(client.post(
            "/api/v1/teacher/offline/sync", headers=teacher_a,
            json=mismatch_after_revocation.model_dump(mode="json"),
        ), 200)["results"][0]
        assert mismatch["status"] == "IDEMPOTENCY_MISMATCH"
        assert mismatch.get("result_entity_id") is None
        assert mismatch.get("server_state") is None
        assert pilot["session"].exec(text(
            "SELECT count(*) FROM attendance_records WHERE class_session_id IN (:original, :alternate)"
        ), params={"original": first_session["id"], "alternate": alternate_session["id"]}).one()[0] == before_mismatch_records
        assert pilot["session"].exec(text(
            "SELECT count(*) FROM outbox_events WHERE event_type LIKE 'student.attendance.%'"
        )).one()[0] == before_mismatch_events

        transfer = _assert(client.post(
            f"/api/v1/academics/enrollments/{enrollments[0]}/placements/transfer", headers=manager,
            json={"expected_current_placement_id": placements[0], "section_id": sections[1]["id"],
                  "effective_on": today.isoformat()},
        ), 200)
        assert transfer["status"] == "ACTIVE"
        assert _assert(client.get(f"/api/v1/enrollments/{enrollments[0]}", headers=manager), 200)["status"] == "ACTIVE"
        placement_history = _assert(client.get(
            f"/api/v1/academics/students/{students[0]['id']}/placements", headers=manager,
        ), 200)
        assert len(placement_history) == 2
        old_placement = next(item for item in placement_history if item["id"] == placements[0])
        assert old_placement["status"] == "TRANSFERRED"

        # M22's existing thresholds are exercised with five records and a
        # majority absence condition for the first synthetic student.
        manager_principal = CurrentPrincipal(actors["manager"]["user_id"], org, institution)
        apply_tenant_context(pilot["session"], TenantContext(org, institution, actors["manager"]["user_id"]))
        refreshed = refresh_signals(pilot["session"], manager_principal)
        signals = client.get("/api/v1/intelligence/signals", headers=manager)
        _assert(signals, 200)
        attendance_signal = next((item for item in signals.json() if item["signal_type"] == "ATTENDANCE_RISK"), None)
        assert attendance_signal is not None, f"M22 returned {refreshed.detected_or_refreshed} signals"

        # M27 case projection links the actual M22 signal/event, then humans
        # assign, review, decide and complete a bounded obligation.
        apply_tenant_context(pilot["session"], TenantContext(
            org, institution, actors["system_admin"]["user_id"],
        ))
        ingest_outbox_events(pilot["session"], institution_id=institution, limit=5000)
        signal_events = pilot["session"].exec(text("""
            SELECT l.id, l.recorded_at, l.aggregate_id FROM event_ledger l
            WHERE l.institution_id=CAST(:institution AS uuid)
              AND l.event_type='student.signal.opened'
            ORDER BY l.position DESC LIMIT 1
        """), params={"institution": str(institution), "signal_id": attendance_signal["id"]}).first()
        assert signal_events is not None, pilot["session"].exec(text("""
            SELECT event_type, aggregate_id, payload_json::text FROM outbox_events
            WHERE institution_id=CAST(:institution AS uuid) AND event_type LIKE 'student.signal.%'
        """), params={"institution": str(institution)}).all()
        assert str(signal_events[2]) == attendance_signal["id"], (signal_events, attendance_signal)
        signal_event = signal_events[:2]
        apply_tenant_context(pilot["session"], TenantContext(
            org, institution, actors["manager"]["user_id"],
        ))
        source_hash = "a" * 64
        case_input = CaseProjectionInput(
            organization_id=org, institution_id=institution,
            subject_type="STUDENT", subject_id=UUID(attendance_signal["student_profile_id"]),
            source_category="ATTENDANCE_RISK", episode_anchor=f"M28-8:{attendance_signal['id']}",
            source=CaseSourceInput(
                source_kind="M22", source_entity_id=UUID(attendance_signal["id"]),
                source_event_id=signal_event[0], source_category="ATTENDANCE_RISK",
                source_provenance_sha256=source_hash, observed_at=signal_event[1],
            ),
        )
        case, _identity, created = project_case(pilot["session"], case_input)
        assert created
        provenance_hash = "b" * 64
        case_id = case.id
        assigned = assign_case_owner(
            pilot["session"], manager_principal, case_id, actors["coordinator"]["user_id"],
            idempotency_key="c" * 64, provenance_sha256=provenance_hash,
        )
        assert assigned.created
        apply_tenant_context(pilot["session"], TenantContext(
            org, institution, actors["coordinator"]["user_id"],
        ))
        review = record_case_review(
            pilot["session"], CurrentPrincipal(actors["coordinator"]["user_id"], org, institution),
            case_id, disposition="READY_FOR_DECISION", evidence_refs=[str(signal_event[0])],
            evidence_fingerprint_sha256="d" * 64, next_required_step="Record human decision",
            idempotency_key="e" * 64, provenance_sha256=provenance_hash,
        )
        before_interventions = pilot["session"].exec(text(
            "SELECT count(*) FROM interventions WHERE institution_id=CAST(:id AS uuid)"
        ), params={"id": str(institution)}).one()[0]
        decision = record_case_decision(
            pilot["session"], CurrentPrincipal(actors["coordinator"]["user_id"], org, institution),
            case_id, review_id=review.record.id, decision_type="MONITOR",
            evidence_refs=[str(signal_event[0])], evidence_fingerprint_sha256="d" * 64,
            idempotency_key="f" * 64, provenance_sha256=provenance_hash,
        )
        assert decision.created and decision.record.decision_actor_user_id == actors["coordinator"]["user_id"]
        assert pilot["session"].exec(text(
            "SELECT count(*) FROM interventions WHERE institution_id=CAST(:id AS uuid)"
        ), params={"id": str(institution)}).one()[0] == before_interventions
        obligation = create_accountability_obligation(
            pilot["session"], CurrentPrincipal(actors["coordinator"]["user_id"], org, institution),
            case_id, origin_type="CASE", origin_id=case_id,
            obligation_type="FOLLOW_UP_REQUIRED", creation_idempotency_key="1" * 64,
            provenance_sha256=provenance_hash, owner_user_id=actors["coordinator"]["user_id"],
        )
        completed = complete_accountability_obligation(
            pilot["session"], CurrentPrincipal(actors["coordinator"]["user_id"], org, institution),
            obligation.obligation.id, evidence_type="M27_HUMAN_REVIEW",
            evidence_id=review.record.id, evidence_fingerprint_sha256="2" * 64,
            idempotency_key="3" * 64, provenance_sha256=provenance_hash,
        )
        assert completed.created

        # Run the canonical M18 and M21 consumers under a separate, minimally
        # permissioned projector identity on the real application connection.
        projector_id = actors["system_admin"]["user_id"]
        apply_tenant_context(pilot["session"], TenantContext(org, institution, projector_id))
        ingested = ingest_outbox_events(pilot["session"], institution_id=institution, limit=5000)
        projected = project_student_timeline(pilot["session"], organization_id=org, institution_id=institution, limit=5000)
        assert ingested > 0 and projected.inserted > 0
        ledger_facts = pilot["session"].exec(text("""
            SELECT event_type, organization_id, institution_id, aggregate_id
            FROM event_ledger
            WHERE institution_id=CAST(:institution AS uuid)
              AND event_type IN ('grading_period.status_changed', 'student.enrollment.created', 'student.attendance.recorded',
                                 'student.attendance.updated', 'student.grade.recorded',
                                 'student.grade.updated')
        """), params={"institution": str(institution)}).all()
        assert ledger_facts
        assert all(row[1] == org and row[2] == institution for row in ledger_facts)
        assert any(row[0] == "student.attendance.recorded" for row in ledger_facts)
        assert any(row[0] == "student.grade.recorded" for row in ledger_facts)
        assert any(row[0] == "grading_period.status_changed" for row in ledger_facts)
        timeline_rows = pilot["session"].exec(text("""
            SELECT event_type, count(*) FROM student_timeline_entries
            WHERE institution_id=CAST(:institution AS uuid)
              AND student_profile_id=CAST(:student AS uuid)
            GROUP BY event_type
        """), params={"institution": str(institution), "student": students[0]["id"]}).all()
        timeline_counts = {event: count for event, count in timeline_rows}
        assert timeline_counts.get("student.attendance.recorded", 0) >= 1
        assert timeline_counts.get("student.grade.recorded", 0) >= 1
        # M21's frozen timeline consumer covers operational attendance and
        # grade facts; M27 consumes the M22 signal through its M18 event.
        second_projection = project_student_timeline(pilot["session"], organization_id=org, institution_id=institution, limit=5000)
        assert second_projection.inserted == 0
        assert client.get(f"/api/v1/students/{students[0]['id']}", headers=manager).status_code == 200

        # Scope/role denial remains in the live HTTP path.
        assert client.get("/api/v1/students/records", headers=unauthorized).status_code == 403
        assert client.post("/api/v1/academics/levels", headers=teacher_a, json={
            "code": "FORBIDDEN", "name": "Forbidden", "sort_order": 1,
        }).status_code == 403
        assert client.get(f"/api/v1/teacher/classes/{offerings[1]['id']}/roster", headers=teacher_a).status_code == 403
        assert client.get("/api/v1/grades/assessments", headers=system_admin).status_code == 403

        # No high-impact action follows an attendance signal or a MONITOR choice.
        assert client.get("/api/v1/enrollments", headers=manager).status_code == 200
        assert pilot["session"].exec(text(
            "SELECT count(*) FROM interventions WHERE institution_id=CAST(:id AS uuid)"
        ), params={"id": str(institution)}).one()[0] == before_interventions
