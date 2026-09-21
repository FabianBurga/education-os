"""Staging-only, process-local opaque sessions. No identity comes from the client.

Deploy exactly one worker/replica. Restart revokes every session. No database
credential, JWT, role grant or student data is created here.
"""

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.db.tenant_context import TenantContext, apply_tenant_context

COOKIE = "__Host-education_demo"
TTL = 900
ROLES = {
    "RECTOR": "RECTOR",
    "COORDINATION": "ACADEMIC_COORDINATOR",
    "TEACHER": "TEACHER",
    "STUDENT": "STUDENT",
    "GUARDIAN": "GUARDIAN",
}
# Demo actors may only hold these permissions. This is an additional restriction,
# never a grant: the normal endpoint permissions and RLS remain authoritative.
READ = {
    "agents.use",
    "agents.view",
    "intelligence.read",
    "coord.console.access",
    "coord.analytics.view",
    "student_timeline.read",
    "student_timeline.read_restricted",
    "intervention.read",
    "intervention.suggestion.read",
}
PERMISSIONS = {
    "RECTOR": READ,
    "COORDINATION": READ
    | {
        "coord.signals.manage",
        "coord.cases.manage",
        "intervention.create",
        "intervention.update",
        "intervention.assign",
        "intervention.resolve",
        "intervention.close",
        "intervention.action.manage",
        "intervention.followup.create",
        "intervention.suggestion.review",
        "intervention.suggestion.generate",
    },
    "TEACHER": {
        "teacher.console.access",
        "teacher.classes.view",
        "teacher.attendance.manage",
        "teacher.grades.manage",
        "teacher.tasks.manage",
        "student_timeline.read",
        "intervention.read",
        "intelligence.read",
    },
    "STUDENT": {
        "student.console.access",
        "student.profile.view",
        "student.classes.view",
        "student.schedule.view",
        "student.attendance.view",
        "student.grades.view",
        "student.progress.view",
        "student.notices.view",
    },
    "GUARDIAN": {
        "guardian.console.access",
        "guardian.students.view",
        "guardian.schedule.view",
        "guardian.attendance.view",
        "guardian.grades.view",
        "guardian.progress.view",
        "guardian.notices.view",
        "guardian.notices.acknowledge",
    },
}


def validate_demo_configuration(config=settings):
    if not config.EDUCATION_OS_DEMO_MODE:
        return
    try:
        origin = urlsplit(config.PUBLIC_BASE_URL or "")
        UUID(config.EDUCATION_OS_DEMO_ORGANIZATION_ID)
        UUID(config.EDUCATION_OS_DEMO_INSTITUTION_ID)
        actors = config.EDUCATION_OS_DEMO_PRINCIPALS
        checks = [
            config.APP_ENV == "staging",
            config.EDUCATION_OS_DEMO_SYNTHETIC_ONLY,
            not config.OWNER_DATABASE_URL,
            config.DATABASE_URL.startswith("postgresql"),
            "education_owner" not in config.DATABASE_URL,
            len(config.SECRET_KEY) >= 32 and "change-me" not in config.SECRET_KEY,
            len(config.EDUCATION_OS_DEMO_ACCESS_CODE) >= 24,
            config.EDUCATION_OS_DEMO_ACCESS_CODE != config.SECRET_KEY,
            origin.scheme == "https" and bool(origin.netloc) and not origin.username,
            origin.path in ("", "/") and not origin.query and not origin.fragment,
            set(actors) == set(ROLES),
            len({UUID(value) for value in actors.values()}) == 5,
        ]
        if not all(checks):
            raise ValueError("Invalid configuration")
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Invalid staging demo configuration") from exc


@dataclass(frozen=True)
class DemoSession:
    expires: float
    alias: str | None = None


class SessionStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.sessions: dict[str, DemoSession] = {}
        self.attempts: list[float] = []

    def get(self, token: str | None):
        with self.lock:
            now = time.monotonic()
            self.sessions = {
                key: value for key, value in self.sessions.items() if value.expires > now
            }
            return self.sessions.get(hashlib.sha256((token or "").encode()).hexdigest())

    def revoke(self, token):
        with self.lock:
            self.sessions.pop(hashlib.sha256((token or "").encode()).hexdigest(), None)

    def issue(self, alias=None, previous=None, require_previous=False):
        self.get(None)
        with self.lock:
            previous_key = hashlib.sha256((previous or "").encode()).hexdigest()
            if require_previous and previous_key not in self.sessions:
                raise HTTPException(401, "Demo session expired")
            if len(self.sessions) >= 1000:
                raise HTTPException(429, "Demo capacity reached")
            token = secrets.token_urlsafe(32)
            self.sessions.pop(previous_key, None)
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = DemoSession(
                time.monotonic() + TTL, alias
            )
            return token

    def admit(self):
        # Global bounded limiter avoids spoofable forwarded-IP keys and memory growth.
        with self.lock:
            now = time.monotonic()
            self.attempts = [value for value in self.attempts if value > now - 60]
            if len(self.attempts) >= 10:
                raise HTTPException(429, "Try again later")
            self.attempts.append(now)


store = SessionStore()


def enabled():
    if not settings.EDUCATION_OS_DEMO_MODE:
        raise HTTPException(404, "Not found")


def same_origin(request: Request):
    expected = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    if (
        request.headers.get("origin") != expected
        or request.headers.get("sec-fetch-site") == "cross-site"
    ):
        raise HTTPException(403, "Demo origin denied")


def browser_session(request: Request):
    enabled()
    entry = store.get(request.cookies.get(COOKIE))
    if entry is None:
        raise HTTPException(401, "Demo session expired")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        same_origin(request)
    return entry


def resolve_actor(session: Session, alias: str):
    """Read through education_app + real RLS; verify live identity and least privilege."""
    runtime = session.exec(
        text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")
    ).one()
    if runtime[0] or runtime[1]:
        raise HTTPException(503, "Demo runtime role is not restricted")
    user = UUID(settings.EDUCATION_OS_DEMO_PRINCIPALS[alias])
    org = UUID(settings.EDUCATION_OS_DEMO_ORGANIZATION_ID)
    institution = UUID(settings.EDUCATION_OS_DEMO_INSTITUTION_ID)
    apply_tenant_context(session, TenantContext(org, institution, user))
    params = {"user": str(user), "org": str(org), "institution": str(institution)}
    rows = session.exec(
        text("""
        SELECT r.key, p.key, r.institution_id
        FROM user_accounts u JOIN persons person ON person.id=u.person_id
        JOIN memberships m ON m.user_id=u.id
        JOIN institutions i ON i.id=m.institution_id
        JOIN membership_roles mr ON mr.membership_id=m.id
        JOIN roles r ON r.id=mr.role_id
        LEFT JOIN role_permissions rp ON rp.role_id=r.id
        LEFT JOIN permissions p ON p.id=rp.permission_id
        WHERE u.id=CAST(:user AS uuid) AND u.is_active=true
          AND m.status='ACTIVE' AND i.status='ACTIVE'
          AND i.id=CAST(:institution AS uuid)
          AND i.organization_id=CAST(:org AS uuid)
          AND person.organization_id=CAST(:org AS uuid)
    """),
        params=params,
    ).all()
    permissions = {row[1] for row in rows if row[1]}
    if (
        {row[0] for row in rows} != {ROLES[alias]}
        or any(row[2] != institution for row in rows)
        or not permissions
        or not permissions <= PERMISSIONS[alias]
    ):
        raise HTTPException(403, "Demo profile unavailable")
    return user, org, institution


def demo_identity(request: Request, session: Session):
    entry = browser_session(request)
    if not entry.alias:
        raise HTTPException(401, "Choose a demo profile")
    # No universal staff endpoints, arbitrary mutations, admin or live Copilot.
    path = request.url.path
    roots = ["/api/v1/ui/bootstrap", "/api/v1/me", "/api/v1/campuses"]
    if entry.alias in ("RECTOR", "COORDINATION"):
        roots += [
            "/api/v1/coordination/",
            "/api/v1/intelligence/",
            "/api/v1/student-timeline/",
            "/api/v1/interventions/",
            "/api/v1/agents/",
        ]
    elif entry.alias == "TEACHER":
        roots += [
            "/api/v1/teacher/",
            "/api/v1/student-timeline/",
            "/api/v1/interventions/",
            "/api/v1/intelligence/",
        ]
    elif entry.alias == "STUDENT":
        roots += ["/api/v1/student/"]
    else:
        roots += ["/api/v1/guardian/"]
    allowed = any(path.startswith(root) if root.endswith("/") else path == root for root in roots)
    if not allowed:
        raise HTTPException(403, "Not available in demo")
    if (
        path.startswith("/api/v1/agents/")
        and request.method == "POST"
        and path != "/api/v1/agents/mentor_institution_briefing/runs"
    ):
        raise HTTPException(403, "Not available in demo")
    return resolve_actor(session, entry.alias)
