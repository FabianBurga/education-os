from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session

from app.db.session import engine as app_engine
from app.db.tenant_context import TenantContext, apply_tenant_context
from app.modules.academics.models import (
    AcademicLevel,
    CourseOffering,
    GradeLevel,
    Section,
    StudentSectionAssignment,
    Subject,
    TeachingAssignment,
)
from app.modules.enrollment.models import AcademicPeriod, Enrollment
from app.modules.events.projection_service import ingest_outbox_events
from app.modules.grades.models import GradingPeriod
from app.modules.identity.models import MembershipRole, Role, RolePermission
from app.modules.student_timeline.projector import project_student_timeline
from app.modules.tenancy.models import Campus
from tests.integration.test_m28_student_record_security import (
    INSTITUTION_ID,
    ORG_ID,
    _actor,
    _pilot,
)


def test_assessment_results_are_scoped_versioned_audited_and_projected():
    with _pilot() as pilot:
        owner = pilot["owner"]
        client = pilot["client"]
        manager = pilot["actors"][0]
        teacher = pilot["actors"][3]
        unauthorized = pilot["bare_headers"]
        generated = {
            "academic_period": uuid4(),
            "grading_period": uuid4(),
            "campus": uuid4(),
            "level": uuid4(),
            "grade": uuid4(),
            "section": uuid4(),
            "subject": uuid4(),
            "offering": uuid4(),
            "teacher_assignment": uuid4(),
            "enrollment": uuid4(),
            "placement": uuid4(),
            "category": None,
            "assessment": None,
            "entry": None,
        }
        no_assignment_teacher = None
        projection_actor = None
        projection_role = None
        runtime_connection = None
        runtime_transaction = None
        runtime_session = None
        try:
            # Existing operation permissions are explicitly attached only to this
            # synthetic institutional manager; the teacher uses the existing M10 grant.
            for permission in ("academics.read", "academics.manage"):
                owner.exec(
                    text("""INSERT INTO role_permissions (role_id, permission_id)
                    SELECT :role, id FROM permissions WHERE key=:key
                    ON CONFLICT DO NOTHING"""),
                    params={"role": manager["role_id"], "key": permission},
                )
            no_assignment_teacher = _actor(owner, set(), role_key="TEACHER")
            pilot["actors"].append(no_assignment_teacher)
            projection_actor = _actor(owner, set())
            pilot["actors"].append(projection_actor)
            # M21's INSERT ... RETURNING path also applies its SELECT policy;
            # the isolated tenant has no canonical role rows, so create the
            # recognized role key with only the two policy-required grants.
            projection_role = Role(
                institution_id=INSTITUTION_ID, key="SYSTEM_ADMIN", name="Synthetic M21 projector",
            )
            owner.add(projection_role)
            owner.flush()
            projection_permissions = owner.exec(
                text("SELECT id FROM permissions WHERE key = ANY(CAST(:keys AS text[]))"),
                params={"keys": ["admin.console.access", "student_timeline.read"]},
            ).all()
            owner.add_all([RolePermission(role_id=projection_role.id, permission_id=row[0]) for row in projection_permissions])
            owner.add(MembershipRole(membership_id=projection_actor["membership_id"], role_id=projection_role.id))

            today = date.today()
            academic_period = AcademicPeriod(
                id=generated["academic_period"], organization_id=ORG_ID,
                institution_id=INSTITUTION_ID, code=f"M28-6-{uuid4().hex[:10]}",
                name="Synthetic assessment period", starts_on=today-timedelta(days=30),
                ends_on=today+timedelta(days=30), status="ACTIVE",
            )
            campus = Campus(id=generated["campus"], institution_id=INSTITUTION_ID, name="Synthetic M28-6 campus")
            level = AcademicLevel(
                id=generated["level"], organization_id=ORG_ID, institution_id=INSTITUTION_ID,
                code=f"L-{uuid4().hex[:8]}", name="Synthetic level",
            )
            grade_level = GradeLevel(
                id=generated["grade"], organization_id=ORG_ID, institution_id=INSTITUTION_ID,
                academic_level_id=generated["level"], code=f"G-{uuid4().hex[:8]}", name="Synthetic grade",
            )
            section = Section(
                id=generated["section"], organization_id=ORG_ID, institution_id=INSTITUTION_ID,
                academic_period_id=generated["academic_period"], campus_id=generated["campus"],
                grade_level_id=generated["grade"], code=f"S-{uuid4().hex[:8]}",
                name="Synthetic section", status="ACTIVE",
            )
            subject = Subject(
                id=generated["subject"], organization_id=ORG_ID, institution_id=INSTITUTION_ID,
                code=f"SUB-{uuid4().hex[:8]}", name="Synthetic subject",
            )
            offering = CourseOffering(
                id=generated["offering"], organization_id=ORG_ID, institution_id=INSTITUTION_ID,
                academic_period_id=generated["academic_period"], section_id=generated["section"],
                subject_id=generated["subject"], status="ACTIVE",
            )
            grading_period = GradingPeriod(
                id=generated["grading_period"], organization_id=ORG_ID,
                institution_id=INSTITUTION_ID, academic_period_id=generated["academic_period"],
                code=f"GP-{uuid4().hex[:8]}", name="Synthetic active grading period",
                starts_on=today-timedelta(days=20), ends_on=today+timedelta(days=20),
                status="ACTIVE",
            )
            teaching_assignment = TeachingAssignment(
                id=generated["teacher_assignment"], organization_id=ORG_ID,
                institution_id=INSTITUTION_ID, course_offering_id=generated["offering"],
                staff_profile_id=teacher["staff_id"], starts_on=today-timedelta(days=1),
                ends_on=today+timedelta(days=1),
            )
            enrollment = Enrollment(
                id=generated["enrollment"], organization_id=ORG_ID,
                institution_id=INSTITUTION_ID, student_profile_id=pilot["student"],
                academic_period_id=generated["academic_period"], campus_id=generated["campus"],
                enrollment_number=f"M28-6-{uuid4().hex[:8]}", status="ACTIVE", enrolled_on=today-timedelta(days=1),
            )
            placement = StudentSectionAssignment(
                id=generated["placement"], organization_id=ORG_ID,
                institution_id=INSTITUTION_ID, academic_period_id=generated["academic_period"],
                enrollment_id=generated["enrollment"], section_id=generated["section"],
                status="ACTIVE", assigned_on=today-timedelta(days=1),
            )
            owner.add(academic_period)
            owner.add(campus)
            owner.flush()
            owner.add_all([level, subject, grading_period])
            owner.flush()
            owner.add(grade_level)
            owner.flush()
            owner.add(section)
            owner.flush()
            owner.add(offering)
            owner.flush()
            owner.add_all([teaching_assignment, enrollment])
            owner.flush()
            owner.add(placement)
            owner.commit()

            assert client.get("/api/v1/grades/assessments", headers=unauthorized).status_code == 403
            assert client.get("/api/v1/grades/assessments", headers=pilot["teacher_headers"]).status_code == 403
            assert client.get(
                "/api/v1/grades/assessments", headers=_headers(projection_actor),
            ).status_code == 403
            assert client.get(
                f"/api/v1/teacher/classes/{uuid4()}/assessments",
                headers=pilot["teacher_headers"],
            ).status_code == 403
            assert client.get(
                f"/api/v1/teacher/classes/{generated['offering']}/assessments",
                headers=_headers(no_assignment_teacher),
            ).status_code == 403

            category_response = client.post(
                f"/api/v1/teacher/classes/{generated['offering']}/categories",
                headers=pilot["teacher_headers"],
                json={"grading_period_id": str(generated["grading_period"]), "code": "EXAM", "name": "Exam"},
            )
            assert category_response.status_code == 201, category_response.text
            generated["category"] = category_response.json()["id"]
            assessment_request = {
                "grading_period_id": str(generated["grading_period"]),
                "assessment_category_id": generated["category"],
                "code": "FINAL-EXAM",
                "title": "Synthetic assessment",
                "max_score": 17.25,
                "due_on": today.isoformat(),
                "operation_id": str(uuid4()),
            }
            missing_maximum = {key: value for key, value in assessment_request.items() if key != "max_score"}
            missing_maximum["operation_id"] = str(uuid4())
            assert client.post(
                f"/api/v1/teacher/classes/{generated['offering']}/assessments",
                headers=pilot["teacher_headers"], json=missing_maximum,
            ).status_code == 422
            created = client.post(
                f"/api/v1/teacher/classes/{generated['offering']}/assessments",
                headers=pilot["teacher_headers"], json=assessment_request,
            )
            assert created.status_code == 201, created.text
            generated["assessment"] = created.json()["id"]
            replay_assessment = client.post(
                f"/api/v1/teacher/classes/{generated['offering']}/assessments",
                headers=pilot["teacher_headers"], json=assessment_request,
            )
            assert replay_assessment.status_code == 201
            assert replay_assessment.json()["id"] == generated["assessment"]
            assert owner.exec(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id AND event_type='assessment.created'"), params={"id": generated["assessment"]}).one()[0] == 1

            roster = client.get(
                f"/api/v1/teacher/assessments/{generated['assessment']}/grades",
                headers=pilot["teacher_headers"],
            )
            assert roster.status_code == 200, roster.text
            assert len(roster.json()) == 1
            assert roster.json()[0]["status"] == "PENDING"
            assert roster.json()[0]["revision"] == 0

            result_url = f"/api/v1/teacher/assessments/{generated['assessment']}/grades"
            create_result = {
                "student_section_assignment_id": str(generated["placement"]),
                "score": 0,
                "status": "GRADED",
                "feedback": "private feedback must remain in the result only",
                "expected_revision": 0,
                "operation_id": str(uuid4()),
                "correction_reason": None,
            }
            first = client.put(result_url, headers=pilot["teacher_headers"], json=create_result)
            assert first.status_code == 200, first.text
            generated["entry"] = first.json()["id"]
            assert first.json()["score"] == 0
            assert first.json()["status"] == "GRADED"
            assert first.json()["feedback"] == create_result["feedback"]
            assert first.json()["revision"] == 1
            replay = client.put(result_url, headers=pilot["teacher_headers"], json=create_result)
            assert replay.status_code == 200, replay.text
            assert replay.json()["id"] == generated["entry"]
            assert owner.exec(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id AND event_type='student.grade.recorded'"), params={"id": generated["entry"]}).one()[0] == 1
            audit_metadata = owner.exec(
                text("SELECT metadata_json FROM audit_logs WHERE entity_type='GradeEntry' AND entity_id=:id ORDER BY created_at"),
                params={"id": generated["entry"]},
            ).all()
            assert audit_metadata
            assert all("feedback" not in row[0] for row in audit_metadata)
            assert all("private feedback must remain in the result only" not in str(row[0]) for row in audit_metadata)
            assert audit_metadata[0][0]["new_value"] == {"score": "0.000", "status": "GRADED"}
            feedback_mismatch = {**create_result, "feedback": "different command", "operation_id": create_result["operation_id"]}
            assert client.put(result_url, headers=pilot["teacher_headers"], json=feedback_mismatch).status_code == 409

            invalid = {**create_result, "operation_id": str(uuid4()), "score": 17.251}
            assert client.put(result_url, headers=pilot["teacher_headers"], json=invalid).status_code == 422
            imprecise = {**create_result, "operation_id": str(uuid4()), "score": 1.2345}
            assert client.put(result_url, headers=pilot["teacher_headers"], json=imprecise).status_code == 422
            missing_zero = {**create_result, "operation_id": str(uuid4()), "score": 0, "status": "MISSING"}
            assert client.put(result_url, headers=pilot["teacher_headers"], json=missing_zero).status_code == 422

            publish = {"expected_status": "DRAFT", "status": "PUBLISHED", "operation_id": str(uuid4())}
            assert client.patch(f"/api/v1/teacher/assessments/{generated['assessment']}/status", headers=pilot["teacher_headers"], json=publish).status_code == 200
            stale_status = {"expected_status": "DRAFT", "status": "CLOSED", "operation_id": str(uuid4())}
            assert client.patch(f"/api/v1/teacher/assessments/{generated['assessment']}/status", headers=pilot["teacher_headers"], json=stale_status).status_code == 409

            max_score = {**create_result, "score": 17.25, "expected_revision": 1, "operation_id": str(uuid4()), "correction_reason": "DATA_ENTRY_ERROR"}
            corrected = client.put(result_url, headers=pilot["teacher_headers"], json=max_score)
            assert corrected.status_code == 200, corrected.text
            assert corrected.json()["score"] == 17.25
            assert corrected.json()["revision"] == 2

            def correction(score: float):
                return client.put(result_url, headers=pilot["teacher_headers"], json={
                    **create_result,
                    "score": score,
                    "expected_revision": 2,
                    "operation_id": str(uuid4()),
                    "correction_reason": "EVIDENCE_CORRECTION",
                })

            with ThreadPoolExecutor(max_workers=2) as pool:
                competing = list(pool.map(correction, (8.125, 9.0)))
            assert sorted(response.status_code for response in competing) == [200, 409]

            current = client.get(result_url, headers=pilot["teacher_headers"]).json()[0]
            missing_result = {
                **create_result,
                "score": None,
                "status": "MISSING",
                "expected_revision": current["revision"],
                "operation_id": str(uuid4()),
                "correction_reason": "EVIDENCE_CORRECTION",
            }
            missing = client.put(result_url, headers=pilot["teacher_headers"], json=missing_result)
            assert missing.status_code == 200, missing.text
            assert missing.json()["score"] is None
            assert missing.json()["status"] == "MISSING"
            assert missing.json()["revision"] == current["revision"] + 1

            history = client.get(
                f"/api/v1/teacher/assessments/{generated['assessment']}/grades/{generated['placement']}/history",
                headers=pilot["teacher_headers"],
            )
            assert history.status_code == 200, history.text
            assert len(history.json()) == 4
            assert history.json()[0]["previous_value"] is None
            assert history.json()[0]["new_value"]["score"] == "0.000"
            assert history.json()[1]["new_value"]["score"] == "17.250"
            assert history.json()[-1]["new_value"]["status"] == "MISSING"
            assert history.json()[-1]["new_value"]["score"] is None
            assert history.json()[-1]["actor_user_id"] == str(teacher["user_id"])

            close = {"expected_status": "PUBLISHED", "status": "CLOSED", "operation_id": str(uuid4())}
            assert client.patch(f"/api/v1/teacher/assessments/{generated['assessment']}/status", headers=pilot["teacher_headers"], json=close).status_code == 200
            assert client.put(result_url, headers=pilot["teacher_headers"], json={
                **missing_result, "expected_revision": missing.json()["revision"], "operation_id": str(uuid4()),
            }).status_code == 409
            archive = {"expected_status": "CLOSED", "status": "ARCHIVED", "operation_id": str(uuid4())}
            assert client.patch(f"/api/v1/teacher/assessments/{generated['assessment']}/status", headers=pilot["teacher_headers"], json=archive).status_code == 200

            manager_assessments = client.get("/api/v1/grades/assessments", headers=pilot["authorized_headers"])
            assert manager_assessments.status_code == 200
            assert generated["assessment"] in {item["id"] for item in manager_assessments.json()}
            cross_scope = client.get(f"/api/v1/grades/assessments/{uuid4()}/entries", headers=pilot["authorized_headers"])
            assert cross_scope.status_code == 404

            runtime_connection = app_engine.connect()
            runtime_transaction = runtime_connection.begin()
            runtime_session = Session(bind=runtime_connection, join_transaction_mode="create_savepoint")
            apply_tenant_context(
                runtime_session,
                TenantContext(organization_id=ORG_ID, institution_id=INSTITUTION_ID, user_id=projection_actor["user_id"]),
            )
            ingested = ingest_outbox_events(runtime_session, institution_id=INSTITUTION_ID, limit=1000)
            assert ingested >= 1
            assert runtime_session.exec(text("""
                SELECT current_setting('app.organization_id', true)=:org_id,
                       current_setting('app.institution_id', true)=:institution_id,
                       current_setting('app.user_id', true)=:user_id,
                       EXISTS (SELECT 1 FROM memberships m
                           JOIN membership_roles mr ON mr.membership_id=m.id
                           JOIN role_permissions rp ON rp.role_id=mr.role_id
                           JOIN permissions p ON p.id=rp.permission_id
                           WHERE m.user_id=CAST(:user_id AS uuid)
                             AND m.institution_id=CAST(:institution_id AS uuid)
                             AND m.status='ACTIVE' AND p.key='admin.console.access')
            """), params={"org_id": str(ORG_ID), "institution_id": str(INSTITUTION_ID), "user_id": str(projection_actor["user_id"])}).one() == (True, True, True, True)
            projected = project_student_timeline(
                runtime_session, organization_id=ORG_ID, institution_id=INSTITUTION_ID, limit=5000,
            )
            assert projected.inserted >= 1
            timeline = runtime_session.exec(text("""SELECT event_type, context_json
                FROM student_timeline_entries
                WHERE institution_id=:institution_id AND source_aggregate_id=:entry_id
                  AND event_type IN ('student.grade.recorded','student.grade.updated')
                ORDER BY ledger_position"""), params={"institution_id": INSTITUTION_ID, "entry_id": generated["entry"]}).all()
            assert len(timeline) == 4
            assert timeline[0][0] == "student.grade.recorded"
            assert timeline[-1][0] == "student.grade.updated"
            assert all("feedback" not in row[1] for row in timeline)

            # Direct INSERT attempts are deliberately negative-only. They prove
            # that M10 teachers and principals without the projector role cannot
            # turn the timeline read model into a second write authority.
            template = dict(runtime_session.exec(text("""
                SELECT organization_id, institution_id, student_profile_id,
                       ledger_event_id, ledger_position, event_type, event_version,
                       category, importance, sensitivity, title, summary,
                       source_aggregate_type, source_aggregate_id, actor_user_id,
                       correlation_id, causation_id, context_json::text AS context_json,
                       occurred_at, recorded_at
                FROM student_timeline_entries
                WHERE institution_id=:institution_id
                  AND source_aggregate_id=:entry_id
                  AND event_type='student.grade.recorded'
                LIMIT 1
            """), params={"institution_id": INSTITUTION_ID, "entry_id": generated["entry"]}).mappings().one())
            attempt_insert = text("""
                INSERT INTO student_timeline_entries (
                    id, organization_id, institution_id, student_profile_id,
                    ledger_event_id, ledger_position, event_type, event_version,
                    category, importance, sensitivity, title, summary,
                    source_aggregate_type, source_aggregate_id, actor_user_id,
                    correlation_id, causation_id, context_json, occurred_at,
                    recorded_at, projected_at
                ) VALUES (
                    CAST(:id AS uuid), CAST(:organization_id AS uuid),
                    CAST(:institution_id AS uuid), CAST(:student_profile_id AS uuid),
                    CAST(:ledger_event_id AS uuid), :ledger_position, :event_type,
                    :event_version, :category, :importance, :sensitivity, :title,
                    :summary, :source_aggregate_type, CAST(:source_aggregate_id AS uuid),
                    CAST(:actor_user_id AS uuid), CAST(:correlation_id AS uuid),
                    CAST(:causation_id AS uuid), CAST(:context_json AS jsonb),
                    :occurred_at, :recorded_at, NOW()
                )
            """)

            def assert_rls_denies(*, principal_id, context_org, context_institution, row_overrides=None):
                apply_tenant_context(runtime_session, TenantContext(
                    organization_id=context_org,
                    institution_id=context_institution,
                    user_id=principal_id,
                ))
                params = {**template, **(row_overrides or {}), "id": str(uuid4())}
                with pytest.raises(DBAPIError) as denied:
                    with runtime_session.begin_nested():
                        runtime_session.exec(attempt_insert, params=params)
                assert getattr(denied.value.orig, "sqlstate", None) == "42501"

            assert_rls_denies(
                principal_id=teacher["user_id"], context_org=ORG_ID,
                context_institution=INSTITUTION_ID,
            )
            assert_rls_denies(
                principal_id=pilot["actors"][2]["user_id"], context_org=ORG_ID,
                context_institution=INSTITUTION_ID,
            )
            foreign_institution = owner.exec(
                text("SELECT id, organization_id FROM institutions WHERE id<>:id ORDER BY id LIMIT 1"),
                params={"id": INSTITUTION_ID},
            ).one()
            assert_rls_denies(
                principal_id=projection_actor["user_id"], context_org=ORG_ID,
                context_institution=INSTITUTION_ID,
                row_overrides={
                    "organization_id": foreign_institution[1],
                    "institution_id": foreign_institution[0],
                },
            )
            assert_rls_denies(
                principal_id=projection_actor["user_id"], context_org=ORG_ID,
                context_institution=foreign_institution[0],
            )
        finally:
            if runtime_session is not None:
                runtime_session.close()
            if runtime_transaction is not None:
                runtime_transaction.rollback()
            if runtime_connection is not None:
                runtime_connection.close()
            owner.rollback()
            if projection_role is not None:
                owner.exec(text("DELETE FROM membership_roles WHERE role_id=:id"), params={"id": projection_role.id})
                owner.exec(text("DELETE FROM role_permissions WHERE role_id=:id"), params={"id": projection_role.id})
                owner.exec(text("DELETE FROM roles WHERE id=:id"), params={"id": projection_role.id})
            ids = [str(generated[key]) for key in ("entry", "assessment", "category") if generated[key] is not None]
            if ids:
                owner.exec(text("DELETE FROM audit_logs WHERE entity_id=ANY(CAST(:ids AS uuid[]))"), params={"ids": ids})
                owner.exec(text("DELETE FROM outbox_events WHERE aggregate_id=ANY(CAST(:ids AS uuid[]))"), params={"ids": ids})
            owner.exec(text("DELETE FROM grade_entries WHERE assessment_id=:id"), params={"id": generated["assessment"]}) if generated["assessment"] else None
            owner.exec(text("DELETE FROM assessments WHERE id=:id"), params={"id": generated["assessment"]}) if generated["assessment"] else None
            owner.exec(text("DELETE FROM assessment_categories WHERE id=:id"), params={"id": generated["category"]}) if generated["category"] else None
            owner.exec(text("DELETE FROM student_section_assignments WHERE id=:id"), params={"id": generated["placement"]})
            owner.exec(text("DELETE FROM enrollments WHERE id=:id"), params={"id": generated["enrollment"]})
            owner.exec(text("DELETE FROM teaching_assignments WHERE id=:id"), params={"id": generated["teacher_assignment"]})
            owner.exec(text("DELETE FROM course_offerings WHERE id=:id"), params={"id": generated["offering"]})
            owner.exec(text("DELETE FROM sections WHERE id=:id"), params={"id": generated["section"]})
            owner.exec(text("DELETE FROM grade_levels WHERE id=:id"), params={"id": generated["grade"]})
            owner.exec(text("DELETE FROM academic_levels WHERE id=:id"), params={"id": generated["level"]})
            owner.exec(text("DELETE FROM subjects WHERE id=:id"), params={"id": generated["subject"]})
            owner.exec(text("DELETE FROM grading_periods WHERE id=:id"), params={"id": generated["grading_period"]})
            owner.exec(text("DELETE FROM academic_periods WHERE id=:id"), params={"id": generated["academic_period"]})
            owner.exec(text("DELETE FROM campuses WHERE id=:id"), params={"id": generated["campus"]})
            owner.commit()


def _headers(actor):
    from tests.integration.test_m28_student_record_security import _headers as headers_for

    return headers_for(actor)
