from __future__ import annotations

import os
import uuid

from sqlalchemy import text
from sqlmodel import Session, create_engine

NAMESPACE = uuid.UUID("e412806c-4c8e-5f75-a6ab-c80bc2b50958")


def uid(name: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, name)


IDS = {
    "org": uid("pilot-org-a"),
    "inst": uid("pilot-inst-a"),
    "guardian_user": uid("pilot-guardian-user"),
    "guardian_person": uid("pilot-guardian-person"),
    "guardian_profile": uid("pilot-guardian-profile"),
    "student": uid("pilot-student-profile"),
    "notice": uid("pilot-notice"),
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


def sqlalchemy_url(url: str) -> str:
    if url.startswith("postgresql+"):
        return url
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def main() -> int:
    # Importing app settings requires canonical env names.
    os.environ.setdefault("DATABASE_URL", sqlalchemy_url(app_pg_url()))
    os.environ.setdefault("OWNER_DATABASE_URL", sqlalchemy_url(owner_pg_url()))

    from app.api.access import GuardianPrincipal
    from app.modules.family_portal.service import (
        child_attendance,
        child_grades,
        child_overview,
        children,
        list_portal_notices,
    )

    engine = create_engine(sqlalchemy_url(app_pg_url()), pool_pre_ping=True)

    principal = GuardianPrincipal(
        user_id=IDS["guardian_user"],
        organization_id=IDS["org"],
        institution_id=IDS["inst"],
        person_id=IDS["guardian_person"],
        guardian_profile_id=IDS["guardian_profile"],
    )

    with Session(engine) as session:
        for key, value in [
            ("app.organization_id", IDS["org"]),
            ("app.institution_id", IDS["inst"]),
            ("app.user_id", IDS["guardian_user"]),
        ]:
            session.exec(text("SELECT set_config(:k, :v, true)").bindparams(k=key, v=str(value)))

        kids = children(session, principal)
        overview = child_overview(session, principal, IDS["student"])
        attendance = child_attendance(session, principal, IDS["student"], 30)
        grades = child_grades(session, principal, IDS["student"])
        notices = list_portal_notices(session, principal)

    checks = [
        ("children", len(kids) == 1),
        ("child_id", bool(kids) and kids[0].student_profile_id == IDS["student"]),
        ("attendance_items", len(attendance) == 5),
        ("absence_count", overview.absence_count == 2),
        ("attendance_rate", overview.attendance_rate == 60.0),
        ("grade_items", len(grades) == 2),
        ("academic_average", overview.academic_average_percent == 55.0),
        ("notices", len(notices) == 1),
        ("notice_id", bool(notices) and notices[0].id == IDS["notice"]),
    ]

    failed = [name for name, ok in checks if not ok]
    if failed:
        print("Family Portal UUID pilot smoke: FAILED -> " + ", ".join(failed))
        return 1

    print("Family Portal children query: OK")
    print("Family Portal overview: OK")
    print("Family Portal attendance: OK")
    print("Family Portal grades: OK")
    print("Family Portal notices: OK")
    print("Family Portal UUID pilot smoke: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
