from __future__ import annotations

import os
import sys
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


def bootstrap_coordination_context():
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                ua.id,
                i.organization_id,
                m.institution_id,
                m.id,
                ua.login_email
            FROM staff_profiles sp
            JOIN persons p ON p.id = sp.person_id
            JOIN user_accounts ua ON ua.person_id = p.id
            JOIN memberships m
              ON m.user_id = ua.id
             AND m.institution_id = sp.institution_id
             AND m.status = 'ACTIVE'
            JOIN institutions i ON i.id = m.institution_id
            WHERE sp.status = 'ACTIVE'
              AND ua.is_active = true
            ORDER BY sp.created_at
            LIMIT 1
            """
        )
        admin = cur.fetchone()
        assert admin is not None, "active staff account not found"
        user_id, org_id, inst_id, membership_id, login_email = admin

        cur.execute(
            """
            SELECT id
            FROM roles
            WHERE institution_id = %s
              AND key = 'RECTOR'
            """,
            (inst_id,),
        )
        role = cur.fetchone()
        assert role is not None, "RECTOR role missing"

        cur.execute(
            """
            INSERT INTO membership_roles (membership_id, role_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (membership_id, role[0]),
        )

        cur.execute(
            """
            SELECT ua.id
            FROM user_accounts ua
            JOIN memberships m ON m.user_id = ua.id
            JOIN staff_profiles sp
              ON sp.person_id = ua.person_id
             AND sp.institution_id = m.institution_id
             AND sp.status = 'ACTIVE'
            WHERE m.institution_id = %s
              AND m.status = 'ACTIVE'
              AND ua.is_active = true
              AND ua.id <> %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM membership_roles mr
                  JOIN role_permissions rp ON rp.role_id = mr.role_id
                  JOIN permissions p ON p.id = rp.permission_id
                  WHERE mr.membership_id = m.id
                    AND p.key = 'coord.console.access'
              )
            ORDER BY ua.created_at
            LIMIT 1
            """,
            (inst_id, user_id),
        )
        other = cur.fetchone()

        if other is None:
            person_id = uuid4()
            other_user_id = uuid4()
            other_membership_id = uuid4()
            staff_id = uuid4()
            suffix = uuid4().hex[:8]

            cur.execute(
                """
                INSERT INTO persons (
                    id,
                    organization_id,
                    given_names,
                    family_names,
                    primary_email,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, NOW())
                """,
                (
                    person_id,
                    org_id,
                    "M9",
                    "Non Coordination",
                    f"m9-noncoord-{suffix}@example.invalid",
                ),
            )
            cur.execute(
                """
                INSERT INTO user_accounts (
                    id,
                    person_id,
                    login_email,
                    password_hash,
                    is_active,
                    created_at
                )
                VALUES (%s, %s, %s, %s, true, NOW())
                """,
                (
                    other_user_id,
                    person_id,
                    f"m9-noncoord-{suffix}@education-os.internal",
                    hash_password("M9-NonCoord-Temporary-2026!"),
                ),
            )
            cur.execute(
                """
                INSERT INTO memberships (
                    id,
                    user_id,
                    institution_id,
                    status,
                    created_at
                )
                VALUES (%s, %s, %s, 'ACTIVE', NOW())
                """,
                (
                    other_membership_id,
                    other_user_id,
                    inst_id,
                ),
            )
            cur.execute(
                """
                INSERT INTO staff_profiles (
                    id,
                    organization_id,
                    institution_id,
                    person_id,
                    staff_code,
                    status,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, 'ACTIVE', NOW())
                """,
                (
                    staff_id,
                    org_id,
                    inst_id,
                    person_id,
                    f"M9-NON-{suffix}",
                ),
            )
        else:
            other_user_id = other[0]

        conn.commit()

    return user_id, org_id, inst_id, other_user_id, login_email


def main() -> None:
    user_id, org_id, inst_id, other_user_id, login_email = (
        bootstrap_coordination_context()
    )

    token = create_access_token(
        user_id=UUID(str(user_id)),
        organization_id=UUID(str(org_id)),
        institution_id=UUID(str(inst_id)),
    )
    other_token = create_access_token(
        user_id=UUID(str(other_user_id)),
        organization_id=UUID(str(org_id)),
        institution_id=UUID(str(inst_id)),
    )

    from app.main import app

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}

    dashboard = client.get("/api/v1/coordination/dashboard")
    assert dashboard.status_code == 200
    assert "Rector / Coordination Console" in dashboard.text
    assert "Casos y seguimiento" in dashboard.text
    print("M9 coordination dashboard HTML: PASSED")

    read_paths = (
        "/api/v1/coordination/summary",
        "/api/v1/coordination/attention",
        "/api/v1/coordination/sections",
        "/api/v1/coordination/trends/attendance?days=30",
        "/api/v1/coordination/trends/academic",
        "/api/v1/coordination/cases",
    )
    for path in read_paths:
        response = client.get(path, headers=headers)
        assert response.status_code == 200, (
            f"{path}: {response.status_code} {response.text}"
        )
    print("M9 coordination protected read surface: PASSED")

    legacy = client.get(
        "/api/v1/intelligence/rector/overview",
        headers=headers,
    )
    assert legacy.status_code == 200, legacy.text
    print("M4 intelligence backward-compatible Rector access: PASSED")

    denied_headers = {"Authorization": f"Bearer {other_token}"}
    denied = client.get(
        "/api/v1/coordination/summary",
        headers=denied_headers,
    )
    assert denied.status_code == 403, denied.text

    legacy_denied = client.get(
        "/api/v1/intelligence/rector/overview",
        headers=denied_headers,
    )
    assert legacy_denied.status_code == 403, legacy_denied.text
    print("Non-coordination negative boundary: PASSED")

    refresh = client.post(
        "/api/v1/coordination/signals/refresh",
        headers=headers,
    )
    assert refresh.status_code == 200, refresh.text

    engine = client.post(
        "/api/v1/coordination/workflows/run",
        headers=headers,
    )
    assert engine.status_code == 200, engine.text

    tick = client.post(
        "/api/v1/coordination/workflows/tick",
        headers=headers,
    )
    assert tick.status_code == 200, tick.text
    print("Coordination signal / workflow control actions: PASSED")

    cases = client.get(
        "/api/v1/coordination/cases",
        headers=headers,
    )
    assert cases.status_code == 200
    cases_body = cases.json()
    if cases_body:
        timeline = client.get(
            f"/api/v1/coordination/cases/{cases_body[0]['case_id']}/timeline",
            headers=headers,
        )
        assert timeline.status_code == 200, timeline.text
        print("Coordination case timeline: PASSED")
    else:
        print("Coordination case timeline: SKIPPED (no cases in clone)")

    actionable_task = None
    for case in cases_body:
        for task in case["tasks"]:
            if task["status"] in {"OPEN", "ESCALATED"}:
                actionable_task = task
                break
        if actionable_task:
            break

    if actionable_task:
        task_id = actionable_task["id"]
        ack = client.post(
            f"/api/v1/coordination/tasks/{task_id}/acknowledge",
            headers=headers,
        )
        assert ack.status_code == 200, ack.text

        complete = client.post(
            f"/api/v1/coordination/tasks/{task_id}/complete",
            headers=headers,
            json={
                "completion_note": (
                    "M9 verifier: seguimiento humano completado en clon."
                )
            },
        )
        assert complete.status_code == 200, complete.text
        assert complete.json()["status"] == "COMPLETED"
        print("Coordination task lifecycle action: PASSED")
    else:
        print("Coordination task lifecycle action: SKIPPED (no open task)")

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
                    "coord.analytics.view",
                    "coord.cases.manage",
                    "coord.console.access",
                    "coord.signals.manage",
                ],
            ),
        )
        permission_keys = [row[0] for row in cur.fetchall()]
        assert permission_keys == [
            "coord.analytics.view",
            "coord.cases.manage",
            "coord.console.access",
            "coord.signals.manage",
        ]

        cur.execute(
            """
            SELECT key
            FROM roles
            WHERE institution_id = %s
              AND key IN ('RECTOR', 'ACADEMIC_COORDINATOR')
            ORDER BY key
            """,
            (inst_id,),
        )
        roles = [row[0] for row in cur.fetchall()]
        assert roles == ["ACADEMIC_COORDINATOR", "RECTOR"]

        cur.execute(
            """
            SELECT action, COUNT(*)
            FROM audit_logs
            WHERE institution_id = %s
              AND action IN (
                  'COORD_SIGNALS_REFRESHED',
                  'COORD_ENGINE_RUN',
                  'COORD_ENGINE_TICK'
              )
            GROUP BY action
            """,
            (inst_id,),
        )
        audit_counts = dict(cur.fetchall())
        for action in (
            "COORD_SIGNALS_REFRESHED",
            "COORD_ENGINE_RUN",
            "COORD_ENGINE_TICK",
        ):
            assert int(audit_counts.get(action, 0)) >= 1

    print("M9 role / permission / audit catalog: PASSED")
    print(f"Rector verifier login source={login_email}")
    print("M9 Rector / Coordination Console verifier: PASSED")


if __name__ == "__main__":
    main()
