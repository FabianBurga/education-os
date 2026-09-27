from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlmodel import Session

from app.api.access import TeacherPrincipal
from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_session
from app.db.tenant_context import TenantContext, apply_tenant_context
from app.main import app
from app.modules.events.projection_service import ingest_outbox_events
from app.modules.student_timeline.projector import project_student_timeline
from app.modules.teacher_console.schemas import TeacherAttendanceMark
from app.modules.teacher_offline.schemas import (
    TeacherOfflineAttendanceBase,
    TeacherOfflineAttendanceOperation,
    TeacherOfflineSyncBatch,
)
from app.modules.teacher_offline.service import sync_teacher_offline_operations

DB_URL_ENV = "M21_E2E_DATABASE_URL"


def _database_url() -> str:
    raw = os.getenv(DB_URL_ENV)
    if not raw:
        pytest.skip(f"{DB_URL_ENV} is not configured")
    if raw.startswith("postgresql://"):
        return "postgresql+psycopg://" + raw[len("postgresql://") :]
    return raw


def _fixture():
    """Read a fixture under owner role; runtime RLS needs context first."""
    if not settings.OWNER_DATABASE_URL:
        pytest.fail("OWNER_DATABASE_URL is required to discover the M21 fixture")
    owner_engine = create_engine(settings.OWNER_DATABASE_URL, pool_pre_ping=True)
    try:
        with Session(owner_engine) as owner:
            row = owner.exec(
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
             AND cs.status = 'OPEN'
            JOIN academic_periods ap
              ON ap.id = co.academic_period_id
             AND ap.institution_id = i.id
             AND ap.status = 'ACTIVE'
             AND cs.session_date BETWEEN ap.starts_on AND ap.ends_on
            JOIN student_section_assignments ssa
              ON ssa.section_id = co.section_id
             AND ssa.institution_id = i.id
             AND ssa.status = 'ACTIVE'
             AND ssa.assigned_on <= cs.session_date
             AND (ssa.ended_on IS NULL OR ssa.ended_on >= cs.session_date)
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
              AND co.status = 'ACTIVE'
              AND (ta.starts_on IS NULL OR ta.starts_on <= cs.session_date)
              AND (ta.ends_on IS NULL OR ta.ends_on >= cs.session_date)
              AND EXISTS (
                  SELECT 1
                  FROM role_permissions rp
                  JOIN permissions p ON p.id=rp.permission_id
                  WHERE rp.role_id=r.id
                    AND p.key='teacher.attendance.manage'
              )
              AND EXISTS (
                  SELECT 1
                  FROM role_permissions rp
                  JOIN permissions p ON p.id=rp.permission_id
                  WHERE rp.role_id=r.id
                    AND p.key='student_timeline.read'
              )
            ORDER BY cs.session_date DESC, cs.starts_at DESC
            LIMIT 1
            """
                )
            ).first()
            if row is None:
                pytest.skip(
                    "No active teacher/class-session/student/attendance-code fixture available"
                )
            projection_user_id = owner.exec(
                text(
                    """
                    SELECT ua.id
                    FROM user_accounts ua
                    JOIN memberships m ON m.user_id=ua.id
                      AND m.institution_id=CAST(:institution_id AS uuid)
                      AND m.status='ACTIVE'
                    JOIN membership_roles mr ON mr.membership_id=m.id
                    JOIN role_permissions rp ON rp.role_id=mr.role_id
                    JOIN permissions p ON p.id=rp.permission_id
                      AND p.key='admin.console.access'
                    WHERE ua.is_active=true
                    ORDER BY ua.id
                    LIMIT 1
                    """
                ),
                params={"institution_id": str(row[1])},
            ).first()
            if projection_user_id is None:
                pytest.fail(
                    "M21 E2E fixture tenant has no principal with admin.console.access"
                )
            return (*row, projection_user_id[0])
    finally:
        owner_engine.dispose()


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
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session

    try:
        (
            organization_id,
            institution_id,
            teacher_user_id,
            class_session_id,
            assignment_id,
            student_profile_id,
            attendance_code_id,
            projection_user_id,
        ) = _fixture()
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
                SELECT id, attendance_code_id, minutes_late, note
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
            new_minutes = 0
            note = None
            expected_type = "student.attendance.recorded"
        else:
            new_minutes = 0 if int(existing[2] or 0) else 1
            note = existing[3]
            expected_type = "student.attendance.updated"

        started_at = datetime.now(UTC)
        command = {
            "student_section_assignment_id": str(assignment_id),
            "attendance_code_id": str(existing[1] if existing else attendance_code_id),
            "minutes_late": new_minutes,
            "note": note,
        }
        if existing is not None:
            command.update(
                {
                    "expected_state": {
                        "attendance_record_id": str(existing[0]),
                        "attendance_code_id": str(existing[1]),
                        "minutes_late": int(existing[2] or 0),
                        "note": existing[3],
                    },
                    "correction_reason": "EVIDENCE_CORRECTION",
                }
            )
        client = TestClient(app)
        response = client.put(
            f"/api/v1/teacher/sessions/{class_session_id}/attendance",
            headers=_authorization(teacher_user_id, organization_id, institution_id),
            json=command,
        )
        assert response.status_code == 200, response.text
        record_id = response.json()["id"]

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
                    "aggregate_id": str(record_id),
                "started_at": started_at,
            },
        ).first()
        assert outbox is not None
        assert outbox[0] not in before_outbox
        assert outbox[1] == expected_type
        assert outbox[2] == UUID(record_id)

        apply_tenant_context(
            session,
            TenantContext(
                organization_id=organization_id,
                institution_id=institution_id,
                user_id=projection_user_id,
            ),
        )
        ingested = ingest_outbox_events(
            session,
            institution_id=institution_id,
            limit=1000,
        )
        assert ingested >= 1

        ledger = session.exec(
            text(
                """
                SELECT id, position, event_type, actor_user_id
                FROM event_ledger
                WHERE source_outbox_event_id = CAST(:outbox_id AS uuid)
                """
            ),
            params={"outbox_id": str(outbox[0])},
        ).one()
        assert ledger[2] == expected_type
        assert ledger[3] == teacher_user_id

        projected = project_student_timeline(
            session,
            organization_id=organization_id,
            institution_id=institution_id,
            limit=1000,
        )
        assert projected.scanned >= 1
        assert projected.inserted >= 1

        apply_tenant_context(
            session,
            TenantContext(
                organization_id=organization_id,
                institution_id=institution_id,
                user_id=teacher_user_id,
            ),
        )

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

        apply_tenant_context(
            session,
            TenantContext(
                organization_id=organization_id,
                institution_id=institution_id,
                user_id=projection_user_id,
            ),
        )
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

        apply_tenant_context(
            session,
            TenantContext(
                organization_id=organization_id,
                institution_id=institution_id,
                user_id=teacher_user_id,
            ),
        )
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


@pytest.mark.integration
def test_offline_sync_emits_one_canonical_attendance_timeline_fact():
    engine = create_engine(_database_url(), pool_pre_ping=True)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    try:
        (
            organization_id,
            institution_id,
            teacher_user_id,
            class_session_id,
            assignment_id,
            student_profile_id,
            attendance_code_id,
            projection_user_id,
        ) = _fixture()
        apply_tenant_context(
            session,
            TenantContext(
                organization_id=organization_id,
                institution_id=institution_id,
                user_id=teacher_user_id,
            ),
        )
        current = session.exec(
            text(
                "SELECT id, attendance_code_id, minutes_late, note "
                "FROM attendance_records WHERE class_session_id=CAST(:session_id AS uuid) "
                "AND student_section_assignment_id=CAST(:assignment_id AS uuid)"
            ),
            params={
                "session_id": str(class_session_id),
                "assignment_id": str(assignment_id),
            },
        ).first()
        base = TeacherOfflineAttendanceBase(
            attendance_record_id=current[0] if current else None,
            attendance_code_id=current[1] if current else None,
            minutes_late=int(current[2] or 0) if current else 0,
            note=current[3] if current else None,
        )
        desired_minutes = (0 if int(current[2] or 0) else 1) if current else 0
        operation = TeacherOfflineAttendanceOperation(
            operation_id=uuid4(),
            class_session_id=class_session_id,
            base=base,
            desired=TeacherAttendanceMark(
                student_section_assignment_id=assignment_id,
                attendance_code_id=current[1] if current else attendance_code_id,
                minutes_late=desired_minutes,
                note=current[3] if current else None,
            ),
        )
        principal = TeacherPrincipal(
            user_id=teacher_user_id,
            organization_id=organization_id,
            institution_id=institution_id,
            person_id=UUID(str(session.exec(
                text("SELECT person_id FROM user_accounts WHERE id=CAST(:user_id AS uuid)"),
                params={"user_id": str(teacher_user_id)},
            ).one()[0])),
            staff_profile_id=UUID(str(session.exec(
                text("SELECT id FROM staff_profiles WHERE person_id=(SELECT person_id FROM user_accounts WHERE id=CAST(:user_id AS uuid)) AND institution_id=CAST(:institution_id AS uuid)"),
                params={"user_id": str(teacher_user_id), "institution_id": str(institution_id)},
            ).one()[0])),
        )
        started_at = datetime.now(UTC)
        batch = TeacherOfflineSyncBatch(operations=[operation])
        response = sync_teacher_offline_operations(session, principal, batch, commit=False)
        assert response.results[0].status == "APPLIED"
        record_id = response.results[0].result_entity_id
        assert record_id is not None

        outbox_rows = session.exec(
            text(
                "SELECT id, event_type FROM outbox_events "
                "WHERE aggregate_id=CAST(:record_id AS uuid) AND created_at>=:started_at "
                "ORDER BY event_type"
            ),
            params={"record_id": str(record_id), "started_at": started_at},
        ).all()
        assert [row[1] for row in outbox_rows] == [
            "student.attendance.recorded" if current is None else "student.attendance.updated",
            "teacher.attendance.synced",
        ]

        apply_tenant_context(
            session,
            TenantContext(
                organization_id=organization_id,
                institution_id=institution_id,
                user_id=projection_user_id,
            ),
        )
        ingested = ingest_outbox_events(session, institution_id=institution_id, limit=1000)
        assert ingested >= 1
        projected = project_student_timeline(
            session,
            organization_id=organization_id,
            institution_id=institution_id,
            limit=1000,
        )
        assert projected.inserted >= 1
        canonical_outbox_id = next(
            row[0] for row in outbox_rows if row[1].startswith("student.attendance.")
        )
        ledger_id = session.exec(
            text("SELECT id FROM event_ledger WHERE source_outbox_event_id=CAST(:outbox_id AS uuid)"),
            params={"outbox_id": str(canonical_outbox_id)},
        ).one()[0]
        timeline_count = session.exec(
            text("SELECT COUNT(*) FROM student_timeline_entries WHERE ledger_event_id=CAST(:ledger_id AS uuid)"),
            params={"ledger_id": str(ledger_id)},
        ).one()[0]
        assert int(timeline_count) == 1

        apply_tenant_context(
            session,
            TenantContext(
                organization_id=organization_id,
                institution_id=institution_id,
                user_id=teacher_user_id,
            ),
        )

        outbox_count = len(outbox_rows)
        retry = sync_teacher_offline_operations(session, principal, batch, commit=False)
        assert retry.results[0].status == "REPLAYED"
        assert session.exec(
            text("SELECT COUNT(*) FROM outbox_events WHERE aggregate_id=CAST(:record_id AS uuid) AND created_at>=:started_at"),
            params={"record_id": str(record_id), "started_at": started_at},
        ).one()[0] == outbox_count

        session.exec(
            text(
                "UPDATE teaching_assignments SET starts_on=CURRENT_DATE+1, ends_on=NULL "
                "WHERE course_offering_id=(SELECT course_offering_id FROM class_sessions "
                "WHERE id=CAST(:session_id AS uuid)) AND staff_profile_id=CAST(:staff_id AS uuid)"
            ),
            params={"session_id": str(class_session_id), "staff_id": str(principal.staff_profile_id)},
        )
        revoked = sync_teacher_offline_operations(session, principal, batch, commit=False)
        assert revoked.results[0].status == "REJECTED"
        assert revoked.results[0].server_state is None
        assert student_profile_id
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()
