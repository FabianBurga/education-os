"""Rollback-only auth probes, not the Phase 3 demonstration dataset.

Setup uses the owner connection. Before HTTP execution SET LOCAL ROLE switches
to education_app: current_user is restricted and FORCE RLS applies. The outer
transaction is always rolled back; no fixture rows are ever committed.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlmodel import Session

from app.api.deps import get_session
from app.core import demo, demo_middleware
from app.core.config import settings
from app.core.security import create_access_token
from app.main import app
from app.modules.families.models import GuardianProfile, StaffProfile
from app.modules.family_portal.models import GuardianStudentPortalAccess
from app.modules.identity.models import (
    Membership,
    MembershipRole,
    Person,
    Role,
    RolePermission,
    UserAccount,
)
from app.modules.students.models import StudentProfile
from app.modules.tenancy.models import Institution, Organization


@pytest.fixture
def harness(monkeypatch):
    owner = create_engine(settings.OWNER_DATABASE_URL)
    with owner.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, expire_on_commit=False)
        try:
            org = Organization(name="Gateway rollback test")
            session.add(org)
            session.flush()
            inst = Institution(organization_id=org.id, name="Gateway rollback test")
            other = Institution(organization_id=org.id, name="Invisible institution")
            session.add_all([inst, other])
            session.flush()
            principals, role_ids = {}, {}
            permissions = dict(session.exec(text("SELECT key,id FROM permissions")).all())
            profiles = {}
            for alias, role_key in demo.ROLES.items():
                person = Person(
                    organization_id=org.id, given_names="Synthetic auth probe", family_names=alias
                )
                session.add(person)
                session.flush()
                user = UserAccount(
                    person_id=person.id,
                    login_email=f"{uuid4()}@test.invalid",
                    password_hash="unusable-test-only",
                )
                role = Role(institution_id=inst.id, key=role_key, name="Rollback-only role")
                session.add_all([user, role])
                session.flush()
                membership = Membership(user_id=user.id, institution_id=inst.id)
                session.add(membership)
                session.flush()
                session.add(MembershipRole(membership_id=membership.id, role_id=role.id))
                for key in demo.PERMISSIONS[alias]:
                    session.add(RolePermission(role_id=role.id, permission_id=permissions[key]))
                cls = (
                    StudentProfile
                    if alias == "STUDENT"
                    else GuardianProfile
                    if alias == "GUARDIAN"
                    else StaffProfile
                )
                profile = cls(organization_id=org.id, institution_id=inst.id, person_id=person.id)
                session.add(profile)
                session.flush()
                principals[alias] = str(user.id)
                role_ids[alias] = role.id
                profiles[alias] = profile.id
            # An authorized link only, no grades, enrollments, classes or story data.
            session.add(
                GuardianStudentPortalAccess(
                    organization_id=org.id,
                    institution_id=inst.id,
                    guardian_profile_id=profiles["GUARDIAN"],
                    student_profile_id=profiles["STUDENT"],
                )
            )
            session.flush()
            session.exec(text("SET LOCAL ROLE education_app"))
            assert session.exec(text("SELECT current_user")).one()[0] == "education_app"
            for key, value in dict(
                EDUCATION_OS_DEMO_MODE=True,
                PUBLIC_BASE_URL="https://demo.example.test",
                EDUCATION_OS_DEMO_ACCESS_CODE="test-entrance-only-not-deployed",
                EDUCATION_OS_DEMO_ORGANIZATION_ID=str(org.id),
                EDUCATION_OS_DEMO_INSTITUTION_ID=str(inst.id),
                EDUCATION_OS_DEMO_PRINCIPALS=principals,
            ).items():
                monkeypatch.setattr(settings, key, value)
            monkeypatch.setattr(demo, "store", demo.SessionStore())
            monkeypatch.setattr(demo_middleware, "engine", connection)
            app.dependency_overrides[get_session] = lambda: session
            with TestClient(
                app,
                base_url="https://demo.example.test",
                headers={"Origin": "https://demo.example.test"},
            ) as client:
                assert (
                    client.post(
                        "/api/demo/entrance", json={"code": settings.EDUCATION_OS_DEMO_ACCESS_CODE}
                    ).status_code
                    == 200
                )
                yield client, session, profiles, other.id, principals
        finally:
            app.dependency_overrides.pop(get_session, None)
            session.close()
            transaction.rollback()
    with owner.connect() as check:
        assert (
            check.execute(
                text("SELECT count(*) FROM organizations WHERE id=:id"), {"id": org.id}
            ).scalar_one()
            == 0
        )
    owner.dispose()


@pytest.mark.parametrize("alias", demo.ROLES)
def test_real_cookie_permission_context(harness, alias):
    client, session, profiles, _, principals = harness
    response = client.post("/api/demo/session", json={"alias": alias})
    assert response.status_code == 200, response.text
    result = client.get("/api/v1/ui/bootstrap")
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["roles"] == [demo.ROLES[alias]]
    assert set(data["permissions"]) == demo.PERMISSIONS[alias]
    assert data["user"]["user_id"] == principals[alias]
    assert client.post("/api/v1/communications/messages", json={}).status_code == 403
    assert client.get("/api/v1/admin/summary").status_code == 403
    assert session.exec(text("SELECT current_user")).one()[0] == "education_app"


def test_switch_revokes_previous_and_never_unions_permissions(harness):
    client, _, _, _, _ = harness
    assert client.post("/api/demo/session", json={"alias": "RECTOR"}).status_code == 200
    old = client.cookies.get(demo.COOKIE)
    assert client.post("/api/demo/session", json={"alias": "TEACHER"}).status_code == 200
    assert demo.store.get(old) is None
    assert "agents.use" not in client.get("/api/v1/ui/bootstrap").json()["permissions"]
    assert (
        client.post(
            "/api/v1/agents/mentor_institution_briefing/runs", json={"briefing_focus": "OVERVIEW"}
        ).status_code
        == 403
    )
    assert client.post("/api/demo/exit", json={}).status_code == 200
    assert client.get("/api/v1/ui/bootstrap").status_code == 401


def test_wrong_tenant_and_missing_actor_fail_closed(harness, monkeypatch):
    client, _, _, other, principals = harness
    monkeypatch.setattr(settings, "EDUCATION_OS_DEMO_INSTITUTION_ID", str(other))
    assert client.post("/api/demo/session", json={"alias": "RECTOR"}).status_code == 403
    monkeypatch.setattr(
        settings, "EDUCATION_OS_DEMO_PRINCIPALS", {**principals, "STUDENT": str(uuid4())}
    )
    assert client.post("/api/demo/session", json={"alias": "STUDENT"}).status_code == 403


def test_student_self_and_guardian_link_scope(harness):
    client, _, profiles, _, _ = harness
    assert client.post("/api/demo/session", json={"alias": "STUDENT"}).status_code == 200
    me = client.get("/api/v1/student/me")
    assert me.status_code == 200, me.text
    assert str(profiles["STUDENT"]) in me.text
    assert client.get("/api/v1/guardian/students").status_code == 403
    assert client.get(f"/api/v1/student-timeline/students/{profiles['STUDENT']}").status_code == 403
    assert client.post("/api/demo/session", json={"alias": "GUARDIAN"}).status_code == 200
    children = client.get("/api/v1/guardian/students")
    assert children.status_code == 200, children.text
    assert [row["student_profile_id"] for row in children.json()] == [str(profiles["STUDENT"])]
    assert client.get(f"/api/v1/guardian/students/{uuid4()}/summary").status_code == 404
    assert client.get("/api/v1/student/me").status_code == 403


def test_bearer_still_works_when_demo_off(harness, monkeypatch):
    client, _, _, _, principals = harness
    monkeypatch.setattr(settings, "EDUCATION_OS_DEMO_MODE", False)
    token = create_access_token(
        user_id=principals["RECTOR"],
        organization_id=settings.EDUCATION_OS_DEMO_ORGANIZATION_ID,
        institution_id=settings.EDUCATION_OS_DEMO_INSTITUTION_ID,
    )
    result = client.get("/api/v1/me", headers={"Authorization": "Bearer " + token})
    assert result.status_code == 200 and result.json()["user_id"] == principals["RECTOR"]


@pytest.mark.parametrize(
    "alias,path",
    [
        ("TEACHER", "teacher"),
        ("STUDENT", "student"),
        ("GUARDIAN", "guardian"),
        ("COORDINATION", "coordination"),
    ],
)
def test_legacy_console_cookie_transport(harness, alias, path):
    client, _, _, _, _ = harness
    assert client.post("/api/demo/session", json={"alias": alias}).status_code == 200
    page = client.get(f"/api/v1/{path}/dashboard")
    assert page.status_code == 200, page.text
    assert ".auth{display:none!important}" in page.text
    assert "window.educationDemo=true" in page.text
    assert client.cookies.get(demo.COOKIE) not in page.text
    assert page.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/admin/dashboard").status_code == 403


def test_wrong_role_and_org_fail_closed(harness, monkeypatch):
    client, _, _, _, principals = harness
    monkeypatch.setattr(
        settings, "EDUCATION_OS_DEMO_PRINCIPALS", {**principals, "RECTOR": principals["TEACHER"]}
    )
    assert client.post("/api/demo/session", json={"alias": "RECTOR"}).status_code == 403
    monkeypatch.setattr(settings, "EDUCATION_OS_DEMO_ORGANIZATION_ID", str(uuid4()))
    assert client.post("/api/demo/session", json={"alias": "TEACHER"}).status_code == 403


def test_permission_expansion_and_membership_revocation_fail_closed(harness):
    client, session, _, _, principals = harness
    assert client.post("/api/demo/session", json={"alias": "RECTOR"}).status_code == 200
    # Owner is used only to change the rollback-only fixture. Restore the runtime
    # role before the request; the gateway must re-check the live permission set.
    session.exec(text("RESET ROLE"))
    session.exec(
        text("""INSERT INTO role_permissions (role_id,permission_id)
        SELECT mr.role_id,p.id FROM membership_roles mr
        JOIN memberships m ON m.id=mr.membership_id CROSS JOIN permissions p
        WHERE m.user_id=CAST(:user AS uuid) AND p.key='admin.console.access'"""),
        params={"user": principals["RECTOR"]},
    )
    session.exec(text("SET LOCAL ROLE education_app"))
    assert client.get("/api/v1/ui/bootstrap").status_code == 403
    assert client.post("/api/demo/session", json={"alias": "STUDENT"}).status_code == 200
    session.exec(text("RESET ROLE"))
    session.exec(
        text("UPDATE memberships SET status='INACTIVE' WHERE user_id=CAST(:user AS uuid)"),
        params={"user": principals["STUDENT"]},
    )
    session.exec(text("SET LOCAL ROLE education_app"))
    assert client.get("/api/v1/student/me").status_code == 403
