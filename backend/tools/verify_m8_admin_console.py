from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.security import create_access_token  # noqa: E402

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)


def bootstrap_admin():
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT ua.id, i.organization_id, m.institution_id, m.id
            FROM staff_profiles sp
            JOIN persons p ON p.id=sp.person_id
            JOIN user_accounts ua ON ua.person_id=p.id
            JOIN memberships m
              ON m.user_id=ua.id
             AND m.institution_id=sp.institution_id
             AND m.status='ACTIVE'
            JOIN institutions i ON i.id=m.institution_id
            WHERE sp.status='ACTIVE'
              AND ua.is_active=true
            ORDER BY sp.created_at
            LIMIT 1
            """
        )
        row = cur.fetchone()
        assert row is not None, "active staff account not found"
        user_id, org_id, inst_id, membership_id = row

        cur.execute(
            """
            SELECT id
            FROM roles
            WHERE institution_id=%s
              AND key='SYSTEM_ADMIN'
            """,
            (inst_id,),
        )
        role = cur.fetchone()
        assert role is not None, "SYSTEM_ADMIN role missing"
        cur.execute(
            """
            INSERT INTO membership_roles (membership_id, role_id)
            VALUES (%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (membership_id, role[0]),
        )
        conn.commit()
    return user_id, org_id, inst_id


def main() -> None:
    user_id, org_id, inst_id = bootstrap_admin()

    token = create_access_token(
        user_id=user_id,
        organization_id=org_id,
        institution_id=inst_id,
    )

    from app.main import app

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}

    dashboard = client.get("/api/v1/admin/dashboard")
    assert dashboard.status_code == 200
    assert "Administrator Console" in dashboard.text
    print("Administrator dashboard HTML: PASSED")

    paths = (
        "/api/v1/admin/summary",
        "/api/v1/admin/institution",
        "/api/v1/admin/campuses",
        "/api/v1/admin/people",
        "/api/v1/admin/accounts",
        "/api/v1/admin/staff",
        "/api/v1/admin/roles",
        "/api/v1/admin/permissions",
        "/api/v1/admin/onboarding-checklist",
    )
    for path in paths:
        response = client.get(path, headers=headers)
        assert response.status_code == 200, (
            f"{path}: {response.status_code} {response.text}"
        )
    print("Administrator protected read surface: PASSED")

    suffix = uuid4().hex[:8]

    campus = client.post(
        "/api/v1/admin/campuses",
        headers=headers,
        json={"name": f"M8 Verification Campus {suffix}"},
    )
    assert campus.status_code == 201, campus.text

    person = client.post(
        "/api/v1/admin/people",
        headers=headers,
        json={
            "given_names": "M8",
            "family_names": "Verifier",
            "primary_email": f"m8-{suffix}@example.invalid",
        },
    )
    assert person.status_code == 201, person.text
    person_id = person.json()["id"]

    account = client.post(
        "/api/v1/admin/accounts",
        headers=headers,
        json={
            "person_id": person_id,
            "login_email": f"m8-{suffix}@education-os.internal",
            "temporary_password": "Temporary-M8-Password-2026!",
        },
    )
    assert account.status_code == 201, account.text
    account_body = account.json()

    staff = client.post(
        "/api/v1/admin/staff",
        headers=headers,
        json={
            "person_id": person_id,
            "staff_code": f"M8-{suffix}",
        },
    )
    assert staff.status_code == 201, staff.text

    role = client.post(
        "/api/v1/admin/roles",
        headers=headers,
        json={
            "key": f"M8_VERIFY_{suffix.upper()}",
            "name": "M8 verification role",
        },
    )
    assert role.status_code == 201, role.text
    role_id = role.json()["id"]

    permissions = client.get(
        "/api/v1/admin/permissions",
        headers=headers,
    ).json()
    people_permission = next(
        item
        for item in permissions
        if item["key"] == "admin.people.manage"
    )

    grant = client.post(
        (
            f"/api/v1/admin/roles/{role_id}/permissions/"
            f"{people_permission['id']}"
        ),
        headers=headers,
    )
    assert grant.status_code == 204, grant.text

    assign = client.post(
        (
            f"/api/v1/admin/memberships/"
            f"{account_body['membership_id']}/roles/{role_id}"
        ),
        headers=headers,
    )
    assert assign.status_code == 204, assign.text

    accounts = client.get(
        "/api/v1/admin/accounts",
        headers=headers,
    )
    assert accounts.status_code == 200
    assert any(
        item["user_id"] == account_body["user_id"]
        for item in accounts.json()
    )

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT password_hash FROM user_accounts WHERE id=%s",
            (account_body["user_id"],),
        )
        hashed = cur.fetchone()[0]
        assert hashed != "Temporary-M8-Password-2026!"

    checklist = client.get(
        "/api/v1/admin/onboarding-checklist",
        headers=headers,
    )
    assert checklist.status_code == 200
    assert checklist.json()["total_items"] >= 8

    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT ua.id, i.organization_id, m.institution_id
            FROM user_accounts ua
            JOIN memberships m ON m.user_id=ua.id
            JOIN institutions i ON i.id=m.institution_id
            WHERE ua.id<>%s
              AND ua.is_active=true
              AND m.institution_id=%s
            ORDER BY ua.created_at
            LIMIT 1
            """,
            (user_id, inst_id),
        )
        other = cur.fetchone()

    if other is not None:
        other_token = create_access_token(
            user_id=other[0],
            organization_id=other[1],
            institution_id=other[2],
        )
        denied = client.get(
            "/api/v1/admin/summary",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert denied.status_code == 403, denied.text
        print("Non-admin negative boundary: PASSED")
    else:
        print("Non-admin negative boundary: SKIPPED (no second account)")

    print("M8 Administrator Console verifier: PASSED")


if __name__ == "__main__":
    main()
