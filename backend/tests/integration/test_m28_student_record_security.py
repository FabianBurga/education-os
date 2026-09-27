"""Application-role HTTP proofs for the M28-1 student record boundary."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_session
from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import engine as app_engine
from app.main import app
from app.modules.families.models import StaffProfile
from app.modules.identity.models import (
    Membership,
    MembershipRole,
    Person,
    Role,
    RolePermission,
    UserAccount,
)
from app.modules.integrations.models import IntegrationConnector, IntegrationRun, IntegrationRunItem
from app.modules.integrations.service import apply_csv_student_enrollment
from app.modules.students.models import StudentProfile

ORG_ID = UUID("d6edc12e-39a5-4a65-b07c-52d8a364acc1")
INSTITUTION_ID = UUID("07b4ca2d-28b8-49ed-a56a-5423ce208583")


def _actor(owner: Session, permissions: set[str], role_key: str = "SYSTEM_ADMIN") -> dict[str, UUID | bool]:
    nonce = uuid4().hex
    person = Person(organization_id=ORG_ID, given_names="Synthetic", family_names=f"M28 actor {nonce[:8]}")
    owner.add(person)
    owner.flush()
    user = UserAccount(person_id=person.id, login_email=f"m28-{nonce}@test.invalid", password_hash="not-a-credential")
    if role_key == "TEACHER":
        role_id = owner.exec(
            text("SELECT id FROM roles WHERE institution_id=:institution_id AND key='TEACHER' LIMIT 1"),
            params={"institution_id": INSTITUTION_ID},
        ).one()[0]
        role_owned = False
    else:
        role = Role(institution_id=INSTITUTION_ID, key=f"{role_key}_{nonce[:10]}", name="M28 synthetic test actor")
        owner.add(role)
        owner.flush()
        role_id = role.id
        role_owned = True
    owner.add(user)
    owner.flush()
    membership = Membership(user_id=user.id, institution_id=INSTITUTION_ID, status="ACTIVE")
    owner.add(membership)
    staff = StaffProfile(organization_id=ORG_ID, institution_id=INSTITUTION_ID, person_id=person.id, staff_code=f"M28-{nonce[:8]}")
    owner.add(staff)
    owner.flush()
    if permissions:
        rows = owner.exec(
            text("SELECT id FROM permissions WHERE key = ANY(CAST(:keys AS text[]))"),
            params={"keys": list(permissions)},
        ).all()
        assert len(rows) == len(permissions)
        owner.add_all([RolePermission(role_id=role_id, permission_id=row[0]) for row in rows])
    owner.add(MembershipRole(membership_id=membership.id, role_id=role_id))
    owner.flush()
    return {"user_id": user.id, "person_id": person.id, "role_id": role_id, "role_owned": role_owned, "membership_id": membership.id, "staff_id": staff.id}


def _person_student(owner: Session, *, institution_id: UUID = INSTITUTION_ID, organization_id: UUID = ORG_ID, code: str = "SYN-M28") -> tuple[UUID, UUID]:
    person = Person(organization_id=organization_id, given_names="Synthetic Student", family_names=f"M28 {uuid4().hex[:8]}")
    owner.add(person)
    owner.flush()
    student = StudentProfile(organization_id=organization_id, institution_id=institution_id, person_id=person.id, student_code=code)
    owner.add(student)
    owner.flush()
    return person.id, student.id


def _cleanup(
    owner: Session,
    actors: list[dict[str, UUID]],
    students: list[tuple[UUID, UUID]],
    extra_people: list[UUID],
    period_ids: list[UUID],
    campus_ids: list[UUID],
    integration_run_ids: list[UUID],
    connector_ids: list[UUID],
) -> None:
    owner.rollback()
    if connector_ids:
        owner.exec(
            text("DELETE FROM integration_external_student_refs WHERE connector_id = ANY(CAST(:ids AS uuid[]))"),
            params={"ids": [str(value) for value in connector_ids]},
        )
    if integration_run_ids:
        ids = [str(value) for value in integration_run_ids]
        owner.exec(text("DELETE FROM integration_run_events WHERE run_id = ANY(CAST(:ids AS uuid[]))"), params={"ids": ids})
        owner.exec(text("DELETE FROM integration_run_items WHERE run_id = ANY(CAST(:ids AS uuid[]))"), params={"ids": ids})
        owner.exec(text("DELETE FROM integration_runs WHERE id = ANY(CAST(:ids AS uuid[]))"), params={"ids": ids})
        owner.exec(text("DELETE FROM audit_logs WHERE entity_id = ANY(CAST(:ids AS uuid[]))"), params={"ids": ids})
    if connector_ids:
        ids = [str(value) for value in connector_ids]
        owner.exec(text("DELETE FROM integration_connectors WHERE id = ANY(CAST(:ids AS uuid[]))"), params={"ids": ids})
    student_ids = [str(student_id) for _, student_id in students]
    if student_ids:
        enrollment_ids = [str(row[0]) for row in owner.exec(
            text("SELECT id FROM enrollments WHERE student_profile_id = ANY(CAST(:ids AS uuid[]))"),
            params={"ids": student_ids},
        ).all()]
        if enrollment_ids:
            owner.exec(text("DELETE FROM audit_logs WHERE entity_type='Enrollment' AND entity_id = ANY(CAST(:ids AS uuid[]))"), params={"ids": enrollment_ids})
            owner.exec(text("DELETE FROM outbox_events WHERE aggregate_type='enrollment' AND aggregate_id = ANY(CAST(:ids AS uuid[]))"), params={"ids": enrollment_ids})
            owner.exec(text("DELETE FROM student_section_assignments WHERE enrollment_id = ANY(CAST(:ids AS uuid[]))"), params={"ids": enrollment_ids})
            owner.exec(text("DELETE FROM enrollments WHERE id = ANY(CAST(:ids AS uuid[]))"), params={"ids": enrollment_ids})
        owner.exec(text("DELETE FROM audit_logs WHERE entity_id = ANY(CAST(:ids AS uuid[]))"), params={"ids": student_ids})
        owner.exec(text("DELETE FROM outbox_events WHERE aggregate_id = ANY(CAST(:ids AS uuid[]))"), params={"ids": student_ids})
        owner.exec(text("DELETE FROM student_profiles WHERE id = ANY(CAST(:ids AS uuid[]))"), params={"ids": student_ids})
    if period_ids:
        owner.exec(text("DELETE FROM academic_periods WHERE id = ANY(CAST(:ids AS uuid[]))"), params={"ids": [str(value) for value in period_ids]})
    if campus_ids:
        owner.exec(text("DELETE FROM campuses WHERE id = ANY(CAST(:ids AS uuid[]))"), params={"ids": [str(value) for value in campus_ids]})
    actor_user_ids = [str(actor["user_id"]) for actor in actors]
    if actor_user_ids:
        owner.exec(text("DELETE FROM audit_logs WHERE actor_user_id = ANY(CAST(:ids AS uuid[]))"), params={"ids": actor_user_ids})
    for actor in actors:
        params = {key: str(value) for key, value in actor.items()}
        owner.exec(text("DELETE FROM membership_roles WHERE membership_id = CAST(:membership_id AS uuid)"), params=params)
        if actor["role_owned"]:
            owner.exec(text("DELETE FROM role_permissions WHERE role_id = CAST(:role_id AS uuid)"), params=params)
        owner.exec(text("DELETE FROM staff_profiles WHERE id = CAST(:staff_id AS uuid)"), params=params)
        owner.exec(text("DELETE FROM memberships WHERE id = CAST(:membership_id AS uuid)"), params=params)
        if actor["role_owned"]:
            owner.exec(text("DELETE FROM roles WHERE id = CAST(:role_id AS uuid)"), params=params)
        owner.exec(text("DELETE FROM user_accounts WHERE id = CAST(:user_id AS uuid)"), params=params)
    person_ids = (
        [str(actor["person_id"]) for actor in actors]
        + [str(person_id) for person_id, _student_id in students]
        + [str(person_id) for person_id in extra_people]
    )
    if person_ids:
        owner.exec(text("DELETE FROM audit_logs WHERE entity_id = ANY(CAST(:ids AS uuid[]))"), params={"ids": person_ids})
        owner.exec(text("DELETE FROM persons WHERE id = ANY(CAST(:ids AS uuid[]))"), params={"ids": person_ids})
    owner.commit()


@contextmanager
def _pilot():
    assert settings.OWNER_DATABASE_URL
    owner_engine = create_engine(settings.OWNER_DATABASE_URL, pool_pre_ping=True)
    owner = Session(owner_engine)
    actors: list[dict[str, UUID]] = []
    students: list[tuple[UUID, UUID]] = []
    extra_people: list[UUID] = []
    period_ids: list[UUID] = []
    campus_ids: list[UUID] = []
    integration_run_ids: list[UUID] = []
    connector_ids: list[UUID] = []
    try:
        assert owner.exec(text("SELECT 1 FROM institutions WHERE id=:id AND organization_id=:org"), params={"id": INSTITUTION_ID, "org": ORG_ID}).first()
        authorized = _actor(owner, {"students.read", "students.manage", "enrollments.read", "enrollments.manage", "integrations.run", "admin.people.manage"})
        student_reader = _actor(owner, {"students.read"})
        bare_admin = _actor(owner, set())
        teacher = _actor(owner, set(), role_key="TEACHER")
        actors.extend((authorized, student_reader, bare_admin, teacher))
        local_person, local_student = _person_student(owner)
        students.append((local_person, local_student))
        foreign = owner.exec(
            text("SELECT id, organization_id FROM institutions WHERE id <> :id ORDER BY id LIMIT 1"),
            params={"id": INSTITUTION_ID},
        ).first()
        assert foreign is not None
        foreign_person, foreign_student = _person_student(owner, institution_id=foreign[0], organization_id=foreign[1], code="FOREIGN-M28")
        students.append((foreign_person, foreign_student))
        owner.commit()

        def session_dependency():
            with Session(app_engine) as app_session:
                yield app_session

        app.dependency_overrides[get_session] = session_dependency
        try:
            yield {
                "owner": owner,
                "actors": actors,
                "students": students,
                "person": local_person,
                "student": local_student,
                "extra_people": extra_people,
                "period_ids": period_ids,
                "campus_ids": campus_ids,
                "integration_run_ids": integration_run_ids,
                "connector_ids": connector_ids,
                "authorized_headers": _headers(authorized),
                "bare_headers": _headers(bare_admin),
                "student_reader_headers": _headers(student_reader),
                "teacher_headers": _headers(teacher),
                "client": TestClient(app, raise_server_exceptions=False),
            }
        finally:
            app.dependency_overrides.pop(get_session, None)
    finally:
        _cleanup(owner, actors, students, extra_people, period_ids, campus_ids, integration_run_ids, connector_ids)
        owner.close()
        owner_engine.dispose()


def _headers(actor: dict[str, UUID]) -> dict[str, str]:
    token = create_access_token(user_id=actor["user_id"], organization_id=ORG_ID, institution_id=INSTITUTION_ID)
    return {"Authorization": f"Bearer {token}"}


def test_student_record_http_scope_permissions_idor_and_mass_assignment() -> None:
    with _pilot() as pilot:
        client = pilot["client"]
        local_id, foreign_id = (str(row[1]) for row in pilot["students"])
        response = client.get("/api/v1/students/records", headers=pilot["authorized_headers"])
        assert response.status_code == 200
        visible_student_ids = {item["id"] for item in response.json()["items"]}
        assert local_id in visible_student_ids
        assert foreign_id not in visible_student_ids
        assert "Synthetic Student" in next(item["display_name"] for item in response.json()["items"] if item["id"] == local_id)
        legacy_list = client.get("/api/v1/students?limit=10", headers=pilot["authorized_headers"])
        assert legacy_list.status_code == 200
        legacy_student_ids = {item["id"] for item in legacy_list.json()}
        assert local_id in legacy_student_ids
        assert foreign_id not in legacy_student_ids
        local_record = next(item for item in legacy_list.json() if item["id"] == local_id)
        assert set(local_record) == {"id", "display_name", "student_code", "status", "updated_at"}
        assert client.get("/api/v1/students", headers=pilot["bare_headers"]).status_code == 403
        assert client.get("/api/v1/students/records", headers=pilot["teacher_headers"]).status_code == 403
        foreign_response = client.get(f"/api/v1/students/{foreign_id}", headers=pilot["authorized_headers"])
        assert foreign_response.status_code == 404
        assert "FOREIGN-M28" not in foreign_response.text
        foreign_cursor = client.get(
            f"/api/v1/students/records?cursor={foreign_id}",
            headers=pilot["authorized_headers"],
        )
        assert foreign_cursor.status_code == 404
        foreign_institution = pilot["owner"].exec(
            text("SELECT id, organization_id FROM institutions WHERE id <> :id ORDER BY id LIMIT 1"),
            params={"id": INSTITUTION_ID},
        ).one()
        foreign_token = create_access_token(
            user_id=pilot["actors"][0]["user_id"],
            organization_id=foreign_institution[1],
            institution_id=foreign_institution[0],
        )
        assert client.get(
            "/api/v1/students/records",
            headers={"Authorization": f"Bearer {foreign_token}"},
        ).status_code == 403
        bad_update = client.patch(
            f"/api/v1/students/{local_id}",
            headers=pilot["authorized_headers"],
            json={"student_code": "FORGED", "institution_id": str(uuid4()), "expected_updated_at": datetime.now(UTC).isoformat()},
        )
        assert bad_update.status_code == 422
        null_status = client.patch(
            f"/api/v1/students/{local_id}",
            headers=pilot["authorized_headers"],
            json={"status": None, "expected_updated_at": datetime.now(UTC).isoformat()},
        )
        assert null_status.status_code == 422
        unauthorized_update = client.patch(
            f"/api/v1/students/{local_id}",
            headers=pilot["bare_headers"],
            json={"student_code": "FORGED", "expected_updated_at": datetime.now(UTC).isoformat()},
        )
        assert unauthorized_update.status_code == 403
        unauthorized_create = client.post(
            "/api/v1/students",
            headers=pilot["bare_headers"],
            json={"person_id": str(pilot["person"]), "student_code": "SYN-M28"},
        )
        assert unauthorized_create.status_code == 403
        injected_create = client.post(
            "/api/v1/students",
            headers=pilot["authorized_headers"],
            json={"person_id": str(pilot["person"]), "student_code": "SYN-M28", "institution_id": str(INSTITUTION_ID)},
        )
        assert injected_create.status_code == 422

        detail = client.get(f"/api/v1/students/{local_id}", headers=pilot["authorized_headers"])
        original_updated_at = detail.json()["updated_at"]
        update = client.patch(
            f"/api/v1/students/{local_id}",
            headers=pilot["authorized_headers"],
            json={"student_code": "SYN-M28-EDITED", "expected_updated_at": original_updated_at},
        )
        assert update.status_code == 200
        assert update.json()["student_code"] == "SYN-M28-EDITED"
        stale = client.patch(
            f"/api/v1/students/{local_id}",
            headers=pilot["authorized_headers"],
            json={"student_code": "SYN-M28-STALE", "expected_updated_at": original_updated_at},
        )
        assert stale.status_code == 409


def test_student_create_retry_is_idempotent_and_audit_failure_rolls_back(monkeypatch) -> None:
    with _pilot() as pilot:
        client = pilot["client"]
        owner = pilot["owner"]
        new_person = Person(organization_id=ORG_ID, given_names="Synthetic Create", family_names=f"M28 {uuid4().hex[:8]}")
        owner.add(new_person)
        owner.commit()
        pilot["extra_people"].append(new_person.id)
        code = f"SYN-M28-{uuid4().hex[:8]}"
        body = {"person_id": str(new_person.id), "student_code": code}
        first = client.post("/api/v1/students", headers=pilot["authorized_headers"], json=body)
        second = client.post("/api/v1/students", headers=pilot["authorized_headers"], json=body)
        assert first.status_code == 201
        assert second.status_code == 200
        assert second.headers.get("Idempotent-Replay") == "true"
        profile_id = first.json()["id"]
        assert set(first.json()) == {"id", "display_name", "student_code", "status", "updated_at"}
        pilot["students"].append((new_person.id, UUID(profile_id)))
        assert owner.exec(text("SELECT count(*) FROM student_profiles WHERE id=CAST(:id AS uuid)"), params={"id": profile_id}).one()[0] == 1
        assert owner.exec(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=CAST(:id AS uuid) AND event_type='student.profile.created'"), params={"id": profile_id}).one()[0] == 1
        assert owner.exec(text("SELECT count(*) FROM audit_logs WHERE entity_id=CAST(:id AS uuid) AND action='STUDENT_PROFILE_CREATED'"), params={"id": profile_id}).one()[0] == 1

        rollback_person = Person(organization_id=ORG_ID, given_names="Synthetic Rollback", family_names="M28")
        owner.add(rollback_person)
        owner.commit()
        pilot["extra_people"].append(rollback_person.id)
        before_events = owner.exec(text("SELECT count(*) FROM outbox_events WHERE event_type='student.profile.created'")).one()[0]
        before_audits = owner.exec(text("SELECT count(*) FROM audit_logs WHERE action='STUDENT_PROFILE_CREATED'")).one()[0]

        def fail_audit(*args, **kwargs):
            raise RuntimeError("synthetic audit failure")

        monkeypatch.setattr("app.modules.students.service.record_audit", fail_audit)
        before_update_events = owner.exec(
            text("SELECT count(*) FROM outbox_events WHERE aggregate_id=CAST(:id AS uuid) AND event_type='student.profile.updated'"),
            params={"id": profile_id},
        ).one()[0]
        failed_update = client.patch(
            f"/api/v1/students/{profile_id}",
            headers=pilot["authorized_headers"],
            json={"student_code": f"{code}-FAILED", "expected_updated_at": first.json()["updated_at"]},
        )
        assert failed_update.status_code == 500
        owner.rollback()
        assert owner.exec(text("SELECT student_code FROM student_profiles WHERE id=CAST(:id AS uuid)"), params={"id": profile_id}).one()[0] == code
        assert owner.exec(
            text("SELECT count(*) FROM outbox_events WHERE aggregate_id=CAST(:id AS uuid) AND event_type='student.profile.updated'"),
            params={"id": profile_id},
        ).one()[0] == before_update_events

        failure = client.post(
            "/api/v1/students",
            headers=pilot["authorized_headers"],
            json={"person_id": str(rollback_person.id), "student_code": "SYN-ROLLBACK"},
        )
        assert failure.status_code == 500
        assert "synthetic audit failure" not in failure.text
        owner.rollback()
        assert owner.exec(text("SELECT count(*) FROM student_profiles WHERE person_id=:id"), params={"id": rollback_person.id}).one()[0] == 0
        assert owner.exec(text("SELECT count(*) FROM outbox_events WHERE event_type='student.profile.created'")).one()[0] == before_events
        assert owner.exec(text("SELECT count(*) FROM audit_logs WHERE action='STUDENT_PROFILE_CREATED'")).one()[0] == before_audits


def test_enrollment_lifecycle_is_scoped_versioned_and_audited(monkeypatch) -> None:
    with _pilot() as pilot:
        owner = pilot["owner"]
        period_id = uuid4()
        campus_id = uuid4()
        owner.exec(text("INSERT INTO campuses (id, institution_id, name, created_at) VALUES (:id, :institution, :name, CURRENT_TIMESTAMP)"),
                   params={"id": campus_id, "institution": INSTITUTION_ID, "name": f"Synthetic M28-2 {campus_id.hex[:8]}"})
        pilot["campus_ids"].append(campus_id)
        pilot["period_ids"].append(period_id)
        owner.exec(text("""INSERT INTO academic_periods
            (id, organization_id, institution_id, code, name, starts_on, ends_on, status, created_at)
            VALUES (:id, :org, :institution, :code, 'Synthetic M28-2', '2025-01-01', '2030-12-31', 'ACTIVE', CURRENT_TIMESTAMP)"""),
            params={"id": period_id, "org": ORG_ID, "institution": INSTITUTION_ID, "code": f"M28-2-{period_id.hex[:12]}"})
        foreign_institution = owner.exec(
            text("SELECT id, organization_id FROM institutions WHERE id <> :id ORDER BY id LIMIT 1"),
            params={"id": INSTITUTION_ID},
        ).one()
        foreign_period_id, foreign_campus_id, foreign_enrollment_id = uuid4(), uuid4(), uuid4()
        pilot["period_ids"].append(foreign_period_id)
        pilot["campus_ids"].append(foreign_campus_id)
        owner.exec(text("""INSERT INTO academic_periods
            (id, organization_id, institution_id, code, name, starts_on, ends_on, status, created_at)
            VALUES (:id, :org, :institution, :code, 'Foreign synthetic period', '2025-01-01', '2030-12-31', 'ACTIVE', CURRENT_TIMESTAMP)"""),
            params={"id": foreign_period_id, "org": foreign_institution[1], "institution": foreign_institution[0], "code": f"FOREIGN-{foreign_period_id.hex[:10]}"})
        owner.exec(text("INSERT INTO campuses (id, institution_id, name, created_at) VALUES (:id, :institution, 'Foreign synthetic campus', CURRENT_TIMESTAMP)"),
                   params={"id": foreign_campus_id, "institution": foreign_institution[0]})
        owner.exec(text("""INSERT INTO enrollments
            (id, organization_id, institution_id, student_profile_id, academic_period_id, campus_id, status, enrolled_on, created_at, updated_at)
            VALUES (:id, :org, :institution, :student, :period, :campus, 'ACTIVE', '2026-01-10', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""),
            params={"id": foreign_enrollment_id, "org": foreign_institution[1], "institution": foreign_institution[0],
                    "student": pilot["students"][1][1], "period": foreign_period_id, "campus": foreign_campus_id})
        owner.commit()
        client = pilot["client"]
        student_id = pilot["students"][0][1]
        body = {
            "student_profile_id": str(student_id), "academic_period_id": str(period_id),
            "campus_id": str(campus_id), "enrollment_number": "SYNTHETIC-ENR-01",
            "status": "ACTIVE", "enrolled_on": "2026-01-10",
        }
        create = client.post("/api/v1/enrollments", headers=pilot["authorized_headers"], json=body)
        assert create.status_code == 201, create.text
        enrollment = create.json()
        enrollment_id = UUID(enrollment["id"])
        out_of_period = client.post("/api/v1/enrollments", headers=pilot["authorized_headers"], json={**body, "enrolled_on": "2031-01-01"})
        assert out_of_period.status_code == 422
        replay = client.post("/api/v1/enrollments", headers=pilot["authorized_headers"], json=body)
        assert replay.status_code == 201
        assert replay.json()["id"] == enrollment["id"]
        assert owner.exec(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id AND event_type='student.enrollment.created'"), params={"id": enrollment_id}).one()[0] == 1
        assert owner.exec(text("SELECT count(*) FROM audit_logs WHERE entity_id=:id AND action='STUDENT_ENROLLMENT_CREATED'"), params={"id": enrollment_id}).one()[0] == 1
        owner.exec(text("UPDATE academic_periods SET status='CLOSED' WHERE id=:id"), params={"id": period_id})
        owner.commit()
        closed_period_change = client.patch(
            f"/api/v1/enrollments/{enrollment_id}/status", headers=pilot["authorized_headers"],
            json={"status": "WITHDRAWN", "expected_updated_at": enrollment["updated_at"], "effective_on": "2026-05-20", "reason_code": "STUDENT_REQUEST"},
        )
        assert closed_period_change.status_code == 409
        owner.exec(text("UPDATE academic_periods SET status='ACTIVE' WHERE id=:id"), params={"id": period_id})
        owner.commit()

        def fail_enrollment_audit(*args, **kwargs):
            raise RuntimeError("synthetic enrollment audit failure")

        with monkeypatch.context() as patcher:
            patcher.setattr("app.modules.enrollment.service.record_audit", fail_enrollment_audit)
            failed_withdrawal = client.patch(
                f"/api/v1/enrollments/{enrollment_id}/status", headers=pilot["authorized_headers"],
                json={"status": "WITHDRAWN", "expected_updated_at": enrollment["updated_at"], "effective_on": "2026-05-20", "reason_code": "STUDENT_REQUEST"},
            )
        assert failed_withdrawal.status_code == 500
        owner.rollback()
        assert owner.exec(text("SELECT status FROM enrollments WHERE id=:id"), params={"id": enrollment_id}).one()[0] == "ACTIVE"
        assert owner.exec(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id AND event_type='student.enrollment.status_changed'"), params={"id": enrollment_id}).one()[0] == 0
        available_period_ids = {
            period["id"] for period in client.get("/api/v1/enrollments/options", headers=pilot["authorized_headers"]).json()["periods"]
        }
        assert str(period_id) in available_period_ids

        denied = client.post("/api/v1/enrollments", headers=pilot["bare_headers"], json=body)
        assert denied.status_code == 403
        assert client.post("/api/v1/enrollments", headers=pilot["teacher_headers"], json=body).status_code == 403
        assert client.get("/api/v1/enrollments", headers=pilot["bare_headers"]).status_code == 403
        assert client.get("/api/v1/enrollments", headers=pilot["student_reader_headers"]).status_code == 403
        assert client.get("/api/v1/enrollments/options", headers=pilot["student_reader_headers"]).status_code == 403
        foreign_student = pilot["students"][1][1]
        foreign_body = {**body, "student_profile_id": str(foreign_student), "academic_period_id": str(period_id)}
        assert client.post("/api/v1/enrollments", headers=pilot["authorized_headers"], json=foreign_body).status_code == 404
        assert client.post("/api/v1/enrollments", headers=pilot["authorized_headers"], json={**body, "academic_period_id": str(foreign_period_id)}).status_code == 404
        assert client.post("/api/v1/enrollments", headers=pilot["authorized_headers"], json={**body, "campus_id": str(foreign_campus_id)}).status_code == 404
        assert client.get(f"/api/v1/enrollments/{foreign_enrollment_id}", headers=pilot["authorized_headers"]).status_code == 404
        assert client.patch(
            f"/api/v1/enrollments/{foreign_enrollment_id}/status", headers=pilot["authorized_headers"],
            json={"status": "WITHDRAWN", "expected_updated_at": enrollment["updated_at"], "effective_on": "2026-05-20", "reason_code": "STUDENT_REQUEST"},
        ).status_code == 404
        assert client.post("/api/v1/enrollments", headers=pilot["authorized_headers"], json={**body, "institution_id": str(uuid4())}).status_code == 422

        def change(target: str, revision: str, effective_on: str, reason: str | None = None):
            return client.patch(
                f"/api/v1/enrollments/{enrollment_id}/status",
                headers=pilot["authorized_headers"],
                json={"status": target, "expected_updated_at": revision, "effective_on": effective_on, "reason_code": reason},
            )

        invalid_date = change("WITHDRAWN", enrollment["updated_at"], "2026-01-09", "STUDENT_REQUEST")
        assert invalid_date.status_code == 422
        withdrawn = change("WITHDRAWN", enrollment["updated_at"], "2026-05-20", "STUDENT_REQUEST")
        assert withdrawn.status_code == 200, withdrawn.text
        retry = change("WITHDRAWN", enrollment["updated_at"], "2026-05-20", "STUDENT_REQUEST")
        assert retry.status_code == 200 and retry.json()["status"] == "WITHDRAWN"
        assert owner.exec(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id AND event_type='student.enrollment.status_changed'"), params={"id": enrollment_id}).one()[0] == 1
        stale_competitor = change("COMPLETED", enrollment["updated_at"], "2026-05-21")
        assert stale_competitor.status_code == 409

        reactivated = change("ACTIVE", withdrawn.json()["updated_at"], "2026-06-01", "RETURN_TO_STUDY")
        assert reactivated.status_code == 200, reactivated.text
        assert reactivated.json()["withdrawn_on"] is None
        completed = change("COMPLETED", reactivated.json()["updated_at"], "2026-06-10")
        assert completed.status_code == 200, completed.text
        assert completed.json()["allowed_actions"] == []
        assert change("WITHDRAWN", completed.json()["updated_at"], "2026-06-11", "OTHER").status_code == 409
        assert client.patch(
            f"/api/v1/enrollments/{enrollment_id}/status", headers=pilot["authorized_headers"],
            json={"status": "TRANSFERRED", "expected_updated_at": completed.json()["updated_at"]},
        ).status_code == 422

        history = client.get(f"/api/v1/enrollments/{enrollment_id}/history", headers=pilot["authorized_headers"])
        assert history.status_code == 200
        changes = [item["details"] for item in history.json() if item["action"] == "STUDENT_ENROLLMENT_STATUS_CHANGED"]
        assert [(item["from_status"], item["to_status"]) for item in changes] == [
            ("ACTIVE", "WITHDRAWN"), ("WITHDRAWN", "ACTIVE"), ("ACTIVE", "COMPLETED"),
        ]
        assert changes[1]["previous_withdrawn_on"] == "2026-05-20"
        assert owner.exec(text("SELECT count(*) FROM audit_logs WHERE entity_type='Enrollment' AND entity_id=:id"), params={"id": enrollment_id}).one()[0] == 4
        assert client.get("/api/v1/enrollments", headers=pilot["authorized_headers"]).json()[0]["id"] == enrollment["id"]

        second_person, second_student = _person_student(owner, code=f"SYN-M28-{uuid4().hex[:8]}")
        third_person, third_student = _person_student(owner, code=f"SYN-M28-{uuid4().hex[:8]}")
        pilot["students"].extend(((second_person, second_student), (third_person, third_student)))
        owner.commit()
        pending = client.post("/api/v1/enrollments", headers=pilot["authorized_headers"], json={
            **body, "student_profile_id": str(second_student), "enrollment_number": "SYNTHETIC-ENR-02",
            "status": "PENDING", "enrolled_on": None,
        })
        assert pending.status_code == 201, pending.text
        activated = client.patch(
            f"/api/v1/enrollments/{pending.json()['id']}/status", headers=pilot["authorized_headers"],
            json={"status": "ACTIVE", "expected_updated_at": pending.json()["updated_at"], "effective_on": "2026-02-01"},
        )
        assert activated.status_code == 200, activated.text
        concurrent_enrollment_id = activated.json()["id"]
        revision = activated.json()["updated_at"]
        prior_event_count = owner.exec(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id AND event_type='student.enrollment.status_changed'"), params={"id": concurrent_enrollment_id}).one()[0]
        def compete(target: str, effective_on: str, reason_code: str | None = None):
            return client.patch(
                f"/api/v1/enrollments/{concurrent_enrollment_id}/status",
                headers=pilot["authorized_headers"],
                json={"status": target, "expected_updated_at": revision, "effective_on": effective_on, "reason_code": reason_code},
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda args: compete(*args), [
                ("WITHDRAWN", "2026-05-01", "STUDENT_REQUEST"),
                ("COMPLETED", "2026-05-01", None),
            ]))
        assert sorted(response.status_code for response in outcomes) == [200, 409]
        assert owner.exec(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id AND event_type='student.enrollment.status_changed'"), params={"id": concurrent_enrollment_id}).one()[0] == prior_event_count + 1
        pending_cancel = client.post("/api/v1/enrollments", headers=pilot["authorized_headers"], json={
            **body, "student_profile_id": str(third_student), "enrollment_number": "SYNTHETIC-ENR-03",
            "status": "PENDING", "enrolled_on": None,
        })
        cancelled = client.patch(
            f"/api/v1/enrollments/{pending_cancel.json()['id']}/status", headers=pilot["authorized_headers"],
            json={"status": "CANCELLED", "expected_updated_at": pending_cancel.json()["updated_at"], "reason_code": "ADMIN_REQUEST"},
        )
        assert pending_cancel.status_code == 201 and cancelled.status_code == 200

def test_enrollment_contract_rejects_mass_assignment_and_transferred() -> None:
    from pydantic import ValidationError

    from app.modules.enrollment.router import EnrollmentCreate, EnrollmentStatusUpdate

    with pytest.raises(ValidationError):
        EnrollmentCreate.model_validate({
            "student_profile_id": str(uuid4()), "academic_period_id": str(uuid4()),
            "campus_id": str(uuid4()), "status": "ACTIVE", "organization_id": str(uuid4()),
        })
    with pytest.raises(ValidationError):
        EnrollmentStatusUpdate.model_validate({
            "status": "TRANSFERRED", "expected_updated_at": datetime.now(UTC).isoformat(),
        })


def test_m24_imported_enrollment_continues_through_authorized_lifecycle() -> None:
    with _pilot() as pilot:
        owner = pilot["owner"]
        actor = pilot["actors"][0]
        period_id, campus_id = uuid4(), uuid4()
        run_id, connector_id = uuid4(), uuid4()
        pilot["period_ids"].append(period_id)
        pilot["campus_ids"].append(campus_id)
        pilot["integration_run_ids"].append(run_id)
        pilot["connector_ids"].append(connector_id)
        owner.exec(text("""INSERT INTO academic_periods
            (id, organization_id, institution_id, code, name, starts_on, ends_on, status, created_at)
            VALUES (:id, :org, :institution, :code, 'Synthetic import period', '2025-01-01', '2030-12-31', 'ACTIVE', CURRENT_TIMESTAMP)"""),
            params={"id": period_id, "org": ORG_ID, "institution": INSTITUTION_ID, "code": f"M24-{period_id.hex[:12]}"})
        owner.exec(text("INSERT INTO campuses (id, institution_id, name, created_at) VALUES (:id, :institution, 'Synthetic import campus', CURRENT_TIMESTAMP)"),
                   params={"id": campus_id, "institution": INSTITUTION_ID})
        connector = IntegrationConnector(
            id=connector_id, organization_id=ORG_ID, institution_id=INSTITUTION_ID,
            connector_key=f"m24-{connector_id.hex[:10]}", connector_type="CSV_STUDENT_ENROLLMENT",
            display_name="Synthetic enrollment import", created_by_user_id=actor["user_id"],
        )
        run = IntegrationRun(
            id=run_id, organization_id=ORG_ID, institution_id=INSTITUTION_ID,
            connector_id=connector_id, initiated_by_user_id=actor["user_id"],
            source_kind="FILE", mode="DRY_RUN", source_fingerprint_sha256="a" * 64,
            idempotency_key="b" * 64, connector_config_version=1,
        )
        external_id = f"SYN-M24-{uuid4().hex[:10]}"
        run_item = IntegrationRunItem(
            organization_id=ORG_ID, institution_id=INSTITUTION_ID, run_id=run_id,
            source_item_key=external_id, source_item_fingerprint_sha256="c" * 64,
            canonical_entity_type="STUDENT_ENROLLMENT", operation_class="CREATE", status="VALID",
            detail_json={
                "external_student_id": external_id, "given_names": "Synthetic Import",
                "family_names": f"M28 {uuid4().hex[:8]}", "academic_period_code": f"M24-{period_id.hex[:12]}",
                "academic_period_id": str(period_id), "campus_id": str(campus_id),
                "student_code": f"SYN-{uuid4().hex[:8]}", "enrollment_number": f"M24-{uuid4().hex[:8]}",
                "enrollment_status": "PENDING", "enrolled_on": None,
            },
        )
        owner.add_all((connector, run, run_item))
        owner.commit()

        principal = CurrentPrincipal(
            user_id=actor["user_id"], organization_id=ORG_ID, institution_id=INSTITUTION_ID,
        )
        result = apply_csv_student_enrollment(owner, principal, run_id)
        owner.commit()
        applied = owner.exec(text("""SELECT metadata_json->>'student_profile_id', metadata_json->>'enrollment_id'
            FROM integration_run_events WHERE run_id=:run AND event_type='ITEM_APPLIED'"""),
            params={"run": run_id}).one()
        student_id, enrollment_id = UUID(applied[0]), UUID(applied[1])
        person_id = owner.exec(text("SELECT person_id FROM student_profiles WHERE id=:id"), params={"id": student_id}).one()[0]
        pilot["students"].append((person_id, student_id))
        pilot["extra_people"].append(person_id)
        assert result.applied_rows == 1
        assert owner.exec(text("SELECT count(*) FROM integration_external_student_refs WHERE connector_id=:id AND external_student_id=:external"),
                          params={"id": connector_id, "external": external_id}).one()[0] == 1

        imported = pilot["client"].get(f"/api/v1/enrollments/{enrollment_id}", headers=pilot["authorized_headers"])
        assert imported.status_code == 200 and imported.json()["status"] == "PENDING"
        activated = pilot["client"].patch(
            f"/api/v1/enrollments/{enrollment_id}/status", headers=pilot["authorized_headers"],
            json={"status": "ACTIVE", "expected_updated_at": imported.json()["updated_at"], "effective_on": "2026-02-01"},
        )
        assert activated.status_code == 200 and activated.json()["status"] == "ACTIVE"
        assert owner.exec(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id AND event_type IN ('student.enrollment.created','student.enrollment.status_changed')"),
                          params={"id": enrollment_id}).one()[0] == 2
