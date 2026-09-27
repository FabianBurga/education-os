from uuid import UUID, uuid4

from sqlalchemy import text

from app.modules.academics import service as academic_service
from app.modules.families.models import StaffProfile
from app.modules.identity.models import Membership, MembershipRole, Person, Role, UserAccount
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
        }
        foreign: dict[str, str] = {}
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

            for key in ("academics.read", "academics.manage", "academics.assign"):
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
            assignment_response = client.post("/api/v1/academics/teaching-assignments", headers=headers, json={
                "course_offering_id": offering_id, "staff_profile_id": staff_id,
                "starts_on": "2026-01-01", "ends_on": "2027-12-31",
            })
            assert assignment_response.status_code == 201, assignment_response.text
            assignment_id = assignment_response.json()["id"]
            generated["teaching_assignments"].append(assignment_id)
            assert client.post("/api/v1/academics/teaching-assignments", headers=headers, json={
                "course_offering_id": offering_id, "staff_profile_id": foreign["staff"],
            }).status_code == 404
            assert client.get("/api/v1/academics/levels", headers=pilot["teacher_headers"]).status_code == 403
            assert client.post("/api/v1/academics/levels", headers=pilot["teacher_headers"], json={
                "code": "TEACHER", "name": "No", "sort_order": 1,
            }).status_code == 403

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
            if generated["enrollments"]:
                enrollment_ids = generated["enrollments"]
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
