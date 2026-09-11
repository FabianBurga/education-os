from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.audit.models import AuditLog
from app.modules.automation.schemas import TaskComplete
from app.modules.automation.service import (
    acknowledge_task,
    complete_task,
    list_case_timeline,
    run_engine,
    tick_engine,
)
from app.modules.coordination_console.schemas import (
    AttentionItem,
    CaseWorkspaceItem,
    CoordinationSummary,
    CoordinationTask,
)
from app.modules.intelligence.schemas import SignalResolve
from app.modules.intelligence.service import (
    academic_trend,
    attendance_trend,
    rector_overview,
    refresh_signals,
    resolve_signal,
    section_drilldown,
)


def _count(session: Session, sql: str) -> int:
    row = session.exec(text(sql)).first()
    return int(row[0] if row is not None else 0)


def _audit(
    session: Session,
    principal: CurrentPrincipal,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    metadata: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            institution_id=principal.institution_id,
            actor_user_id=principal.user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=metadata or {},
        )
    )


def coordination_summary(session: Session) -> CoordinationSummary:
    overview = rector_overview(session)
    task_row = session.exec(
        text(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE status IN ('OPEN', 'ACKNOWLEDGED', 'ESCALATED')
                ) AS open_tasks,
                COUNT(*) FILTER (WHERE status = 'ACKNOWLEDGED') AS acknowledged,
                COUNT(*) FILTER (WHERE status = 'ESCALATED') AS escalated
            FROM automation_tasks
            """
        )
    ).first()

    return CoordinationSummary(
        **overview.model_dump(),
        high_signals=_count(
            session,
            """
            SELECT COUNT(*)
            FROM intelligence_signals
            WHERE status = 'OPEN'
              AND severity = 'HIGH'
            """,
        ),
        open_cases=_count(
            session,
            """
            SELECT COUNT(*)
            FROM automation_cases
            WHERE status = 'OPEN'
            """,
        ),
        open_tasks=int(task_row[0] or 0) if task_row else 0,
        acknowledged_tasks=int(task_row[1] or 0) if task_row else 0,
        escalated_tasks=int(task_row[2] or 0) if task_row else 0,
    )


def attention_queue(session: Session) -> list[AttentionItem]:
    rows = session.exec(
        text(
            """
            SELECT
                sig.id AS signal_id,
                sig.student_profile_id,
                trim(concat_ws(' ', p.given_names, p.family_names)) AS student_name,
                sp.student_code,
                sig.section_id,
                sec.name AS section_name,
                gl.name AS grade_name,
                sig.signal_type,
                sig.severity,
                sig.metric_value,
                sig.threshold_value,
                sig.summary,
                sig.detected_at,
                sig.last_seen_at,
                c.id AS case_id,
                c.status AS case_status,
                t.id AS task_id,
                t.title AS task_title,
                t.status AS task_status,
                t.assigned_role_code,
                t.due_at
            FROM intelligence_signals sig
            JOIN student_profiles sp ON sp.id = sig.student_profile_id
            JOIN persons p ON p.id = sp.person_id
            LEFT JOIN sections sec ON sec.id = sig.section_id
            LEFT JOIN grade_levels gl ON gl.id = sec.grade_level_id
            LEFT JOIN LATERAL (
                SELECT ac.id, ac.status, ac.opened_at
                FROM automation_cases ac
                WHERE ac.intelligence_signal_id = sig.id
                ORDER BY ac.opened_at DESC
                LIMIT 1
            ) c ON true
            LEFT JOIN LATERAL (
                SELECT
                    at.id,
                    at.title,
                    at.status,
                    at.assigned_role_code,
                    at.due_at,
                    at.created_at
                FROM automation_tasks at
                WHERE at.automation_case_id = c.id
                ORDER BY
                    CASE at.status
                        WHEN 'ESCALATED' THEN 4
                        WHEN 'OPEN' THEN 3
                        WHEN 'ACKNOWLEDGED' THEN 2
                        ELSE 1
                    END DESC,
                    at.created_at DESC
                LIMIT 1
            ) t ON true
            WHERE sig.status = 'OPEN'
            ORDER BY
                CASE sig.severity
                    WHEN 'HIGH' THEN 3
                    WHEN 'MEDIUM' THEN 2
                    ELSE 1
                END DESC,
                sig.last_seen_at DESC
            """
        )
    ).all()

    items: list[AttentionItem] = []
    for row in rows:
        items.append(
            AttentionItem(
                signal_id=row[0],
                student_profile_id=row[1],
                student_name=row[2],
                student_code=row[3],
                section_id=row[4],
                section_name=row[5],
                grade_name=row[6],
                signal_type=row[7],
                severity=row[8],
                metric_value=float(row[9]),
                threshold_value=float(row[10]),
                summary=row[11],
                detected_at=row[12],
                last_seen_at=row[13],
                case_id=row[14],
                case_status=row[15],
                task_id=row[16],
                task_title=row[17],
                task_status=row[18],
                assigned_role_code=row[19],
                due_at=row[20],
            )
        )
    return items


def case_workspace(session: Session) -> list[CaseWorkspaceItem]:
    rows = session.exec(
        text(
            """
            SELECT
                ac.id AS case_id,
                ac.intelligence_signal_id,
                ac.student_profile_id,
                trim(concat_ws(' ', p.given_names, p.family_names)) AS student_name,
                sp.student_code,
                ac.section_id,
                sec.name AS section_name,
                gl.name AS grade_name,
                sig.signal_type,
                sig.severity,
                sig.summary,
                ac.status,
                ac.opened_at,
                ac.closed_at,
                ac.outcome_note
            FROM automation_cases ac
            JOIN intelligence_signals sig ON sig.id = ac.intelligence_signal_id
            JOIN student_profiles sp ON sp.id = ac.student_profile_id
            JOIN persons p ON p.id = sp.person_id
            LEFT JOIN sections sec ON sec.id = ac.section_id
            LEFT JOIN grade_levels gl ON gl.id = sec.grade_level_id
            ORDER BY
                CASE ac.status WHEN 'OPEN' THEN 2 ELSE 1 END DESC,
                ac.opened_at DESC
            """
        )
    ).all()

    result: list[CaseWorkspaceItem] = []
    for row in rows:
        task_rows = session.exec(
            text(
                """
                SELECT
                    id,
                    automation_case_id,
                    assigned_role_code,
                    title,
                    description,
                    status,
                    due_at,
                    escalate_at,
                    acknowledged_at,
                    completed_at,
                    completion_note
                FROM automation_tasks
                WHERE automation_case_id = CAST(:case_id AS uuid)
                ORDER BY created_at
                """
            ).bindparams(case_id=str(row[0]))
        ).all()

        tasks = [
            CoordinationTask(
                id=task[0],
                automation_case_id=task[1],
                assigned_role_code=task[2],
                title=task[3],
                description=task[4],
                status=task[5],
                due_at=task[6],
                escalate_at=task[7],
                acknowledged_at=task[8],
                completed_at=task[9],
                completion_note=task[10],
            )
            for task in task_rows
        ]

        result.append(
            CaseWorkspaceItem(
                case_id=row[0],
                signal_id=row[1],
                student_profile_id=row[2],
                student_name=row[3],
                student_code=row[4],
                section_id=row[5],
                section_name=row[6],
                grade_name=row[7],
                signal_type=row[8],
                severity=row[9],
                signal_summary=row[10],
                case_status=row[11],
                opened_at=row[12],
                closed_at=row[13],
                outcome_note=row[14],
                tasks=tasks,
            )
        )
    return result


def coordination_sections(session: Session):
    return section_drilldown(session)


def coordination_attendance_trend(session: Session, days: int):
    return attendance_trend(session, days=days)


def coordination_academic_trend(session: Session):
    return academic_trend(session)


def coordination_case_timeline(session: Session, case_id: UUID):
    return list_case_timeline(session, case_id)


def refresh_coordination_signals(
    session: Session,
    principal: CurrentPrincipal,
):
    result = refresh_signals(session, principal)
    _audit(
        session,
        principal,
        "COORD_SIGNALS_REFRESHED",
        "IntelligenceSignal",
        None,
        result.model_dump(),
    )
    session.commit()
    return result


def resolve_coordination_signal(
    session: Session,
    principal: CurrentPrincipal,
    signal_id: UUID,
    payload: SignalResolve,
):
    signal = resolve_signal(session, signal_id, payload)
    _audit(
        session,
        principal,
        "COORD_SIGNAL_RESOLVED",
        "IntelligenceSignal",
        signal.id,
        {"resolution_note": payload.resolution_note},
    )
    session.commit()
    return signal


def run_coordination_engine(
    session: Session,
    principal: CurrentPrincipal,
):
    result = run_engine(session, principal)
    _audit(
        session,
        principal,
        "COORD_ENGINE_RUN",
        "AutomationCase",
        None,
        result.model_dump(),
    )
    session.commit()
    return result


def tick_coordination_engine(
    session: Session,
    principal: CurrentPrincipal,
):
    result = tick_engine(session, principal)
    _audit(
        session,
        principal,
        "COORD_ENGINE_TICK",
        "AutomationTask",
        None,
        result.model_dump(),
    )
    session.commit()
    return result


def acknowledge_coordination_task(
    session: Session,
    principal: CurrentPrincipal,
    task_id: UUID,
):
    task = acknowledge_task(session, principal, task_id)
    _audit(
        session,
        principal,
        "COORD_TASK_ACKNOWLEDGED",
        "AutomationTask",
        task.id,
        {"case_id": str(task.automation_case_id)},
    )
    session.commit()
    return task


def complete_coordination_task(
    session: Session,
    principal: CurrentPrincipal,
    task_id: UUID,
    payload: TaskComplete,
):
    task = complete_task(session, principal, task_id, payload)
    _audit(
        session,
        principal,
        "COORD_TASK_COMPLETED",
        "AutomationTask",
        task.id,
        {
            "case_id": str(task.automation_case_id),
            "completion_note": payload.completion_note,
        },
    )
    session.commit()
    return task
