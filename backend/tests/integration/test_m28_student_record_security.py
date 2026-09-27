"""Application-role HTTP proofs for the M28-1 student record boundary."""

from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlmodel import Session

from app.api.deps import get_session
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


def _cleanup(owner: Session, actors: list[dict[str, UUID]], students: list[tuple[UUID, UUID]], extra_people: list[UUID]) -> None:
    owner.rollback()
    student_ids = [str(student_id) for _, student_id in students]
    if student_ids:
        owner.exec(text("DELETE FROM audit_logs WHERE entity_id = ANY(CAST(:ids AS uuid[]))"), params={"ids": student_ids})
        owner.exec(text("DELETE FROM outbox_events WHERE aggregate_id = ANY(CAST(:ids AS uuid[]))"), params={"ids": student_ids})
        owner.exec(text("DELETE FROM student_profiles WHERE id = ANY(CAST(:ids AS uuid[]))"), params={"ids": student_ids})
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
    try:
        assert owner.exec(text("SELECT 1 FROM institutions WHERE id=:id AND organization_id=:org"), params={"id": INSTITUTION_ID, "org": ORG_ID}).first()
        authorized = _actor(owner, {"students.read", "students.manage", "admin.people.manage"})
        bare_admin = _actor(owner, set())
        teacher = _actor(owner, set(), role_key="TEACHER")
        actors.extend((authorized, bare_admin, teacher))
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
                "authorized_headers": _headers(authorized),
                "bare_headers": _headers(bare_admin),
                "teacher_headers": _headers(teacher),
                "client": TestClient(app, raise_server_exceptions=False),
            }
        finally:
            app.dependency_overrides.pop(get_session, None)
    finally:
        _cleanup(owner, actors, students, extra_people)
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
        assert {item["id"] for item in response.json()["items"]} == {local_id}
        assert "Synthetic Student" in response.json()["items"][0]["display_name"]
        legacy_list = client.get("/api/v1/students?limit=10", headers=pilot["authorized_headers"])
        assert legacy_list.status_code == 200
        assert {item["id"] for item in legacy_list.json()} == {local_id}
        assert set(legacy_list.json()[0]) == {"id", "display_name", "student_code", "status", "updated_at"}
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
