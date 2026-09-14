from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.core.security import create_access_token
from app.db.session import get_session
from app.db.tenant_context import TenantContext, apply_tenant_context
from app.main import app
from app.modules.attendance.schemas import AttendanceRecordUpsert
from app.modules.attendance.service import upsert_record
from app.modules.events.projection_service import ingest_outbox_events
from app.modules.student_timeline.projector import project_student_timeline

DB_URL_ENV = "M21_E2E_DATABASE_URL"


def _database_url() -> str:
    raw = os.getenv(DB_URL_ENV)
    if not raw:
        pytest.skip(f"{DB_URL_ENV} is not configured")
    if raw.startswith("postgresql://"):
        return "postgresql+psycopg://" + raw[len("postgresql://") :]
    return raw


def _fixture(session: Session):
    row = session.exec(
        text(
            """
            SELECT
                i.organization_id,
                i.id AS institution_id,
                ua.id AS teacher_user_id,
                cs.id AS class_session_id,
                ssa.id AS student_section_assignment_id,
                en.student_profile_id,
                ac.id AS attendance_code_id
            FROM institutions i
            JOIN user_accounts ua ON ua.is_active = true
            JOIN staff_profiles sp
              ON sp.person_id = ua.person_id
             AND sp.institution_id = i.id
             AND sp.status = 'ACTIVE'
            JOIN teaching_assignments ta
              ON ta.staff_profile_id = sp.id
             AND ta.institution_id = i.id
             AND (ta.starts_on IS NULL OR ta.starts_on <= CURRENT_DATE)
             AND (ta.ends_on IS NULL OR ta.ends_on >= CURRENT_DATE)
            JOIN course_offerings co
              ON co.id = ta.course_offering_id
             AND co.institution_id = i.id
             AND co.status = 'ACTIVE'
            JOIN class_sessions cs
              ON cs.course_offering_id = co.id
             AND cs.institution_id = i.id
            JOIN student_section_assignments ssa
              ON ssa.section_id = co.section_id
             AND ssa.institution_id = i.id
             AND ssa.status = 'ACTIVE'
            JOIN enrollments en
              ON en.id = ssa.enrollment_id
             AND en.institution_id = i.id
            JOIN attendance_codes ac
              ON ac.institution_id = i.id
             AND ac.status = 'ACTIVE'
            JOIN memberships m
              ON m.user_id = ua.id
             AND m.institution_id = i.id
             AND m.status = 'ACTIVE'
            JOIN membership_roles mr ON mr.membership_id = m.id
            JOIN roles r
              ON r.id = mr.role_id
             AND r.key = 'TEACHER'
            WHERE i.status = 'ACTIVE'
            ORDER BY cs.session_date DESC, cs.starts_at DESC
            LIMIT 1
            """
        )
    ).first()
    if row is None:
        pytest.skip(
            "No active teacher/class-session/student/attendance-code fixture available"
        )
    return row


def _authorization(
    user_id: UUID,
    organization_id: UUID,
    institution_id: UUID,
) -> dict[str, str]:
    token = create_access_token(
        user_id=user_id,
        organization_id=organization_id,
        institution_id=institution_id,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
def test_attendance_to_timeline_read_api_end_to_end():
    engine = create_engine(_database_url(), pool_pre_ping=True)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    try:
        (
            organization_id,
            institution_id,
            teacher_user_id,
            class_session_id,
            assignment_id,
            student_profile_id,
            attendance_code_id,
        ) = _fixture(session)

        principal = CurrentPrincipal(
            user_id=teacher_user_id,
            organization_id=organization_id,
            institution_id=institution_id,
        )
        apply_tenant_context(
            session,
            TenantContext(
                organization_id=organization_id,
                institution_id=institution_id,
                user_id=teacher_user_id,
            ),
        )

        before_outbox = set(
            session.exec(
                text(
                    """
                    SELECT id
                    FROM outbox_events
                    WHERE institution_id = CAST(:institution_id AS uuid)
                    """
                ),
                params={"institution_id": str(institution_id)},
            ).all()
        )

        existing = session.exec(
            text(
                """
                SELECT attendance_code_id, minutes_late, note
                FROM attendance_records
                WHERE class_session_id = CAST(:class_session_id AS uuid)
                  AND student_section_assignment_id = CAST(:assignment_id AS uuid)
                LIMIT 1
                """
            ),
            params={
                "class_session_id": str(class_session_id),
                "assignment_id": str(assignment_id),
            },
        ).first()

        if existing is None:
            payload = AttendanceRecordUpsert(
                student_section_assignment_id=assignment_id,
                attendance_code_id=attendance_code_id,
                minutes_late=0,
                note=None,
            )
            expected_type = "student.attendance.recorded"
        else:
            payload = AttendanceRecordUpsert(
                student_section_assignment_id=assignment_id,
                attendance_code_id=existing[0],
                minutes_late=int(existing[1] or 0),
                note=existing[2],
            )
            expected_type = "student.attendance.updated"

        started_at = datetime.now(UTC)
        record = upsert_record(
            session,
            principal,
            class_session_id,
            payload,
        )

        outbox = session.exec(
            text(
                """
                SELECT id, event_type, aggregate_id
                FROM outbox_events
                WHERE institution_id = CAST(:institution_id AS uuid)
                  AND aggregate_id = CAST(:aggregate_id AS uuid)
                  AND created_at >= :started_at
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            params={
                "institution_id": str(institution_id),
                "aggregate_id": str(record.id),
                "started_at": started_at,
            },
        ).first()
        assert outbox is not None
        assert outbox[0] not in before_outbox
        assert outbox[1] == expected_type
        assert outbox[2] == record.id

        ingested = ingest_outbox_events(
            session,
            institution_id=institution_id,
            limit=1000,
        )
        assert ingested >= 1

        ledger = session.exec(
            text(
                """
                SELECT id, position, event_type, actor_user_id, payload_json
                FROM event_ledger
                WHERE source_outbox_event_id = CAST(:outbox_id AS uuid)
                """
            ),
            params={"outbox_id": str(outbox[0])},
        ).one()
        assert ledger[2] == expected_type
        assert ledger[3] == teacher_user_id
        assert ledger[4]["student_profile_id"] == str(student_profile_id)

        projected = project_student_timeline(
            session,
            organization_id=organization_id,
            institution_id=institution_id,
            limit=1000,
        )
        assert projected.scanned >= 1

        timeline = session.exec(
            text(
                """
                SELECT
                    id,
                    student_profile_id,
                    ledger_event_id,
                    ledger_position,
                    event_type,
                    category,
                    sensitivity,
                    context_json
                FROM student_timeline_entries
                WHERE ledger_event_id = CAST(:ledger_event_id AS uuid)
                """
            ),
            params={"ledger_event_id": str(ledger[0])},
        ).one()
        assert timeline[1] == student_profile_id
        assert timeline[2] == ledger[0]
        assert int(timeline[3]) == int(ledger[1])
        assert timeline[4] == expected_type
        assert timeline[5] == "ATTENDANCE"
        assert timeline[6] == "GENERAL"
        assert "note" not in timeline[7]

        second_projection = project_student_timeline(
            session,
            organization_id=organization_id,
            institution_id=institution_id,
            limit=1000,
        )
        assert second_projection.inserted == 0

        count = session.exec(
            text(
                """
                SELECT COUNT(*)
                FROM student_timeline_entries
                WHERE ledger_event_id = CAST(:ledger_event_id AS uuid)
                """
            ),
            params={"ledger_event_id": str(ledger[0])},
        ).one()[0]
        assert int(count) == 1

        def override_session():
            yield session

        app.dependency_overrides[get_session] = override_session
        client = TestClient(app)
        response = client.get(
            f"/api/v1/student-timeline/students/{student_profile_id}",
            headers=_authorization(
                teacher_user_id,
                organization_id,
                institution_id,
            ),
        )
        assert response.status_code == 200

        returned = [
            item
            for item in response.json()["entries"]
            if item["ledger_event_id"] == str(ledger[0])
        ]
        assert len(returned) == 1
        assert returned[0]["event_type"] == expected_type
        assert returned[0]["category"] == "ATTENDANCE"
        assert returned[0]["sensitivity"] == "GENERAL"
        assert "note" not in returned[0]["context_json"]
    finally:
        app.dependency_overrides.clear()
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()