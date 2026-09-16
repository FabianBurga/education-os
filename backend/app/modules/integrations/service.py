from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.admin_console.schemas import PersonAdminCreate
from app.modules.admin_console.service import create_person
from app.modules.audit.service import record_audit
from app.modules.enrollment.models import AcademicPeriod
from app.modules.enrollment.service import create_enrollment_record
from app.modules.integrations.access import (
    require_integrations_manage,
    require_integrations_run,
    require_integrations_view,
)
from app.modules.integrations.csv_student_enrollment import CsvRow, parse_csv_student_enrollment
from app.modules.integrations.idempotency import integration_idempotency_key
from app.modules.integrations.models import (
    IntegrationConnector,
    IntegrationExternalStudentRef,
    IntegrationRun,
    IntegrationRunEvent,
    IntegrationRunItem,
)
from app.modules.integrations.schemas import (
    CsvStudentEnrollmentPreviewRead,
    IntegrationConnectorCreate,
    IntegrationConnectorRead,
    IntegrationRunItemRead,
    IntegrationRunRead,
)
from app.modules.students.models import StudentProfile
from app.modules.students.service import create_student_profile
from app.modules.tenancy.models import Campus


def _connector_read(connector: IntegrationConnector) -> IntegrationConnectorRead:
    return IntegrationConnectorRead(
        id=connector.id, connector_key=connector.connector_key, connector_type=connector.connector_type,
        display_name=connector.display_name, status=connector.status, config_version=connector.config_version,
        configuration=connector.configuration_json, created_at=connector.created_at, updated_at=connector.updated_at,
    )


def create_connector(session: Session, principal: CurrentPrincipal, payload: IntegrationConnectorCreate) -> IntegrationConnectorRead:
    require_integrations_manage(session, principal)
    connector = IntegrationConnector(
        organization_id=principal.organization_id, institution_id=principal.institution_id,
        connector_key=payload.connector_key, connector_type=payload.connector_type,
        display_name=payload.display_name, configuration_json=payload.configuration,
        created_by_user_id=principal.user_id,
    )
    session.add(connector)
    session.flush()
    record_audit(session, institution_id=principal.institution_id, actor_user_id=principal.user_id,
                 action="INTEGRATION_CONNECTOR_CREATED", entity_type="IntegrationConnector", entity_id=connector.id,
                 metadata={"connector_key": connector.connector_key, "connector_type": connector.connector_type})
    return _connector_read(connector)


def list_connectors(session: Session, principal: CurrentPrincipal) -> list[IntegrationConnectorRead]:
    require_integrations_view(session, principal)
    return [_connector_read(item) for item in session.exec(select(IntegrationConnector).order_by(IntegrationConnector.created_at.desc())).all()]


def get_connector(session: Session, principal: CurrentPrincipal, connector_id: UUID) -> IntegrationConnectorRead:
    require_integrations_view(session, principal)
    connector = session.get(IntegrationConnector, connector_id)
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration connector not found")
    return _connector_read(connector)


def set_connector_status(session: Session, principal: CurrentPrincipal, connector_id: UUID, target: str) -> IntegrationConnectorRead:
    require_integrations_manage(session, principal)
    connector = session.get(IntegrationConnector, connector_id)
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration connector not found")
    connector.status = target
    connector.config_version += 1
    session.add(connector)
    record_audit(session, institution_id=principal.institution_id, actor_user_id=principal.user_id,
                 action=f"INTEGRATION_CONNECTOR_{target}", entity_type="IntegrationConnector", entity_id=connector.id,
                 metadata={"connector_key": connector.connector_key, "config_version": connector.config_version})
    return _connector_read(connector)


def list_runs(session: Session, principal: CurrentPrincipal) -> list[IntegrationRunRead]:
    require_integrations_view(session, principal)
    rows = session.exec(text("""
        SELECT r.id, r.connector_id, r.mapping_id, r.initiated_by_user_id, r.source_kind, r.mode,
               r.source_fingerprint_sha256, r.idempotency_key, r.connector_config_version,
               COALESCE((SELECT e.event_type FROM integration_run_events e WHERE e.run_id=r.id AND e.run_item_id IS NULL
                         ORDER BY e.sequence DESC LIMIT 1), 'CREATED'), r.created_at
        FROM integration_runs r ORDER BY r.created_at DESC
    """)).all()
    return [IntegrationRunRead(id=row[0], connector_id=row[1], mapping_id=row[2], initiated_by_user_id=row[3],
                               source_kind=row[4], mode=row[5], source_fingerprint_sha256=row[6], idempotency_key=row[7],
                               connector_config_version=int(row[8]), status=row[9], created_at=row[10]) for row in rows]


def get_run(session: Session, principal: CurrentPrincipal, run_id: UUID) -> IntegrationRunRead:
    for run in list_runs(session, principal):
        if run.id == run_id:
            return run
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration run not found")


def _run_read(session: Session, run: IntegrationRun) -> IntegrationRunRead:
    latest = session.exec(
        select(IntegrationRunEvent.event_type)
        .where(IntegrationRunEvent.run_id == run.id, IntegrationRunEvent.run_item_id.is_(None))
        .order_by(IntegrationRunEvent.sequence.desc())
        .limit(1)
    ).first()
    return IntegrationRunRead(
        id=run.id, connector_id=run.connector_id, mapping_id=run.mapping_id,
        initiated_by_user_id=run.initiated_by_user_id, source_kind=run.source_kind,
        mode=run.mode, source_fingerprint_sha256=run.source_fingerprint_sha256,
        idempotency_key=run.idempotency_key, connector_config_version=run.connector_config_version,
        status=latest or "CREATED", created_at=run.created_at,
    )


def _append_run_event(
    session: Session,
    principal: CurrentPrincipal,
    run: IntegrationRun,
    event_type: str,
    *,
    run_item_id: UUID | None = None,
    metadata: dict | None = None,
) -> IntegrationRunEvent:
    sequence = int(session.exec(
        select(func.coalesce(func.max(IntegrationRunEvent.sequence), 0))
        .where(IntegrationRunEvent.run_id == run.id)
    ).one()) + 1
    event = IntegrationRunEvent(
        organization_id=principal.organization_id, institution_id=principal.institution_id,
        run_id=run.id, run_item_id=run_item_id, sequence=sequence, event_type=event_type,
        actor_user_id=principal.user_id, metadata_json=metadata or {},
    )
    session.add(event)
    return event


def _csv_row_detail(row: CsvRow, idempotency_key: str) -> dict:
    return {
        "source_row_number": row.row_number,
        "external_student_id": row.external_student_id,
        "given_names": row.given_names,
        "family_names": row.family_names,
        "academic_period_code": row.academic_period_code,
        "campus_id": row.campus_id,
        "student_code": row.student_code,
        "enrollment_number": row.enrollment_number,
        "enrollment_status": row.enrollment_status,
        "enrolled_on": row.enrolled_on.isoformat() if row.enrolled_on else None,
        "idempotency_key": idempotency_key,
    }


def _validate_csv_row(
    session: Session,
    principal: CurrentPrincipal,
    connector: IntegrationConnector,
    source_fingerprint: str,
    row: CsvRow,
    seen_external_ids: set[str],
) -> tuple[str, str | None, dict]:
    key = integration_idempotency_key(
        organization_id=str(principal.organization_id), institution_id=str(principal.institution_id),
        connector_id=str(connector.id), external_source=f"csv:{source_fingerprint}",
        source_record_identity=row.external_student_id, canonical_entity_type="STUDENT_ENROLLMENT",
        operation_class="CREATE",
    )
    detail = _csv_row_detail(row, key)
    if row.external_student_id in seen_external_ids:
        return "CONFLICT", "EXTERNAL_ID_DUPLICATE", detail
    seen_external_ids.add(row.external_student_id)
    existing_ref = session.exec(select(IntegrationExternalStudentRef.id).where(
        IntegrationExternalStudentRef.connector_id == connector.id,
        IntegrationExternalStudentRef.external_student_id == row.external_student_id,
    )).first()
    if existing_ref is not None:
        return "CONFLICT", "ALREADY_APPLIED", detail
    period = session.exec(select(AcademicPeriod.id).where(
        AcademicPeriod.organization_id == principal.organization_id,
        AcademicPeriod.institution_id == principal.institution_id,
        AcademicPeriod.code == row.academic_period_code,
    )).first()
    if period is None:
        return "INVALID", "ACADEMIC_PERIOD_NOT_FOUND", detail
    try:
        campus_id = UUID(row.campus_id)
    except ValueError:
        return "INVALID", "CSV_ROW_INVALID", detail
    campus = session.exec(select(Campus.id).where(
        Campus.id == campus_id, Campus.institution_id == principal.institution_id,
    )).first()
    if campus is None:
        return "INVALID", "CAMPUS_NOT_FOUND", detail
    if row.student_code:
        existing_student = session.exec(select(StudentProfile.id).where(
            StudentProfile.organization_id == principal.organization_id,
            StudentProfile.institution_id == principal.institution_id,
            StudentProfile.student_code == row.student_code,
        )).first()
        if existing_student is not None:
            return "CONFLICT", "STUDENT_IDENTITY_CONFLICT", detail
    detail["academic_period_id"] = str(period)
    return "VALID", None, detail


def preview_csv_student_enrollment(
    session: Session,
    principal: CurrentPrincipal,
    connector_id: UUID,
    payload: bytes,
    source_filename: str | None,
) -> CsvStudentEnrollmentPreviewRead:
    require_integrations_run(session, principal)
    connector = session.get(IntegrationConnector, connector_id)
    if connector is None or connector.connector_type != "CSV_STUDENT_ENROLLMENT":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CSV student/enrollment connector not found")
    if connector.status != "ENABLED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Integration connector is disabled")
    fingerprint, rows = parse_csv_student_enrollment(payload)
    run_key = integration_idempotency_key(
        organization_id=str(principal.organization_id), institution_id=str(principal.institution_id),
        connector_id=str(connector.id), external_source="csv", source_record_identity=fingerprint,
        canonical_entity_type="CSV_STUDENT_ENROLLMENT", operation_class="PREVIEW",
    )
    existing = session.exec(select(IntegrationRun).where(
        IntegrationRun.connector_id == connector.id, IntegrationRun.idempotency_key == run_key,
    )).first()
    if existing is not None:
        return CsvStudentEnrollmentPreviewRead(run=_run_read(session, existing), **_summary(session, existing.id))
    run = IntegrationRun(
        organization_id=principal.organization_id, institution_id=principal.institution_id,
        connector_id=connector.id, initiated_by_user_id=principal.user_id, source_kind="FILE",
        mode="DRY_RUN", source_fingerprint_sha256=fingerprint, idempotency_key=run_key,
        connector_config_version=connector.config_version,
    )
    session.add(run)
    session.flush()
    filename = (source_filename or "upload.csv").replace("\\", "/").split("/")[-1][:160]
    _append_run_event(session, principal, run, "CREATED", metadata={
        "workflow": "CSV_STUDENT_ENROLLMENT", "source_filename": filename,
        "source_sha256": fingerprint, "total_rows": len(rows), "dry_run": True,
    })
    _append_run_event(session, principal, run, "VALIDATING")
    seen_external_ids: set[str] = set()
    for row in rows:
        item_status, error_code, detail = _validate_csv_row(
            session, principal, connector, fingerprint, row, seen_external_ids,
        )
        source_item_fingerprint = integration_idempotency_key(
            organization_id=str(principal.organization_id), institution_id=str(principal.institution_id),
            connector_id=str(connector.id), external_source=f"csv:{fingerprint}",
            source_record_identity=f"row:{row.row_number}", canonical_entity_type="STUDENT_ENROLLMENT",
            operation_class="CREATE",
        )
        session.add(IntegrationRunItem(
            organization_id=principal.organization_id, institution_id=principal.institution_id, run_id=run.id,
            source_item_key=f"row:{row.row_number}", source_item_fingerprint_sha256=source_item_fingerprint,
            canonical_entity_type="STUDENT_ENROLLMENT", operation_class="CREATE", status=item_status,
            error_code=error_code, detail_json=detail,
        ))
    session.flush()
    summary = _summary(session, run.id)
    _append_run_event(session, principal, run, "VALIDATED", metadata=summary)
    record_audit(session, institution_id=principal.institution_id, actor_user_id=principal.user_id,
                 action="INTEGRATION_CSV_PREVIEWED", entity_type="IntegrationRun", entity_id=run.id,
                 metadata={"source_sha256": fingerprint, **summary})
    return CsvStudentEnrollmentPreviewRead(run=_run_read(session, run), **summary)


def _summary(session: Session, run_id: UUID) -> dict[str, int]:
    rows = session.exec(select(IntegrationRunItem.status).where(IntegrationRunItem.run_id == run_id)).all()
    return {
        "total_rows": len(rows), "valid_rows": sum(value == "VALID" for value in rows),
        "invalid_rows": sum(value == "INVALID" for value in rows),
        "conflict_rows": sum(value == "CONFLICT" for value in rows),
    }


def list_run_items(session: Session, principal: CurrentPrincipal, run_id: UUID) -> list[IntegrationRunItemRead]:
    get_run(session, principal, run_id)
    items = session.exec(select(IntegrationRunItem).where(IntegrationRunItem.run_id == run_id).order_by(IntegrationRunItem.created_at)).all()
    result: list[IntegrationRunItemRead] = []
    for item in items:
        event = session.exec(select(IntegrationRunEvent).where(
            IntegrationRunEvent.run_item_id == item.id,
        ).order_by(IntegrationRunEvent.sequence.desc()).limit(1)).first()
        status_value, error_code, result_entity_id = item.status, item.error_code, item.result_entity_id
        if event is not None and event.event_type == "ITEM_APPLIED":
            status_value, error_code = "APPLIED", None
            result_entity_id = UUID(event.metadata_json["student_profile_id"])
        elif event is not None and event.event_type == "ITEM_FAILED":
            status_value, error_code = "FAILED", event.metadata_json.get("error_code", "DOMAIN_COMMAND_FAILED")
        result.append(IntegrationRunItemRead(
            id=item.id, source_item_key=item.source_item_key, canonical_entity_type=item.canonical_entity_type,
            operation_class=item.operation_class, status=status_value, error_code=error_code,
            detail=item.detail_json, result_entity_id=result_entity_id, created_at=item.created_at,
        ))
    return result


def apply_csv_student_enrollment(session: Session, principal: CurrentPrincipal, run_id: UUID) -> IntegrationRunRead:
    require_integrations_run(session, principal)
    run = session.get(IntegrationRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration run not found")
    connector = session.get(IntegrationConnector, run.connector_id)
    if connector is None or connector.connector_type != "CSV_STUDENT_ENROLLMENT":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Run is not a CSV student/enrollment run")
    if connector.status != "ENABLED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Integration connector is disabled")
    _append_run_event(session, principal, run, "APPLYING")
    for item in session.exec(select(IntegrationRunItem).where(
        IntegrationRunItem.run_id == run.id, IntegrationRunItem.status == "VALID",
    )).all():
        prior = session.exec(select(IntegrationRunEvent.id).where(
            IntegrationRunEvent.run_item_id == item.id,
            IntegrationRunEvent.event_type == "ITEM_APPLIED",
        )).first()
        if prior is not None:
            continue
        detail = item.detail_json
        try:
            with session.begin_nested():
                person = create_person(session, principal, PersonAdminCreate(
                    given_names=detail["given_names"], family_names=detail["family_names"],
                ))
                session.flush()
                student = create_student_profile(
                    session, principal, person_id=person.id, student_code=detail.get("student_code"),
                )
                session.flush()
                enrollment = create_enrollment_record(
                    session, principal, student_profile_id=student.id,
                    academic_period_id=UUID(detail["academic_period_id"]), campus_id=UUID(detail["campus_id"]),
                    enrollment_number=detail.get("enrollment_number"), status_value=detail["enrollment_status"],
                    enrolled_on=date.fromisoformat(detail["enrolled_on"]) if detail.get("enrolled_on") else None,
                )
                session.add(IntegrationExternalStudentRef(
                    organization_id=principal.organization_id, institution_id=principal.institution_id,
                    connector_id=connector.id, external_student_id=detail["external_student_id"],
                    student_profile_id=student.id, created_run_id=run.id,
                ))
                session.flush()
            _append_run_event(session, principal, run, "ITEM_APPLIED", run_item_id=item.id, metadata={
                "student_profile_id": str(student.id), "enrollment_id": str(enrollment.id),
                "external_student_id": detail["external_student_id"],
            })
        except (HTTPException, IntegrityError, ValueError):
            _append_run_event(session, principal, run, "ITEM_FAILED", run_item_id=item.id,
                              metadata={"error_code": "DOMAIN_COMMAND_FAILED"})
    _append_run_event(session, principal, run, "COMPLETED", metadata={"applied_at": datetime.now(UTC).isoformat()})
    record_audit(session, institution_id=principal.institution_id, actor_user_id=principal.user_id,
                 action="INTEGRATION_CSV_APPLIED", entity_type="IntegrationRun", entity_id=run.id)
    return _run_read(session, run)
