from __future__ import annotations

import os
import sys
import types
import uuid
from pathlib import Path

import psycopg
from sqlalchemy import text
from sqlmodel import Session, create_engine

NAMESPACE = uuid.UUID("0e0d8a06-76cc-53ef-8f25-cbe38d0c6d6a")


def uid(name: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, name)


IDS = {
    "org": uid("uo-pilot-org"),
    "institution": uid("uo-pilot-institution"),
    "teacher_person": uid("uo-pilot-teacher-person-1"),
    "teacher_user": uid("uo-pilot-teacher-user-1"),
    "teacher_profile": uid("uo-pilot-teacher-profile-1"),
}


def app_pg_url() -> str:
    return os.getenv(
        "DATABASE_URL_PG",
        "postgresql://education_app:education_app_dev@localhost:5432/education_os",
    )


def owner_pg_url() -> str:
    return os.getenv(
        "OWNER_DATABASE_URL_PG",
        "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
    )


def sqlalchemy_url(raw: str) -> str:
    if raw.startswith("postgresql+"):
        return raw
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


def set_env() -> None:
    os.environ.setdefault("DATABASE_URL", sqlalchemy_url(app_pg_url()))
    os.environ.setdefault("OWNER_DATABASE_URL", sqlalchemy_url(owner_pg_url()))


def set_context(session: Session) -> None:
    for key, value in (
        ("app.organization_id", IDS["org"]),
        ("app.institution_id", IDS["institution"]),
        ("app.user_id", IDS["teacher_user"]),
    ):
        session.exec(
            text("SELECT set_config(:k, :v, true)").bindparams(
                k=key,
                v=str(value),
            )
        )


def target_state() -> dict[str, object]:
    with psycopg.connect(owner_pg_url()) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.id, c.id, t.status, t.acknowledged_at, t.completed_at,
                   t.completion_note, c.status
            FROM automation_tasks t
            JOIN automation_cases c ON c.id=t.automation_case_id
            JOIN intelligence_signals s ON s.id=c.intelligence_signal_id
            JOIN student_profiles sp ON sp.id=c.student_profile_id
            WHERE sp.student_code='PILOT-EST-05'
              AND s.signal_type='MISSING_WORK'
            """
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("Controlled-pilot MISSING_WORK task not found")
        return {
            "task_id": row[0],
            "case_id": row[1],
            "task_status": row[2],
            "acknowledged_at": row[3],
            "completed_at": row[4],
            "completion_note": row[5],
            "case_status": row[6],
        }


def timeline_count(case_id: uuid.UUID) -> int:
    with psycopg.connect(owner_pg_url()) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM automation_timeline_events
            WHERE automation_case_id=%s
            """,
            (case_id,),
        )
        return int(cur.fetchone()[0])


def build_complete_payload(task_complete: type) -> object:
    values = {}
    for name, field in task_complete.model_fields.items():
        lower = name.lower()
        if "note" in lower or "comment" in lower or "reason" in lower:
            values[name] = "Controlled pilot human review completed after rc4 RLS hotfix."
        elif field.is_required():
            annotation = field.annotation
            if annotation is str:
                values[name] = "Controlled pilot human review completed after rc4 RLS hotfix."
            elif annotation is bool:
                values[name] = True
            elif annotation is int:
                values[name] = 1
            else:
                raise RuntimeError(
                    f"Unsupported required TaskComplete field: {name} {annotation!r}"
                )
    return task_complete(**values)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_automation_rls_hotfix.py <repo_root>")
        return 2

    repo_root = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(repo_root / "backend"))
    set_env()

    from app.modules.automation.schemas import TaskComplete
    from app.modules.automation.service import acknowledge_task, complete_task

    principal = types.SimpleNamespace(
        user_id=IDS["teacher_user"],
        organization_id=IDS["org"],
        institution_id=IDS["institution"],
        person_id=IDS["teacher_person"],
        staff_profile_id=IDS["teacher_profile"],
    )

    before = target_state()
    task_id = before["task_id"]
    case_id = before["case_id"]
    before_timeline = timeline_count(case_id)

    if before["task_status"] not in {"OPEN", "ACKNOWLEDGED", "COMPLETED"}:
        raise RuntimeError(f"Unexpected target task state: {before}")

    engine = create_engine(sqlalchemy_url(app_pg_url()), pool_pre_ping=True)

    if before["task_status"] == "OPEN":
        with Session(engine) as session:
            set_context(session)
            task = acknowledge_task(session, principal, task_id)
            status = getattr(task.status, "value", task.status)
            if status != "ACKNOWLEDGED":
                raise RuntimeError(f"acknowledge_task returned status={status}")
        print("Real acknowledge_task commit/refresh: PASSED")
    elif before["task_status"] == "ACKNOWLEDGED":
        print("Real acknowledge_task: already committed by rc3 failing gate; resume preserved.")
    else:
        print("Target task already COMPLETED; completion call skipped.")

    mid = target_state()
    if mid["task_status"] == "ACKNOWLEDGED":
        payload = build_complete_payload(TaskComplete)
        with Session(engine) as session:
            set_context(session)
            task = complete_task(session, principal, task_id, payload)
            status = getattr(task.status, "value", task.status)
            if status != "COMPLETED":
                raise RuntimeError(f"complete_task returned status={status}")
        print("Real complete_task commit/refresh: PASSED")

    after = target_state()
    after_timeline = timeline_count(case_id)

    if after["task_status"] != "COMPLETED":
        raise RuntimeError(f"Final task is not COMPLETED: {after}")
    if not after["completion_note"]:
        raise RuntimeError("Completed task has no completion note")
    if after_timeline <= before_timeline and before["task_status"] != "COMPLETED":
        raise RuntimeError(
            f"Timeline did not grow: before={before_timeline}, after={after_timeline}"
        )

    print(
        "Automation RLS hotfix runtime verification: PASSED "
        f"(task={after['task_status']}, case={after['case_status']}, "
        f"timeline={before_timeline}->{after_timeline})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
