from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlmodel import Session

from app.api.access import TeacherPrincipal
from app.db.session import engine as app_engine
from app.db.tenant_context import TenantContext, apply_tenant_context
from app.modules.academics import service as academic_service
from app.modules.families.models import StaffProfile
from app.modules.identity.models import Membership, MembershipRole, Person, Role, UserAccount
from app.modules.teacher_offline.schemas import TeacherOfflineSyncBatch
from app.modules.teacher_offline.service import sync_teacher_offline_operations
from tests.integration.test_m28_student_record_security import (
    INSTITUTION_ID,
    ORG_ID,
    _headers,
    _pilot,
)


def _fail_outbox(*_args, **_kwargs):
    raise RuntimeError("synthetic outbox failure")


def test_academic_structure_is_permission_scoped_integral_and_audited(monkeypatch) -> None:
    with _pilot() as pilot:
        owner = pilot["owner"]
        client = pilot["client"]
        actor = pilot["actors"][0]
        role_id = actor["role_id"]
        generated: dict[str, list[str]] = {
            "academic_periods": [], "academic_levels": [], "grade_levels": [],
            "subjects": [], "sections": [], "curriculum_plans": [],
            "curriculum_subjects": [], "course_offerings": [], "teaching_assignments": [],
            "enrollments": [],
            "student_section_assignments": [],
            "class_sessions": [],
            "attendance_records": [],
            "attendance_codes": [],
        }
        foreign: dict[str, str] = {}
        offline_capability_before = None
        offline_capability_touched = False
        try:
            denied = client.get("/api/v1/academics/levels", headers=pilot["bare_headers"])
            assert denied.status_code == 403
            assert client.get("/api/v1/academic-periods", headers=pilot["bare_headers"]).status_code == 403
            assert client.post("/api/v1/academics/subjects", headers=pilot["bare_headers"], json={
                "code": "DENIED", "name": "Denied",
            }).status_code == 403

            system_role = Role(institution_id=INSTITUTION_ID, key="SYSTEM_ADMIN", name="Synthetic system administrator")
            owner.add(system_role)
            owner.flush()
            sys_person = Person(organization_id=ORG_ID,
                                given_names="Synthetic", family_names="Academic system admin test")
            owner.add(sys_person)
            owner.flush()
            sys_user = UserAccount(person_id=sys_person.id, login_email=f"m28-real-system-{uuid4().hex[:10]}@test.invalid", password_hash="not-a-credential")
            owner.add(sys_user)
            owner.flush()
            sys_membership = Membership(user_id=sys_user.id, institution_id=INSTITUTION_ID, status="ACTIVE")
            owner.add(sys_membership)
            sys_staff = StaffProfile(organization_id=ORG_ID, institution_id=INSTITUTION_ID,
                                     person_id=sys_person.id, staff_code=f"M28-SYS-{uuid4().hex[:6]}")
            owner.add(sys_staff)
            owner.flush()
            owner.add(MembershipRole(membership_id=sys_membership.id, role_id=system_role.id))
            owner.commit()
            system_admin_actor = {
                "user_id": sys_user.id, "person_id": sys_person.id, "role_id": system_role.id,
                "role_owned": True, "membership_id": sys_membership.id, "staff_id": sys_staff.id,
            }
            pilot["actors"].append(system_admin_actor)
            system_admin_headers = _headers(system_admin_actor)
            assert client.get("/api/v1/academics/levels", headers=system_admin_headers).status_code == 403
            assert client.get("/api/v1/academic-periods", headers=system_admin_headers).status_code == 403

            for key in (
                "academics.read", "academics.manage", "academics.assign",
                "attendance.read", "attendance.manage", "attendance.correct",
            ):
                owner.exec(text("""INSERT INTO role_permissions (role_id, permission_id)
                    SELECT :role, id FROM permissions WHERE key=:key ON CONFLICT DO NOTHING"""),
                    params={"role": role_id, "key": key})
            owner.commit()
            headers = pilot["authorized_headers"]

            failed_code = f"ROLLBACK-{uuid4().hex[:8]}"
            with monkeypatch.context() as patcher:
                patcher.setattr(academic_service, "enqueue_canonical_event", _fail_outbox)
                failed_write = client.post("/api/v1/academics/subjects", headers=headers, json={
                    "code": failed_code, "name": "Must not persist",
                })
            assert failed_write.status_code == 500
            assert owner.exec(text("SELECT 1 FROM subjects WHERE institution_id=:institution AND code=:code"),
                              params={"institution": INSTITUTION_ID, "code": failed_code}).first() is None

            foreign_institution = owner.exec(text(
                "SELECT id, organization_id FROM institutions WHERE id<>:id ORDER BY id LIMIT 1"
            ), params={"id": INSTITUTION_ID}).one()
            foreign_person = Person(
                organization_id=foreign_institution[1],
                given_names="Synthetic",
                family_names="Foreign M28-3 staff",
            )
            owner.add(foreign_person)
            owner.flush()
            foreign_staff = StaffProfile(
                organization_id=foreign_institution[1],
                institution_id=foreign_institution[0],
                person_id=foreign_person.id,
                staff_code=f"F-{uuid4().hex[:8]}",
            )
            owner.add(foreign_staff)
            owner.flush()
            foreign["staff"] = str(foreign_staff.id)
            foreign["person"] = str(foreign_person.id)
            foreign.update({key: str(uuid4()) for key in ("period", "level", "grade", "subject", "campus", "section")})
            foreign_values = {**foreign, "org": foreign_institution[1], "institution": foreign_institution[0]}
            owner.exec(text("""INSERT INTO academic_periods
                (id, organization_id, institution_id, code, name, starts_on, ends_on, status, created_at)
                VALUES (:period, :org, :institution, :code, 'Foreign synthetic period', '2026-01-01', '2027-12-31', 'ACTIVE', CURRENT_TIMESTAMP)"""),
                params={**foreign_values, "code": f"F-{uuid4().hex[:10]}"})
            owner.exec(text("""INSERT INTO academic_levels
                (id, organization_id, institution_id, code, name, sort_order, status, created_at)
                VALUES (:level, :org, :institution, :code, 'Foreign level', 1, 'ACTIVE', CURRENT_TIMESTAMP)"""),
                params={**foreign_values, "code": f"F-{uuid4().hex[:8]}"})
            owner.exec(text("""INSERT INTO grade_levels
                (id, organization_id, institution_id, academic_level_id, code, name, sort_order, status, created_at)
                VALUES (:grade, :org, :institution, :level, :code, 'Foreign grade', 1, 'ACTIVE', CURRENT_TIMESTAMP)"""),
                params={**foreign_values, "code": f"F-{uuid4().hex[:8]}"})
            owner.exec(text("""INSERT INTO subjects
                (id, organization_id, institution_id, code, name, status, created_at)
                VALUES (:subject, :org, :institution, :code, 'Foreign subject', 'ACTIVE', CURRENT_TIMESTAMP)"""),
                params={**foreign_values, "code": f"F-{uuid4().hex[:8]}"})
            owner.exec(text("INSERT INTO campuses (id, institution_id, name, created_at) VALUES (:campus, :institution, 'Foreign campus', CURRENT_TIMESTAMP)"), params=foreign_values)
            owner.exec(text("""INSERT INTO sections
                (id, organization_id, institution_id, academic_period_id, campus_id, grade_level_id, code, name, capacity, status, created_at)
                VALUES (:section, :org, :institution, :period, :campus, :grade, 'FOREIGN', 'Foreign section', 20, 'ACTIVE', CURRENT_TIMESTAMP)"""), params=foreign_values)
            owner.commit()

            period_response = client.post("/api/v1/academic-periods", headers=headers, json={
                "code": f"M28-{uuid4().hex[:10]}", "name": "Synthetic academic cycle",
                "starts_on": "2026-01-01", "ends_on": "2027-12-31",
            })
            assert period_response.status_code == 201, period_response.text
            period = period_response.json()
            period_id = period["id"]
            generated["academic_periods"].append(period_id)
            assert period["status"] == "PLANNED"
            assert client.post("/api/v1/academic-periods", headers=headers, json={
                "code": period["code"], "name": "Duplicate cycle",
                "starts_on": "2026-01-01", "ends_on": "2027-12-31",
            }).status_code == 409
            assert client.post("/api/v1/academic-periods", headers=headers, json={
                "code": f"M28-{uuid4().hex[:10]}", "name": "Forged status",
                "starts_on": "2026-01-01", "ends_on": "2027-12-31", "status": "ACTIVE",
            }).status_code == 422
            assert client.patch(f"/api/v1/academic-periods/{period_id}/status", headers=headers, json={
                "expected_status": "PLANNED", "status": "ACTIVE",
            }).status_code == 200
            assert client.patch(f"/api/v1/academic-periods/{period_id}/status", headers=headers, json={
                "expected_status": "PLANNED", "status": "CLOSED",
            }).status_code == 409

            campus_id = str(uuid4())
            pilot["campus_ids"].append(UUID(campus_id))
            owner.exec(text("INSERT INTO campuses (id, institution_id, name, created_at) VALUES (:id, :institution, 'Synthetic M28-3 campus', CURRENT_TIMESTAMP)"),
                       params={"id": campus_id, "institution": INSTITUTION_ID})
            owner.commit()

            enrollment_response = client.post("/api/v1/enrollments", headers=headers, json={
                "student_profile_id": str(pilot["student"]), "academic_period_id": period_id,
                "campus_id": campus_id, "status": "ACTIVE", "enrolled_on": "2026-02-01",
            })
            assert enrollment_response.status_code == 201, enrollment_response.text
            enrollment_id = enrollment_response.json()["id"]
            generated["enrollments"].append(enrollment_id)
            assert client.patch(f"/api/v1/academic-periods/{period_id}/status", headers=headers, json={
                "expected_status": "ACTIVE", "status": "CLOSED",
            }).status_code == 409

            level_response = client.post("/api/v1/academics/levels", headers=headers, json={
                "code": f"LV-{uuid4().hex[:8]}", "name": "Synthetic level", "sort_order": 1,
            })
            assert level_response.status_code == 201, level_response.text
            level_id = level_response.json()["id"]
            generated["academic_levels"].append(level_id)
            grade_response = client.post("/api/v1/academics/grades", headers=headers, json={
                "academic_level_id": level_id, "code": f"GR-{uuid4().hex[:8]}",
                "name": "Synthetic grade", "sort_order": 1,
            })
            assert grade_response.status_code == 201, grade_response.text
            grade_id = grade_response.json()["id"]
            generated["grade_levels"].append(grade_id)
            subject_response = client.post("/api/v1/academics/subjects", headers=headers, json={
                "code": f"SB-{uuid4().hex[:8]}", "name": "Synthetic subject", "area": "Synthetic",
            })
            assert subject_response.status_code == 201, subject_response.text
            subject_id = subject_response.json()["id"]
            generated["subjects"].append(subject_id)

            section_body = {
                "academic_period_id": period_id, "campus_id": campus_id, "grade_level_id": grade_id,
                "code": f"SC-{uuid4().hex[:8]}", "name": "Synthetic section", "capacity": 30,
            }
            section_response = client.post("/api/v1/academics/sections", headers=headers, json=section_body)
            assert section_response.status_code == 201, section_response.text
            section_id = section_response.json()["id"]
            generated["sections"].append(section_id)
            target_sections = []
            for suffix in ("B", "C"):
                response = client.post("/api/v1/academics/sections", headers=headers, json={
                    **section_body, "code": f"SC-{suffix}-{uuid4().hex[:6]}",
                    "name": f"Synthetic transfer section {suffix}",
                })
                assert response.status_code == 201, response.text
                target_sections.append(response.json()["id"])
                generated["sections"].append(response.json()["id"])
            assert client.post("/api/v1/academics/sections", headers=headers,
                               json={**section_body, "organization_id": str(uuid4())}).status_code == 422
            assert client.post("/api/v1/academics/sections", headers=headers,
                               json={**section_body, "academic_period_id": foreign["period"]}).status_code == 404
            assert client.post("/api/v1/academics/sections", headers=headers,
                               json={**section_body, "grade_level_id": foreign["grade"]}).status_code == 404
            assert client.post("/api/v1/academics/sections", headers=headers,
                               json={**section_body, "campus_id": foreign["campus"]}).status_code == 404

            plan_response = client.post("/api/v1/academics/curriculum-plans", headers=headers, json={
                "academic_period_id": period_id, "grade_level_id": grade_id,
                "code": f"CP-{uuid4().hex[:8]}", "name": "Synthetic curriculum",
            })
            assert plan_response.status_code == 201, plan_response.text
            plan_id = plan_response.json()["id"]
            generated["curriculum_plans"].append(plan_id)
            curriculum_subject_response = client.post(
                f"/api/v1/academics/curriculum-plans/{plan_id}/subjects", headers=headers,
                json={"subject_id": subject_id, "weekly_periods": 4},
            )
            assert curriculum_subject_response.status_code == 201, curriculum_subject_response.text
            curriculum_subject_id = curriculum_subject_response.json()["id"]
            generated["curriculum_subjects"].append(curriculum_subject_id)
            offering_response = client.post("/api/v1/academics/course-offerings", headers=headers, json={
                "section_id": section_id, "subject_id": subject_id,
                "curriculum_subject_id": curriculum_subject_id,
            })
            assert offering_response.status_code == 201, offering_response.text
            offering_id = offering_response.json()["id"]
            generated["course_offerings"].append(offering_id)
            assert client.post("/api/v1/academics/course-offerings", headers=headers, json={
                "section_id": section_id, "subject_id": foreign["subject"],
            }).status_code == 404
            assert client.post("/api/v1/academics/course-offerings", headers=headers, json={
                "section_id": foreign["section"], "subject_id": subject_id,
            }).status_code == 404

            staff_id = str(actor["staff_id"])
            assert client.get(f"/api/v1/teacher/classes/{offering_id}/roster",
                              headers=pilot["teacher_headers"]).status_code == 403
            assignment_response = client.post("/api/v1/academics/teaching-assignments", headers=headers, json={
                "course_offering_id": offering_id, "staff_profile_id": staff_id,
                "starts_on": "2026-01-01", "ends_on": "2027-12-31",
            })
            assert assignment_response.status_code == 201, assignment_response.text
            assignment_id = assignment_response.json()["id"]
            generated["teaching_assignments"].append(assignment_id)
            teacher_assignment = client.post("/api/v1/academics/teaching-assignments", headers=headers, json={
                "course_offering_id": offering_id,
                "staff_profile_id": str(pilot["actors"][3]["staff_id"]),
                "starts_on": "2026-01-01",
            })
            assert teacher_assignment.status_code == 201, teacher_assignment.text
            generated["teaching_assignments"].append(teacher_assignment.json()["id"])
            assert client.get(f"/api/v1/teacher/classes/{offering_id}/roster",
                              headers=pilot["teacher_headers"]).status_code == 200
            assert client.post("/api/v1/academics/teaching-assignments", headers=headers, json={
                "course_offering_id": offering_id, "staff_profile_id": foreign["staff"],
            }).status_code == 404
            assert client.get("/api/v1/academics/levels", headers=pilot["teacher_headers"]).status_code == 403
            assert client.post("/api/v1/academics/levels", headers=pilot["teacher_headers"], json={
                "code": "TEACHER", "name": "No", "sort_order": 1,
            }).status_code == 403

            placement_url = "/api/v1/academics/student-section-assignments"
            initial_body = {"enrollment_id": enrollment_id, "section_id": section_id, "assigned_on": "2026-02-02"}
            initial = client.post(placement_url, headers=headers, json=initial_body)
            assert initial.status_code == 201, initial.text
            placement_id = initial.json()["id"]
            generated["student_section_assignments"].append(placement_id)
            teacher_roster = client.get(f"/api/v1/teacher/classes/{offering_id}/roster",
                                        headers=pilot["teacher_headers"])
            assert teacher_roster.status_code == 200
            assert [item["student_profile_id"] for item in teacher_roster.json()] == [str(pilot["student"])]
            teacher_classes = client.get("/api/v1/teacher/classes", headers=pilot["teacher_headers"])
            assert teacher_classes.status_code == 200
            assert next(item for item in teacher_classes.json() if item["course_offering_id"] == offering_id)["student_count"] == 1
            teacher_summary = client.get("/api/v1/teacher/summary", headers=pilot["teacher_headers"])
            assert teacher_summary.status_code == 200 and teacher_summary.json()["unique_students"] == 1

            # Online and M20 offline commands share the canonical M3 fact and
            # target lock; retries must replay without a second domain write.
            offline_capability_before = owner.exec(
                text("SELECT enabled FROM institution_capabilities "
                     "WHERE institution_id=:institution AND capability_key='teacher.offline_pwa'"),
                params={"institution": INSTITUTION_ID},
            ).first()
            if offline_capability_before is None:
                owner.exec(text("INSERT INTO institution_capabilities "
                                "(institution_id, capability_key, enabled) "
                                "VALUES (:institution, 'teacher.offline_pwa', true)"),
                           params={"institution": INSTITUTION_ID})
            else:
                owner.exec(text("UPDATE institution_capabilities SET enabled=true "
                                "WHERE institution_id=:institution "
                                "AND capability_key='teacher.offline_pwa'"),
                           params={"institution": INSTITUTION_ID})
            owner.commit()
            offline_capability_touched = True

            attendance_code = client.post(
                "/api/v1/attendance/codes",
                headers=headers,
                json={"code": f"M28-{uuid4().hex[:8]}", "label": "Synthetic present",
                      "semantic": "PRESENT", "counts_as_present": True},
            )
            assert attendance_code.status_code == 201, attendance_code.text
            attendance_code_id = attendance_code.json()["id"]
            generated["attendance_codes"].append(attendance_code_id)
            attendance_codes = client.get(
                "/api/v1/teacher/attendance/codes", headers=pilot["teacher_headers"]
            )
            assert attendance_codes.status_code == 200 and attendance_codes.json()
            assert attendance_code_id in {row["id"] for row in attendance_codes.json()}
            assert client.get(
                "/api/v1/attendance/codes", headers=pilot["teacher_headers"]
            ).status_code == 403
            session_response = client.post(
                f"/api/v1/teacher/classes/{offering_id}/sessions",
                headers=pilot["teacher_headers"],
                json={"session_date": "2026-03-10", "starts_at": "09:00", "ends_at": "09:45"},
            )
            assert session_response.status_code == 201, session_response.text
            class_session_id = session_response.json()["id"]
            generated["class_sessions"].append(class_session_id)
            attendance_path = f"/api/v1/teacher/sessions/{class_session_id}/attendance"
            first_mark = client.put(
                attendance_path,
                headers=pilot["teacher_headers"],
                json={"student_section_assignment_id": placement_id,
                      "attendance_code_id": attendance_code_id, "minutes_late": 0},
            )
            assert first_mark.status_code == 200, first_mark.text
            record = first_mark.json()
            record_id = record["id"]
            generated["attendance_records"].append(record_id)
            correction = client.put(
                attendance_path,
                headers=pilot["teacher_headers"],
                json={"student_section_assignment_id": placement_id,
                      "attendance_code_id": attendance_code_id, "minutes_late": 1,
                      "expected_state": {"attendance_record_id": record_id,
                          "attendance_code_id": attendance_code_id, "minutes_late": 0,
                          "note": None}, "correction_reason": "EVIDENCE_CORRECTION"},
            )
            assert correction.status_code == 200 and correction.json()["minutes_late"] == 1
            stale_online_correction = client.put(
                attendance_path,
                headers=pilot["teacher_headers"],
                json={"student_section_assignment_id": placement_id,
                      "attendance_code_id": attendance_code_id, "minutes_late": 4,
                      "expected_state": {"attendance_record_id": record_id,
                          "attendance_code_id": attendance_code_id, "minutes_late": 0,
                          "note": None}, "correction_reason": "DATA_ENTRY_ERROR"},
            )
            assert stale_online_correction.status_code == 409

            operation_id = str(uuid4())
            offline_batch = {"operations": [{
                "operation_id": operation_id,
                "operation_type": "ATTENDANCE_MARK",
                "class_session_id": class_session_id,
                "base": {"attendance_record_id": record_id,
                         "attendance_code_id": attendance_code_id,
                         "minutes_late": 1, "note": None},
                "desired": {"student_section_assignment_id": placement_id,
                            "attendance_code_id": attendance_code_id,
                            "minutes_late": 2, "note": None},
            }]}
            assert client.post(
                "/api/v1/teacher/offline/sync",
                headers=pilot["bare_headers"],
                json=offline_batch,
            ).status_code == 403

            offline_connection = app_engine.connect()
            offline_transaction = offline_connection.begin()
            offline_session = Session(
                bind=offline_connection, join_transaction_mode="create_savepoint"
            )
            try:
                apply_tenant_context(
                    offline_session,
                    TenantContext(
                        organization_id=ORG_ID,
                        institution_id=INSTITUTION_ID,
                        user_id=pilot["actors"][3]["user_id"],
                    ),
                )
                teacher_principal = TeacherPrincipal(
                    user_id=pilot["actors"][3]["user_id"],
                    organization_id=ORG_ID,
                    institution_id=INSTITUTION_ID,
                    person_id=pilot["actors"][3]["person_id"],
                    staff_profile_id=pilot["actors"][3]["staff_id"],
                )
                offline_operation = TeacherOfflineSyncBatch.model_validate(offline_batch)
                stale_offline_batch = TeacherOfflineSyncBatch.model_validate({
                    "operations": [{**offline_batch["operations"][0],
                        "operation_id": str(uuid4()),
                        "base": {"attendance_record_id": record_id,
                                 "attendance_code_id": attendance_code_id,
                                 "minutes_late": 0, "note": None}}]
                })
                stale_result = sync_teacher_offline_operations(
                    offline_session, teacher_principal, stale_offline_batch,
                    commit=False,
                )
                assert stale_result.results[0].status == "CONFLICT"
                synced = sync_teacher_offline_operations(
                    offline_session, teacher_principal, offline_operation, commit=False
                )
                assert synced.results[0].status == "APPLIED"
                assert synced.results[0].result_entity_id == UUID(record_id)
                replayed = sync_teacher_offline_operations(
                    offline_session, teacher_principal, offline_operation, commit=False
                )
                assert replayed.results[0].status == "REPLAYED"
                mismatched_replay = TeacherOfflineSyncBatch.model_validate({
                    "operations": [{**offline_batch["operations"][0],
                        "desired": {**offline_batch["operations"][0]["desired"],
                                    "minutes_late": 3}}]
                })
                mismatch_result = sync_teacher_offline_operations(
                    offline_session, teacher_principal, mismatched_replay,
                    commit=False,
                )
                assert mismatch_result.results[0].status == "IDEMPOTENCY_MISMATCH"

                latest_canonical_event = offline_session.exec(
                    text("SELECT id,event_type FROM outbox_events WHERE aggregate_id=:id "
                         "AND event_type='student.attendance.updated' "
                         "ORDER BY created_at DESC,id DESC LIMIT 1"),
                    params={"id": record_id},
                ).one()[0]
                assert latest_canonical_event is not None
                pending_event_types = offline_session.exec(
                    text("SELECT event_type FROM outbox_events WHERE aggregate_id=:id"),
                    params={"id": record_id},
                ).all()
                assert [row[0] for row in pending_event_types].count(
                    "student.attendance.updated"
                ) == 2
                assert [row[0] for row in pending_event_types].count(
                    "teacher.attendance.synced"
                ) == 1

                offline_session.exec(
                    text("UPDATE teaching_assignments SET ends_on=CURRENT_DATE-1 "
                         "WHERE course_offering_id=:offering AND staff_profile_id=:staff"),
                    params={"offering": offering_id,
                            "staff": pilot["actors"][3]["staff_id"]},
                )
                revoked_replay = sync_teacher_offline_operations(
                    offline_session, teacher_principal, offline_operation, commit=False
                )
                assert revoked_replay.results[0].status == "REJECTED"
            finally:
                offline_session.close()
                offline_transaction.rollback()
                offline_connection.close()
            assert owner.exec(text("SELECT count(*) FROM attendance_records "
                                   "WHERE class_session_id=:session AND student_section_assignment_id=:placement"),
                              params={"session": class_session_id, "placement": placement_id}).one()[0] == 1
            attendance_event_types = owner.exec(
                text("SELECT event_type FROM outbox_events WHERE aggregate_id=:id ORDER BY event_type"),
                params={"id": record_id},
            ).all()
            assert [row[0] for row in attendance_event_types].count("student.attendance.recorded") == 1
            assert [row[0] for row in attendance_event_types].count("student.attendance.updated") == 1

            with monkeypatch.context() as patcher:
                from app.modules import attendance as attendance_module
                patcher.setattr(attendance_module.service, "enqueue_canonical_event", _fail_outbox)
                failed_correction = client.put(
                    attendance_path,
                    headers=pilot["teacher_headers"],
                    json={"student_section_assignment_id": placement_id,
                          "attendance_code_id": attendance_code_id, "minutes_late": 3,
                          "expected_state": {"attendance_record_id": record_id,
                              "attendance_code_id": attendance_code_id, "minutes_late": 1,
                              "note": None}, "correction_reason": "DATA_ENTRY_ERROR"},
                )
            assert failed_correction.status_code == 500
            after_failed_correction = client.get(attendance_path, headers=pilot["teacher_headers"])
            assert after_failed_correction.status_code == 200
            assert after_failed_correction.json()[0]["minutes_late"] == 1
            teacher_assignment_id = teacher_assignment.json()["id"]
            end_assignment_path = f"/api/v1/academics/teaching-assignments/{teacher_assignment_id}"
            ended_assignment = client.patch(end_assignment_path, headers=headers, json={
                "expected_ends_on": None, "ends_on": "2026-09-26",
            })
            assert ended_assignment.status_code == 200, ended_assignment.text
            assert client.patch(end_assignment_path, headers=pilot["teacher_headers"], json={
                "expected_ends_on": None, "ends_on": "2026-09-26",
            }).status_code == 403
            replay_end = client.patch(end_assignment_path, headers=headers, json={
                "expected_ends_on": None, "ends_on": "2026-09-26",
            })
            assert replay_end.status_code == 200
            assert client.patch(end_assignment_path, headers=headers, json={
                "expected_ends_on": None, "ends_on": "2026-09-25",
            }).status_code == 409
            assert owner.exec(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id"),
                              params={"id": teacher_assignment_id}).one()[0] == 2
            assert client.get(f"/api/v1/teacher/classes/{offering_id}/roster",
                              headers=pilot["teacher_headers"]).status_code == 403
            placement_options = client.get(
                f"/api/v1/academics/enrollments/{enrollment_id}/placement-options", headers=headers,
            )
            assert placement_options.status_code == 200
            assert {item["id"] for item in placement_options.json()["sections"]} == set(target_sections)
            assert client.get(
                f"/api/v1/academics/enrollments/{enrollment_id}/placement-options",
                headers=pilot["bare_headers"],
            ).status_code == 403
            event_before_retry = owner.exec(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id"),
                                            params={"id": placement_id}).one()[0]
            retry_initial = client.post(placement_url, headers=headers, json=initial_body)
            assert retry_initial.status_code == 201 and retry_initial.json()["id"] == placement_id
            assert owner.exec(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id"),
                              params={"id": placement_id}).one()[0] == event_before_retry
            assert client.post(placement_url, headers=pilot["bare_headers"], json=initial_body).status_code == 403
            assert client.post(placement_url, headers=pilot["teacher_headers"], json=initial_body).status_code == 403
            assert client.post(placement_url, headers=headers, json={**initial_body, "status": "TRANSFERRED"}).status_code == 422
            assert client.post(placement_url, headers=headers, json={**initial_body, "section_id": foreign["section"]}).status_code == 404

            transfer_path = f"/api/v1/academics/enrollments/{enrollment_id}/placements/transfer"
            transfer_date = "2026-04-01"
            transfer_payloads = [
                {"expected_current_placement_id": placement_id, "section_id": target, "effective_on": transfer_date}
                for target in target_sections
            ]
            with ThreadPoolExecutor(max_workers=2) as pool:
                transfer_responses = list(pool.map(
                    lambda payload: client.post(transfer_path, headers=headers, json=payload),
                    transfer_payloads,
                ))
            assert sorted(response.status_code for response in transfer_responses) == [200, 409], [
                (response.status_code, response.text) for response in transfer_responses
            ]
            winner = next(response.json() for response in transfer_responses if response.status_code == 200)
            generated["student_section_assignments"].append(winner["id"])
            active_section = winner["section_id"]
            previous_state = owner.exec(text("SELECT status, ended_on FROM student_section_assignments WHERE id=:id"),
                                         params={"id": placement_id}).one()
            assert (previous_state[0], previous_state[1].isoformat()) == ("TRANSFERRED", "2026-03-31")
            replay = client.post(transfer_path, headers=headers, json={
                "expected_current_placement_id": placement_id, "section_id": active_section,
                "effective_on": transfer_date,
            })
            assert replay.status_code == 200 and replay.json()["id"] == winner["id"]
            history = client.get(f"/api/v1/academics/students/{pilot['student']}/placements", headers=headers)
            assert history.status_code == 200 and len(history.json()) == 2
            assert client.get(f"/api/v1/academics/students/{pilot['students'][1][1]}/placements",
                              headers=headers).status_code == 404
            assert client.get(f"/api/v1/academics/sections/{active_section}/roster",
                              headers=pilot["bare_headers"]).status_code == 403
            assert client.get(f"/api/v1/academics/sections/{active_section}/roster?limit=251",
                              headers=headers).status_code == 422
            roster = client.get(f"/api/v1/academics/sections/{active_section}/roster", headers=headers)
            assert roster.status_code == 200 and roster.json()[0]["student_profile_id"] == str(pilot["student"])
            previous_roster = client.get(f"/api/v1/academics/sections/{section_id}/roster", headers=headers)
            assert previous_roster.status_code == 200 and previous_roster.json() == []
            assert owner.exec(text("SELECT count(*) FROM student_section_assignments WHERE enrollment_id=:id AND status='ACTIVE'"),
                              params={"id": enrollment_id}).one()[0] == 1
            assert owner.exec(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id"),
                              params={"id": winner["id"]}).one()[0] == 1
            assert client.post(transfer_path, headers=headers, json={
                "expected_current_placement_id": winner["id"],
                "section_id": next(section for section in target_sections if section != active_section),
                "effective_on": transfer_date,
            }).status_code == 422
            assert client.get(f"/api/v1/academics/sections/{foreign['section']}/roster", headers=headers).status_code == 404
            enrollment_after_transfer = client.get(f"/api/v1/enrollments/{enrollment_id}", headers=headers).json()
            assert enrollment_after_transfer["status"] == "ACTIVE"
            with monkeypatch.context() as patcher:
                patcher.setattr(academic_service, "enqueue_canonical_event", _fail_outbox)
                failed_transfer = client.post(transfer_path, headers=headers, json={
                    "expected_current_placement_id": winner["id"],
                    "section_id": next(section for section in target_sections if section != active_section),
                    "effective_on": "2026-08-01",
                })
            assert failed_transfer.status_code == 500
            assert owner.exec(text("SELECT id FROM student_section_assignments WHERE enrollment_id=:id AND status='ACTIVE'"),
                              params={"id": enrollment_id}).one()[0] == UUID(winner["id"])

            event_count = owner.exec(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=ANY(CAST(:ids AS uuid[]))"),
                                     params={"ids": [period_id, level_id, grade_id, subject_id, section_id, plan_id, curriculum_subject_id, offering_id, assignment_id]}).one()[0]
            audit_count = owner.exec(text("SELECT count(*) FROM audit_logs WHERE entity_id=ANY(CAST(:ids AS uuid[]))"),
                                     params={"ids": [period_id, level_id, grade_id, subject_id, section_id, plan_id, curriculum_subject_id, offering_id, assignment_id]}).one()[0]
            assert event_count == 10 and audit_count == 10
            assert {item["id"] for item in client.get("/api/v1/academics/sections", headers=headers).json()} >= {section_id}
            assert foreign["level"] not in {item["id"] for item in client.get("/api/v1/academics/levels", headers=headers).json()}
            assert {item["id"] for item in client.get("/api/v1/academic-periods", headers=headers).json()} >= {period_id}
            enrollment_detail = client.get(f"/api/v1/enrollments/{enrollment_id}", headers=headers)
            assert enrollment_detail.status_code == 200
            assert enrollment_detail.json()["academic_period_id"] == period_id
            withdrawn = client.patch(f"/api/v1/enrollments/{enrollment_id}/status", headers=headers, json={
                "status": "WITHDRAWN", "expected_updated_at": enrollment_detail.json()["updated_at"],
                "effective_on": "2026-06-01", "reason_code": "SYNTHETIC_TEST",
            })
            assert withdrawn.status_code == 200, withdrawn.text
            closed = client.patch(f"/api/v1/academic-periods/{period_id}/status", headers=headers, json={
                "expected_status": "ACTIVE", "status": "CLOSED",
            })
            assert closed.status_code == 200
            assert client.get(f"/api/v1/enrollments/{enrollment_id}", headers=headers).json()["academic_period_id"] == period_id
        finally:
            ids = [value for values in generated.values() for value in values]
            owner.rollback()
            if offline_capability_touched:
                if offline_capability_before is None:
                    owner.exec(text("DELETE FROM institution_capabilities "
                                    "WHERE institution_id=:institution "
                                    "AND capability_key='teacher.offline_pwa'"),
                               params={"institution": INSTITUTION_ID})
                else:
                    owner.exec(text("UPDATE institution_capabilities SET enabled=:enabled "
                                    "WHERE institution_id=:institution "
                                    "AND capability_key='teacher.offline_pwa'"),
                               params={"institution": INSTITUTION_ID,
                                       "enabled": bool(offline_capability_before[0])})
            for table, key in (("sections", "section"), ("grade_levels", "grade"), ("academic_levels", "level"),
                               ("subjects", "subject"), ("academic_periods", "period")):
                if key in foreign:
                    owner.exec(text(f"DELETE FROM {table} WHERE id=:id"), params={"id": foreign[key]})
            if "campus" in foreign:
                owner.exec(text("DELETE FROM campuses WHERE id=:id"), params={"id": foreign["campus"]})
            if "staff" in foreign:
                owner.exec(text("DELETE FROM staff_profiles WHERE id=:id"), params={"id": foreign["staff"]})
            if "person" in foreign:
                owner.exec(text("DELETE FROM persons WHERE id=:id"), params={"id": foreign["person"]})
            if ids:
                id_params = {"ids": ids}
                owner.exec(text("DELETE FROM audit_logs WHERE entity_id=ANY(CAST(:ids AS uuid[]))"), params=id_params)
                owner.exec(text("DELETE FROM outbox_events WHERE aggregate_id=ANY(CAST(:ids AS uuid[]))"), params=id_params)
            if generated["attendance_records"]:
                owner.exec(text("DELETE FROM attendance_records WHERE id=ANY(CAST(:ids AS uuid[]))"),
                           params={"ids": generated["attendance_records"]})
            if generated["class_sessions"]:
                owner.exec(text("DELETE FROM class_sessions WHERE id=ANY(CAST(:ids AS uuid[]))"),
                           params={"ids": generated["class_sessions"]})
            if generated["attendance_codes"]:
                owner.exec(text("DELETE FROM attendance_codes WHERE id=ANY(CAST(:ids AS uuid[]))"),
                           params={"ids": generated["attendance_codes"]})
            if generated["enrollments"]:
                enrollment_ids = generated["enrollments"]
                placement_ids = generated["student_section_assignments"]
                if placement_ids:
                    owner.exec(text("DELETE FROM audit_logs WHERE entity_id=ANY(CAST(:ids AS uuid[]))"), params={"ids": placement_ids})
                    owner.exec(text("DELETE FROM outbox_events WHERE aggregate_id=ANY(CAST(:ids AS uuid[]))"), params={"ids": placement_ids})
                    owner.exec(text("DELETE FROM student_section_assignments WHERE id=ANY(CAST(:ids AS uuid[]))"), params={"ids": placement_ids})
                owner.exec(text("DELETE FROM audit_logs WHERE entity_type='Enrollment' AND entity_id=ANY(CAST(:ids AS uuid[]))"), params={"ids": enrollment_ids})
                owner.exec(text("DELETE FROM outbox_events WHERE aggregate_type='enrollment' AND aggregate_id=ANY(CAST(:ids AS uuid[]))"), params={"ids": enrollment_ids})
                owner.exec(text("DELETE FROM enrollments WHERE id=ANY(CAST(:ids AS uuid[]))"), params={"ids": enrollment_ids})
            for table in ("teaching_assignments", "course_offerings", "curriculum_subjects", "curriculum_plans", "sections", "grade_levels", "academic_levels", "subjects"):
                values = generated.get(table, [])
                if values:
                    owner.exec(text(f"DELETE FROM {table} WHERE id=ANY(CAST(:ids AS uuid[]))"), params={"ids": values})
            if generated["academic_periods"]:
                owner.exec(text("DELETE FROM academic_periods WHERE id=ANY(CAST(:ids AS uuid[]))"), params={"ids": generated["academic_periods"]})
            owner.commit()
