from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.audit.service import record_audit
from app.modules.communications.models import (
    Communication,
    CommunicationRecipient,
    CommunicationTarget,
    CommunicationTemplate,
)
from app.modules.communications.schemas import (
    CommunicationCreate,
    CommunicationDeliveryReport,
    CommunicationDetail,
    CommunicationPreview,
    CommunicationPublishResult,
    CommunicationRead,
    CommunicationSummary,
    CommunicationTargetRead,
    CommunicationTargetsReplace,
    CommunicationTemplateCreate,
    CommunicationTemplateRead,
    CommunicationTemplateUpdate,
    CommunicationUpdate,
    DeliveryRecipientRead,
    TargetOption,
)
from app.modules.events.service import enqueue_event
from app.modules.family_portal.models import FamilyNotice

TARGET_TYPES = {
    "INSTITUTION",
    "CAMPUS",
    "SECTION",
    "COURSE",
    "STUDENT",
    "FAMILY",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def _message(
    session: Session,
    principal: CurrentPrincipal,
    communication_id: UUID,
) -> Communication:
    entity = session.get(Communication, communication_id)
    if (
        entity is None
        or entity.institution_id != principal.institution_id
        or entity.organization_id != principal.organization_id
    ):
        raise HTTPException(status_code=404, detail="Communication not found")
    return entity


def _template(
    session: Session,
    principal: CurrentPrincipal,
    template_id: UUID,
) -> CommunicationTemplate:
    entity = session.get(CommunicationTemplate, template_id)
    if (
        entity is None
        or entity.institution_id != principal.institution_id
        or entity.organization_id != principal.organization_id
    ):
        raise HTTPException(status_code=404, detail="Communication template not found")
    return entity


def _require_draft(entity: Communication) -> None:
    if entity.status != "DRAFT":
        raise HTTPException(
            status_code=409,
            detail="Only draft communications can be edited",
        )


def _counts_for_message(session: Session, communication_id: UUID) -> tuple[int, int]:
    row = session.exec(
        text(
            """
            SELECT
                (SELECT COUNT(*) FROM communication_targets
                 WHERE communication_id = CAST(:communication_id AS uuid)),
                (SELECT COUNT(*) FROM communication_recipients
                 WHERE communication_id = CAST(:communication_id AS uuid))
            """
        ).bindparams(communication_id=str(communication_id))
    ).first()
    if row is None:
        return 0, 0
    return int(row[0] or 0), int(row[1] or 0)


def _to_read(session: Session, entity: Communication) -> CommunicationRead:
    target_count, recipient_count = _counts_for_message(session, entity.id)
    return CommunicationRead(
        id=entity.id,
        template_id=entity.template_id,
        title=entity.title,
        body=entity.body,
        notice_type=entity.notice_type,
        requires_acknowledgement=entity.requires_acknowledgement,
        status=entity.status,
        published_at=entity.published_at,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        target_count=target_count,
        recipient_count=recipient_count,
    )


def communication_summary(session: Session) -> CommunicationSummary:
    row = session.exec(
        text(
            """
            SELECT
                COUNT(*) FILTER (WHERE c.status = 'DRAFT'),
                COUNT(*) FILTER (WHERE c.status = 'PUBLISHED'),
                COUNT(*) FILTER (WHERE c.status = 'ARCHIVED'),
                (SELECT COUNT(*) FROM communication_templates t
                 WHERE t.status = 'ACTIVE'),
                (SELECT COUNT(*) FROM communication_recipients r
                 WHERE r.delivery_status = 'DELIVERED'),
                (
                    SELECT COUNT(*)
                    FROM communication_recipients r
                    JOIN family_notice_receipts fnr
                      ON fnr.family_notice_id = r.family_notice_id
                     AND fnr.guardian_profile_id = r.guardian_profile_id
                    WHERE fnr.read_at IS NOT NULL
                ),
                (
                    SELECT COUNT(*)
                    FROM communication_recipients r
                    JOIN family_notice_receipts fnr
                      ON fnr.family_notice_id = r.family_notice_id
                     AND fnr.guardian_profile_id = r.guardian_profile_id
                    WHERE fnr.acknowledged_at IS NOT NULL
                )
            FROM communications c
            """
        )
    ).first()
    if row is None:
        return CommunicationSummary(
            draft_messages=0,
            published_messages=0,
            archived_messages=0,
            active_templates=0,
            delivered_recipients=0,
            read_recipients=0,
            acknowledged_recipients=0,
        )
    return CommunicationSummary(
        draft_messages=int(row[0] or 0),
        published_messages=int(row[1] or 0),
        archived_messages=int(row[2] or 0),
        active_templates=int(row[3] or 0),
        delivered_recipients=int(row[4] or 0),
        read_recipients=int(row[5] or 0),
        acknowledged_recipients=int(row[6] or 0),
    )


def list_templates(session: Session) -> list[CommunicationTemplateRead]:
    rows = session.exec(
        select(CommunicationTemplate).order_by(
            CommunicationTemplate.status,
            CommunicationTemplate.name,
        )
    ).all()
    return [
        CommunicationTemplateRead(
            id=row.id,
            name=row.name,
            title_template=row.title_template,
            body_template=row.body_template,
            notice_type=row.notice_type,
            requires_acknowledgement=row.requires_acknowledgement,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


def create_template(
    session: Session,
    principal: CurrentPrincipal,
    payload: CommunicationTemplateCreate,
) -> CommunicationTemplateRead:
    duplicate = session.exec(
        select(CommunicationTemplate).where(
            CommunicationTemplate.institution_id == principal.institution_id,
            CommunicationTemplate.name == payload.name,
        )
    ).first()
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Template name already exists")

    now = utcnow()
    entity = CommunicationTemplate(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        created_by_user_id=principal.user_id,
        created_at=now,
        updated_at=now,
        **payload.model_dump(),
    )
    session.add(entity)
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="COMMUNICATION_TEMPLATE_CREATED",
        entity_type="communication_template",
        entity_id=entity.id,
        metadata={"name": entity.name},
    )
    session.commit()
    session.refresh(entity)
    return CommunicationTemplateRead(
        id=entity.id,
        name=entity.name,
        title_template=entity.title_template,
        body_template=entity.body_template,
        notice_type=entity.notice_type,
        requires_acknowledgement=entity.requires_acknowledgement,
        status=entity.status,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def update_template(
    session: Session,
    principal: CurrentPrincipal,
    template_id: UUID,
    payload: CommunicationTemplateUpdate,
) -> CommunicationTemplateRead:
    entity = _template(session, principal, template_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(entity, key, value)
    entity.updated_at = utcnow()
    session.add(entity)
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="COMMUNICATION_TEMPLATE_UPDATED",
        entity_type="communication_template",
        entity_id=entity.id,
        metadata={"fields": sorted(data)},
    )
    session.commit()
    session.refresh(entity)
    return CommunicationTemplateRead(
        id=entity.id,
        name=entity.name,
        title_template=entity.title_template,
        body_template=entity.body_template,
        notice_type=entity.notice_type,
        requires_acknowledgement=entity.requires_acknowledgement,
        status=entity.status,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def list_messages(session: Session) -> list[CommunicationRead]:
    entities = session.exec(
        select(Communication).order_by(Communication.created_at.desc())
    ).all()
    return [_to_read(session, entity) for entity in entities]


def message_detail(
    session: Session,
    principal: CurrentPrincipal,
    communication_id: UUID,
) -> CommunicationDetail:
    entity = _message(session, principal, communication_id)
    targets = session.exec(
        select(CommunicationTarget)
        .where(CommunicationTarget.communication_id == communication_id)
        .order_by(
            CommunicationTarget.target_type,
            CommunicationTarget.target_label,
        )
    ).all()
    base = _to_read(session, entity)
    return CommunicationDetail(
        **base.model_dump(),
        targets=[
            CommunicationTargetRead(
                id=target.id,
                target_type=target.target_type,
                target_id=target.target_id,
                target_label=target.target_label,
            )
            for target in targets
        ],
    )


def create_message(
    session: Session,
    principal: CurrentPrincipal,
    payload: CommunicationCreate,
) -> CommunicationRead:
    if payload.template_id is not None:
        _template(session, principal, payload.template_id)

    now = utcnow()
    entity = Communication(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        created_by_user_id=principal.user_id,
        created_at=now,
        updated_at=now,
        **payload.model_dump(),
    )
    session.add(entity)
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="COMMUNICATION_CREATED",
        entity_type="communication",
        entity_id=entity.id,
        metadata={"notice_type": entity.notice_type},
    )
    session.commit()
    session.refresh(entity)
    return _to_read(session, entity)


def update_message(
    session: Session,
    principal: CurrentPrincipal,
    communication_id: UUID,
    payload: CommunicationUpdate,
) -> CommunicationRead:
    entity = _message(session, principal, communication_id)
    _require_draft(entity)

    data = payload.model_dump(exclude_unset=True)
    if "template_id" in data and data["template_id"] is not None:
        _template(session, principal, data["template_id"])

    for key, value in data.items():
        setattr(entity, key, value)
    entity.updated_at = utcnow()
    session.add(entity)
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="COMMUNICATION_UPDATED",
        entity_type="communication",
        entity_id=entity.id,
        metadata={"fields": sorted(data)},
    )
    session.commit()
    session.refresh(entity)
    return _to_read(session, entity)


def _target_label(
    session: Session,
    principal: CurrentPrincipal,
    target_type: str,
    target_id: UUID,
) -> str:
    if target_type == "INSTITUTION":
        if target_id != principal.institution_id:
            raise HTTPException(
                status_code=404,
                detail="Institution target must match signed institution",
            )
        row = session.exec(
            text(
                """
                SELECT name
                FROM institutions
                WHERE id = CAST(:target_id AS uuid)
                """
            ).bindparams(target_id=str(target_id))
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Institution target not found")
        return str(row[0])

    query_map = {
        "CAMPUS": """
            SELECT name
            FROM campuses
            WHERE id = CAST(:target_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
        """,
        "SECTION": """
            SELECT concat(gl.name, ' · ', s.name)
            FROM sections s
            JOIN grade_levels gl ON gl.id = s.grade_level_id
            WHERE s.id = CAST(:target_id AS uuid)
              AND s.institution_id = CAST(:institution_id AS uuid)
              AND s.status = 'ACTIVE'
        """,
        "COURSE": """
            SELECT concat(sub.name, ' · ', s.name)
            FROM course_offerings co
            JOIN subjects sub ON sub.id = co.subject_id
            JOIN sections s ON s.id = co.section_id
            WHERE co.id = CAST(:target_id AS uuid)
              AND co.institution_id = CAST(:institution_id AS uuid)
              AND co.status = 'ACTIVE'
              AND s.status = 'ACTIVE'
        """,
        "STUDENT": """
            SELECT trim(concat_ws(' ', p.given_names, p.family_names))
            FROM student_profiles sp
            JOIN persons p ON p.id = sp.person_id
            WHERE sp.id = CAST(:target_id AS uuid)
              AND sp.institution_id = CAST(:institution_id AS uuid)
              AND sp.status = 'ACTIVE'
        """,
        "FAMILY": """
            SELECT fh.name
            FROM family_households fh
            WHERE fh.id = CAST(:target_id AS uuid)
              AND fh.institution_id = CAST(:institution_id AS uuid)
              AND fh.status = 'ACTIVE'
        """,
    }
    sql = query_map.get(target_type)
    if sql is None:
        raise HTTPException(status_code=422, detail="Unsupported communication target")
    row = session.exec(
        text(sql).bindparams(
            target_id=str(target_id),
            institution_id=str(principal.institution_id),
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{target_type} target not found")
    return str(row[0])


def replace_targets(
    session: Session,
    principal: CurrentPrincipal,
    communication_id: UUID,
    payload: CommunicationTargetsReplace,
) -> list[CommunicationTargetRead]:
    entity = _message(session, principal, communication_id)
    _require_draft(entity)

    normalized: list[tuple[str, UUID, str]] = []
    seen: set[tuple[str, UUID]] = set()
    for item in payload.targets:
        target_type = str(item.target_type)
        if target_type not in TARGET_TYPES:
            raise HTTPException(status_code=422, detail="Unsupported target type")
        key = (target_type, item.target_id)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            (
                target_type,
                item.target_id,
                _target_label(
                    session,
                    principal,
                    target_type,
                    item.target_id,
                ),
            )
        )

    session.exec(
        text(
            """
            DELETE FROM communication_targets
            WHERE communication_id = CAST(:communication_id AS uuid)
            """
        ).bindparams(communication_id=str(communication_id))
    )

    result: list[CommunicationTarget] = []
    for target_type, target_id, target_label in normalized:
        target = CommunicationTarget(
            organization_id=principal.organization_id,
            institution_id=principal.institution_id,
            communication_id=communication_id,
            target_type=target_type,
            target_id=target_id,
            target_label=target_label,
        )
        session.add(target)
        result.append(target)

    entity.updated_at = utcnow()
    session.add(entity)
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="COMMUNICATION_TARGETS_REPLACED",
        entity_type="communication",
        entity_id=entity.id,
        metadata={
            "target_count": len(result),
            "target_types": sorted({item.target_type for item in result}),
        },
    )
    session.commit()

    return [
        CommunicationTargetRead(
            id=item.id,
            target_type=item.target_type,
            target_id=item.target_id,
            target_label=item.target_label,
        )
        for item in result
    ]


def target_options(
    session: Session,
    principal: CurrentPrincipal,
    target_type: str,
) -> list[TargetOption]:
    if target_type not in TARGET_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported target type")

    if target_type == "INSTITUTION":
        row = session.exec(
            text(
                """
                SELECT id, name
                FROM institutions
                WHERE id = CAST(:institution_id AS uuid)
                """
            ).bindparams(institution_id=str(principal.institution_id))
        ).first()
        if row is None:
            return []
        return [TargetOption(id=row[0], label=row[1], secondary="Institución")]

    queries = {
        "CAMPUS": """
            SELECT c.id, c.name, 'Campus'
            FROM campuses c
            WHERE c.institution_id = CAST(:institution_id AS uuid)
            ORDER BY c.name
        """,
        "SECTION": """
            SELECT
                s.id,
                concat(gl.name, ' · ', s.name),
                concat(COALESCE(c.name, 'Campus'), ' · ', COALESCE(ap.name, 'Periodo'))
            FROM sections s
            JOIN grade_levels gl ON gl.id = s.grade_level_id
            LEFT JOIN campuses c ON c.id = s.campus_id
            LEFT JOIN academic_periods ap ON ap.id = s.academic_period_id
            WHERE s.institution_id = CAST(:institution_id AS uuid)
              AND s.status = 'ACTIVE'
            ORDER BY gl.sort_order, s.name
        """,
        "COURSE": """
            SELECT
                co.id,
                concat(sub.name, ' · ', s.name),
                concat(COALESCE(gl.name, ''), ' · ', COALESCE(c.name, ''))
            FROM course_offerings co
            JOIN subjects sub ON sub.id = co.subject_id
            JOIN sections s ON s.id = co.section_id
            LEFT JOIN grade_levels gl ON gl.id = s.grade_level_id
            LEFT JOIN campuses c ON c.id = s.campus_id
            WHERE co.institution_id = CAST(:institution_id AS uuid)
              AND co.status = 'ACTIVE'
              AND s.status = 'ACTIVE'
            ORDER BY sub.name, s.name
        """,
        "STUDENT": """
            SELECT DISTINCT
                sp.id,
                trim(concat_ws(' ', p.given_names, p.family_names)),
                concat(
                    COALESCE(gl.name, ''),
                    CASE WHEN gl.name IS NOT NULL AND s.name IS NOT NULL THEN ' · ' ELSE '' END,
                    COALESCE(s.name, '')
                )
            FROM student_profiles sp
            JOIN persons p ON p.id = sp.person_id
            LEFT JOIN enrollments e
              ON e.student_profile_id = sp.id
             AND e.status = 'ACTIVE'
            LEFT JOIN student_section_assignments ssa
              ON ssa.enrollment_id = e.id
             AND ssa.status = 'ACTIVE'
            LEFT JOIN sections s ON s.id = ssa.section_id
            LEFT JOIN grade_levels gl ON gl.id = s.grade_level_id
            WHERE sp.institution_id = CAST(:institution_id AS uuid)
              AND sp.status = 'ACTIVE'
            ORDER BY 2
        """,
        "FAMILY": """
            SELECT
                fh.id,
                fh.name,
                concat(
                    COUNT(*) FILTER (WHERE fm.member_role = 'STUDENT'),
                    ' estudiante(s)'
                )
            FROM family_households fh
            LEFT JOIN family_members fm ON fm.family_id = fh.id
            WHERE fh.institution_id = CAST(:institution_id AS uuid)
              AND fh.status = 'ACTIVE'
            GROUP BY fh.id, fh.name
            ORDER BY fh.name
        """,
    }
    rows = session.exec(
        text(queries[target_type]).bindparams(
            institution_id=str(principal.institution_id)
        )
    ).all()
    return [
        TargetOption(
            id=row[0],
            label=str(row[1]),
            secondary=str(row[2]) if row[2] else None,
        )
        for row in rows
    ]


def _student_ids_for_target(
    session: Session,
    principal: CurrentPrincipal,
    target_type: str,
    target_id: UUID,
) -> set[UUID]:
    base = {
        "INSTITUTION": """
            SELECT DISTINCT sp.id
            FROM student_profiles sp
            JOIN enrollments e
              ON e.student_profile_id = sp.id
             AND e.status = 'ACTIVE'
            WHERE sp.institution_id = CAST(:institution_id AS uuid)
              AND sp.status = 'ACTIVE'
        """,
        "CAMPUS": """
            SELECT DISTINCT sp.id
            FROM student_profiles sp
            JOIN enrollments e
              ON e.student_profile_id = sp.id
             AND e.status = 'ACTIVE'
            WHERE sp.institution_id = CAST(:institution_id AS uuid)
              AND sp.status = 'ACTIVE'
              AND e.campus_id = CAST(:target_id AS uuid)
        """,
        "SECTION": """
            SELECT DISTINCT sp.id
            FROM student_profiles sp
            JOIN enrollments e
              ON e.student_profile_id = sp.id
             AND e.status = 'ACTIVE'
            JOIN student_section_assignments ssa
              ON ssa.enrollment_id = e.id
             AND ssa.status = 'ACTIVE'
            JOIN sections s
              ON s.id = ssa.section_id
             AND s.status = 'ACTIVE'
            WHERE sp.institution_id = CAST(:institution_id AS uuid)
              AND sp.status = 'ACTIVE'
              AND ssa.section_id = CAST(:target_id AS uuid)
        """,
        "COURSE": """
            SELECT DISTINCT sp.id
            FROM course_offerings co
            JOIN student_section_assignments ssa
              ON ssa.section_id = co.section_id
             AND ssa.status = 'ACTIVE'
            JOIN enrollments e
              ON e.id = ssa.enrollment_id
             AND e.status = 'ACTIVE'
            JOIN student_profiles sp ON sp.id = e.student_profile_id
            WHERE co.id = CAST(:target_id AS uuid)
              AND co.institution_id = CAST(:institution_id AS uuid)
              AND co.status = 'ACTIVE'
              AND EXISTS (
                  SELECT 1
                  FROM sections s
                  WHERE s.id = co.section_id
                    AND s.status = 'ACTIVE'
              )
              AND sp.status = 'ACTIVE'
        """,
        "STUDENT": """
            SELECT DISTINCT sp.id
            FROM student_profiles sp
            JOIN enrollments e
              ON e.student_profile_id = sp.id
             AND e.status = 'ACTIVE'
            WHERE sp.id = CAST(:target_id AS uuid)
              AND sp.institution_id = CAST(:institution_id AS uuid)
              AND sp.status = 'ACTIVE'
        """,
        "FAMILY": """
            SELECT DISTINCT sp.id
            FROM family_households fh
            JOIN family_members fm
              ON fm.family_id = fh.id
             AND fm.member_role = 'STUDENT'
            JOIN student_profiles sp
              ON sp.person_id = fm.person_id
             AND sp.institution_id = fh.institution_id
             AND sp.status = 'ACTIVE'
            JOIN enrollments e
              ON e.student_profile_id = sp.id
             AND e.status = 'ACTIVE'
            WHERE fh.id = CAST(:target_id AS uuid)
              AND fh.institution_id = CAST(:institution_id AS uuid)
              AND fh.status = 'ACTIVE'
        """,
    }
    params = {
        "institution_id": str(principal.institution_id),
        "target_id": str(target_id),
    }
    if target_type == "INSTITUTION":
        if target_id != principal.institution_id:
            return set()
        rows = session.exec(
            text(base[target_type]).bindparams(
                institution_id=str(principal.institution_id)
            )
        ).all()
    else:
        rows = session.exec(
            text(base[target_type]).bindparams(**params)
        ).all()
    return {row[0] for row in rows}


def _resolved_students(
    session: Session,
    principal: CurrentPrincipal,
    communication_id: UUID,
) -> set[UUID]:
    targets = session.exec(
        select(CommunicationTarget).where(
            CommunicationTarget.communication_id == communication_id
        )
    ).all()
    students: set[UUID] = set()
    for target in targets:
        students |= _student_ids_for_target(
            session,
            principal,
            target.target_type,
            target.target_id,
        )
    return students


def _recipient_pairs(
    session: Session,
    principal: CurrentPrincipal,
    student_ids: set[UUID],
) -> list[tuple[UUID, UUID]]:
    if not student_ids:
        return []

    rows = session.exec(
        text(
            """
            SELECT
                pa.guardian_profile_id,
                pa.student_profile_id
            FROM guardian_student_portal_access pa
            JOIN guardian_profiles gp ON gp.id = pa.guardian_profile_id
            JOIN student_profiles sp ON sp.id = pa.student_profile_id
            WHERE pa.institution_id = CAST(:institution_id AS uuid)
              AND pa.status = 'ACTIVE'
              AND gp.status = 'ACTIVE'
              AND sp.status = 'ACTIVE'
            """
        ).bindparams(institution_id=str(principal.institution_id))
    ).all()

    pairs = {
        (row[0], row[1])
        for row in rows
        if row[1] in student_ids
    }
    return sorted(pairs, key=lambda pair: (str(pair[1]), str(pair[0])))


def preview_message(
    session: Session,
    principal: CurrentPrincipal,
    communication_id: UUID,
) -> CommunicationPreview:
    entity = _message(session, principal, communication_id)
    targets = session.exec(
        select(CommunicationTarget).where(
            CommunicationTarget.communication_id == communication_id
        )
    ).all()
    student_ids = _resolved_students(session, principal, communication_id)
    pairs = _recipient_pairs(session, principal, student_ids)
    reachable_students = {student_id for _, student_id in pairs}
    return CommunicationPreview(
        communication_id=entity.id,
        target_count=len(targets),
        target_students=len(student_ids),
        reachable_students=len(reachable_students),
        guardian_recipients=len(pairs),
        unreachable_students=max(0, len(student_ids) - len(reachable_students)),
    )


def publish_message(
    session: Session,
    principal: CurrentPrincipal,
    communication_id: UUID,
) -> CommunicationPublishResult:
    entity = _message(session, principal, communication_id)
    _require_draft(entity)

    targets = session.exec(
        select(CommunicationTarget).where(
            CommunicationTarget.communication_id == communication_id
        )
    ).all()
    if not targets:
        raise HTTPException(
            status_code=409,
            detail="At least one communication target is required",
        )

    student_ids = _resolved_students(session, principal, communication_id)
    pairs = _recipient_pairs(session, principal, student_ids)
    if not pairs:
        raise HTTPException(
            status_code=409,
            detail="No active family recipients were resolved",
        )

    by_student: dict[UUID, list[UUID]] = defaultdict(list)
    for guardian_id, student_id in pairs:
        by_student[student_id].append(guardian_id)

    now = utcnow()
    notices_created = 0
    for student_id, guardian_ids in by_student.items():
        notice = FamilyNotice(
            organization_id=principal.organization_id,
            institution_id=principal.institution_id,
            student_profile_id=student_id,
            notice_type=entity.notice_type,
            title=entity.title,
            body=entity.body,
            requires_acknowledgement=entity.requires_acknowledgement,
            status="PUBLISHED",
            published_at=now,
            created_by_user_id=principal.user_id,
            created_at=now,
        )
        session.add(notice)
        session.flush()
        notices_created += 1

        for guardian_id in guardian_ids:
            session.add(
                CommunicationRecipient(
                    organization_id=principal.organization_id,
                    institution_id=principal.institution_id,
                    communication_id=entity.id,
                    guardian_profile_id=guardian_id,
                    student_profile_id=student_id,
                    family_notice_id=notice.id,
                    delivery_status="DELIVERED",
                    delivered_at=now,
                    created_at=now,
                )
            )

    entity.status = "PUBLISHED"
    entity.published_by_user_id = principal.user_id
    entity.published_at = now
    entity.updated_at = now
    session.add(entity)

    publication_payload = {
        "target_count": len(targets),
        "students_reached": len(by_student),
        "guardian_recipients": len(pairs),
        "family_notices_created": notices_created,
    }
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="COMMUNICATION_PUBLISHED",
        entity_type="communication",
        entity_id=entity.id,
        metadata=publication_payload,
    )
    enqueue_event(
        session,
        institution_id=principal.institution_id,
        event_type="COMMUNICATION_PUBLISHED",
        aggregate_type="communication",
        aggregate_id=entity.id,
        payload=publication_payload,
    )
    session.commit()

    return CommunicationPublishResult(
        communication_id=entity.id,
        published_at=now,
        students_reached=len(by_student),
        guardian_recipients=len(pairs),
        family_notices_created=notices_created,
    )


def archive_message(
    session: Session,
    principal: CurrentPrincipal,
    communication_id: UUID,
) -> CommunicationRead:
    entity = _message(session, principal, communication_id)
    if entity.status == "ARCHIVED":
        return _to_read(session, entity)

    entity.status = "ARCHIVED"
    entity.updated_at = utcnow()
    session.add(entity)
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="COMMUNICATION_ARCHIVED",
        entity_type="communication",
        entity_id=entity.id,
        metadata={"published_at": str(entity.published_at) if entity.published_at else None},
    )
    session.commit()
    session.refresh(entity)
    return _to_read(session, entity)


def delivery_report(
    session: Session,
    principal: CurrentPrincipal,
    communication_id: UUID,
) -> CommunicationDeliveryReport:
    entity = _message(session, principal, communication_id)
    rows = session.exec(
        text(
            """
            SELECT
                r.guardian_profile_id,
                trim(concat_ws(' ', gp_person.given_names, gp_person.family_names)),
                r.student_profile_id,
                trim(concat_ws(' ', sp_person.given_names, sp_person.family_names)),
                r.family_notice_id,
                r.delivered_at,
                fnr.read_at,
                fnr.acknowledged_at
            FROM communication_recipients r
            JOIN guardian_profiles gp ON gp.id = r.guardian_profile_id
            JOIN persons gp_person ON gp_person.id = gp.person_id
            JOIN student_profiles sp ON sp.id = r.student_profile_id
            JOIN persons sp_person ON sp_person.id = sp.person_id
            LEFT JOIN family_notice_receipts fnr
              ON fnr.family_notice_id = r.family_notice_id
             AND fnr.guardian_profile_id = r.guardian_profile_id
            WHERE r.communication_id = CAST(:communication_id AS uuid)
            ORDER BY gp_person.family_names, gp_person.given_names,
                     sp_person.family_names, sp_person.given_names
            """
        ).bindparams(communication_id=str(communication_id))
    ).all()

    recipients: list[DeliveryRecipientRead] = []
    read_count = 0
    acknowledged_count = 0
    for row in rows:
        status = "DELIVERED"
        if row[6] is not None:
            status = "READ"
            read_count += 1
        if row[7] is not None:
            status = "ACKNOWLEDGED"
            acknowledged_count += 1
        recipients.append(
            DeliveryRecipientRead(
                guardian_profile_id=row[0],
                guardian_name=row[1],
                student_profile_id=row[2],
                student_name=row[3],
                family_notice_id=row[4],
                status=status,
                delivered_at=row[5],
                read_at=row[6],
                acknowledged_at=row[7],
            )
        )

    return CommunicationDeliveryReport(
        communication_id=entity.id,
        title=entity.title,
        requires_acknowledgement=entity.requires_acknowledgement,
        recipients_total=len(recipients),
        delivered=len(recipients),
        read=read_count,
        acknowledged=acknowledged_count,
        recipients=recipients,
    )
