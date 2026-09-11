from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.automation.models import (
    AutomationCase,
    AutomationRule,
    AutomationTask,
    AutomationTimelineEvent,
)
from app.modules.automation.schemas import (
    AutomationRuleCreate,
    BootstrapRulesResult,
    EngineRunResult,
    EngineTickResult,
    TaskComplete,
)
from app.modules.intelligence.models import IntelligenceSignal

SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}

DEFAULT_RULES = (
    {
        "code": "ATTENDANCE_REVIEW",
        "name": "Revisión de riesgo de asistencia",
        "signal_type": "ATTENDANCE_RISK",
        "minimum_severity": "MEDIUM",
        "assignee_role_code": "INSPECTOR",
        "task_title": "Revisar patrón de ausencias",
        "due_in_hours": 24,
        "escalate_after_hours": 48,
    },
    {
        "code": "LATE_FOLLOWUP",
        "name": "Seguimiento de atrasos repetidos",
        "signal_type": "REPEATED_LATE",
        "minimum_severity": "MEDIUM",
        "assignee_role_code": "TUTOR",
        "task_title": "Dar seguimiento a atrasos repetidos",
        "due_in_hours": 48,
        "escalate_after_hours": 72,
    },
    {
        "code": "ACADEMIC_REVIEW",
        "name": "Revisión de riesgo académico",
        "signal_type": "ACADEMIC_RISK",
        "minimum_severity": "MEDIUM",
        "assignee_role_code": "ACADEMIC_COORDINATOR",
        "task_title": "Revisar desempeño académico",
        "due_in_hours": 48,
        "escalate_after_hours": 96,
    },
    {
        "code": "MISSING_WORK_FOLLOWUP",
        "name": "Seguimiento de evaluaciones faltantes",
        "signal_type": "MISSING_WORK",
        "minimum_severity": "MEDIUM",
        "assignee_role_code": "TEACHER",
        "task_title": "Revisar evaluaciones faltantes",
        "due_in_hours": 72,
        "escalate_after_hours": 120,
    },
)


def rule_matches(rule: AutomationRule, signal: IntelligenceSignal) -> bool:
    return (
        rule.is_enabled
        and rule.signal_type == signal.signal_type
        and SEVERITY_RANK.get(signal.severity, 0) >= SEVERITY_RANK.get(rule.minimum_severity, 999)
    )


def _timeline(
    session: Session,
    principal: CurrentPrincipal,
    case_id: UUID,
    event_type: str,
    message: str,
    task_id: UUID | None = None,
) -> None:
    session.add(
        AutomationTimelineEvent(
            organization_id=principal.organization_id,
            institution_id=principal.institution_id,
            automation_case_id=case_id,
            automation_task_id=task_id,
            event_type=event_type,
            message=message,
            actor_user_id=getattr(principal, "user_id", None),
        )
    )


def list_rules(session: Session):
    return session.exec(select(AutomationRule).order_by(AutomationRule.code)).all()


def create_rule(
    session: Session,
    principal: CurrentPrincipal,
    payload: AutomationRuleCreate,
):
    entity = AutomationRule(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def bootstrap_default_rules(
    session: Session,
    principal: CurrentPrincipal,
) -> BootstrapRulesResult:
    created = 0
    existing = 0
    for data in DEFAULT_RULES:
        found = session.exec(
            select(AutomationRule).where(AutomationRule.code == data["code"])
        ).first()
        if found:
            existing += 1
            continue
        session.add(
            AutomationRule(
                organization_id=principal.organization_id,
                institution_id=principal.institution_id,
                **data,
            )
        )
        created += 1

    session.commit()
    return BootstrapRulesResult(created=created, existing=existing)


def list_cases(session: Session):
    return session.exec(select(AutomationCase).order_by(AutomationCase.opened_at.desc())).all()


def get_case(session: Session, case_id: UUID) -> AutomationCase:
    case = session.get(AutomationCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Automation case not found")
    return case


def list_case_tasks(session: Session, case_id: UUID):
    get_case(session, case_id)
    return session.exec(
        select(AutomationTask)
        .where(AutomationTask.automation_case_id == case_id)
        .order_by(AutomationTask.created_at)
    ).all()


def list_case_timeline(session: Session, case_id: UUID):
    get_case(session, case_id)
    return session.exec(
        select(AutomationTimelineEvent)
        .where(AutomationTimelineEvent.automation_case_id == case_id)
        .order_by(AutomationTimelineEvent.created_at)
    ).all()


def run_engine(
    session: Session,
    principal: CurrentPrincipal,
) -> EngineRunResult:
    signals = list(
        session.exec(select(IntelligenceSignal).where(IntelligenceSignal.status == "OPEN")).all()
    )
    rules = list(
        session.exec(select(AutomationRule).where(AutomationRule.is_enabled.is_(True))).all()
    )

    matched_pairs = 0
    cases_created = 0
    tasks_created = 0
    now = datetime.now(UTC)

    for signal in signals:
        for rule in rules:
            if not rule_matches(rule, signal):
                continue
            matched_pairs += 1

            existing_case = session.exec(
                select(AutomationCase).where(
                    AutomationCase.intelligence_signal_id == signal.id,
                    AutomationCase.automation_rule_id == rule.id,
                )
            ).first()
            if existing_case:
                continue

            case = AutomationCase(
                organization_id=principal.organization_id,
                institution_id=principal.institution_id,
                intelligence_signal_id=signal.id,
                automation_rule_id=rule.id,
                student_profile_id=signal.student_profile_id,
                section_id=signal.section_id,
                status="OPEN",
                opened_at=now,
            )
            session.add(case)
            session.flush()
            cases_created += 1

            task = AutomationTask(
                organization_id=principal.organization_id,
                institution_id=principal.institution_id,
                automation_case_id=case.id,
                assigned_role_code=rule.assignee_role_code,
                task_type="REVIEW",
                title=rule.task_title,
                description=signal.summary,
                status="OPEN",
                due_at=now + timedelta(hours=rule.due_in_hours),
                escalate_at=now + timedelta(hours=rule.escalate_after_hours),
            )
            session.add(task)
            session.flush()
            tasks_created += 1

            _timeline(
                session,
                principal,
                case.id,
                "CASE_OPENED",
                f"Caso creado por regla {rule.code}.",
            )
            _timeline(
                session,
                principal,
                case.id,
                "TASK_CREATED",
                f"Tarea asignada al rol {rule.assignee_role_code}.",
                task.id,
            )

    session.commit()
    return EngineRunResult(
        signals_scanned=len(signals),
        matched_pairs=matched_pairs,
        cases_created=cases_created,
        tasks_created=tasks_created,
    )


def acknowledge_task(
    session: Session,
    principal: CurrentPrincipal,
    task_id: UUID,
) -> AutomationTask:
    task = session.get(AutomationTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Automation task not found")
    if task.status not in {"OPEN", "ESCALATED"}:
        raise HTTPException(status_code=409, detail="Task cannot be acknowledged")

    task.status = "ACKNOWLEDGED"
    task.acknowledged_at = datetime.now(UTC)
    session.add(task)
    _timeline(
        session,
        principal,
        task.automation_case_id,
        "TASK_ACKNOWLEDGED",
        "La tarea fue reconocida por un usuario.",
        task.id,
    )
    session.commit()
    session.refresh(task)
    return task


def complete_task(
    session: Session,
    principal: CurrentPrincipal,
    task_id: UUID,
    payload: TaskComplete,
) -> AutomationTask:
    task = session.get(AutomationTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Automation task not found")
    if task.status == "COMPLETED":
        raise HTTPException(status_code=409, detail="Task is already completed")

    now = datetime.now(UTC)
    task.status = "COMPLETED"
    task.completed_at = now
    task.completion_note = payload.completion_note
    session.add(task)

    _timeline(
        session,
        principal,
        task.automation_case_id,
        "TASK_COMPLETED",
        payload.completion_note,
        task.id,
    )

    remaining = session.exec(
        select(AutomationTask).where(
            AutomationTask.automation_case_id == task.automation_case_id,
            AutomationTask.id != task.id,
            AutomationTask.status != "COMPLETED",
        )
    ).first()

    if remaining is None:
        case = get_case(session, task.automation_case_id)
        case.status = "CLOSED"
        case.closed_at = now
        case.outcome_note = payload.completion_note
        session.add(case)
        _timeline(
            session,
            principal,
            case.id,
            "CASE_CLOSED",
            "Caso cerrado tras completar todas sus tareas.",
        )

    session.commit()
    session.refresh(task)
    return task


def tick_engine(
    session: Session,
    principal: CurrentPrincipal,
) -> EngineTickResult:
    now = datetime.now(UTC)
    overdue = list(
        session.exec(
            select(AutomationTask).where(
                AutomationTask.status.in_(["OPEN", "ACKNOWLEDGED"]),
                AutomationTask.escalate_at <= now,
            )
        ).all()
    )

    for task in overdue:
        task.status = "ESCALATED"
        session.add(task)
        _timeline(
            session,
            principal,
            task.automation_case_id,
            "TASK_ESCALATED",
            "Tarea escalada automáticamente por vencimiento.",
            task.id,
        )

    session.commit()
    return EngineTickResult(tasks_escalated=len(overdue))
