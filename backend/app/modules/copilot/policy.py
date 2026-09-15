from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.m21_access import (
    has_any_role,
    has_permission,
    is_teacher,
    teacher_has_student_scope,
)

COPILOT_MANAGER_ROLES = {
    "SYSTEM_ADMIN",
    "RECTOR",
    "ACADEMIC_COORDINATOR",
}
FOUNDATION_INTENTS = {
    "INSTITUTION_RISK_SUMMARY",
    "STUDENT_SUPPORT_SUMMARY",
}


@dataclass(frozen=True, slots=True)
class GateFacts:
    intent: str
    has_use_permission: bool
    is_manager: bool
    is_teacher_actor: bool
    target_student_profile_id: UUID | None
    teacher_has_target_scope: bool
    policy_enabled: bool
    prompt_enabled: bool
    model_eligible: bool
    daily_run_count: int
    max_daily_runs_per_user: int


@dataclass(frozen=True, slots=True)
class GateDecision:
    allowed: bool
    code: str


@dataclass(frozen=True, slots=True)
class GovernedSelection:
    decision: GateDecision
    policy_key: str | None = None
    policy_version: int | None = None
    prompt_key: str | None = None
    prompt_version: int | None = None
    output_schema_version: str | None = None
    provider_key: str | None = None
    model_key: str | None = None
    model_config_version: int | None = None
    max_evidence_items: int = 0


def decide_pre_invocation(facts: GateFacts) -> GateDecision:
    if not facts.has_use_permission:
        return GateDecision(False, "MISSING_COPILOT_USE")
    if facts.intent not in FOUNDATION_INTENTS:
        return GateDecision(False, "INTENT_NOT_ENABLED")
    if facts.intent == "INSTITUTION_RISK_SUMMARY" and not facts.is_manager:
        return GateDecision(False, "MANAGER_SCOPE_REQUIRED")
    if facts.intent == "STUDENT_SUPPORT_SUMMARY":
        if facts.target_student_profile_id is None:
            return GateDecision(False, "STUDENT_TARGET_REQUIRED")
        if (
            facts.is_teacher_actor
            and not facts.is_manager
            and not facts.teacher_has_target_scope
        ):
            return GateDecision(False, "STUDENT_SCOPE_DENIED")
        if not facts.is_manager and not facts.is_teacher_actor:
            return GateDecision(False, "ACTOR_SCOPE_DENIED")
    if not facts.policy_enabled:
        return GateDecision(False, "POLICY_DISABLED")
    if not facts.prompt_enabled:
        return GateDecision(False, "PROMPT_DISABLED")
    if not facts.model_eligible:
        return GateDecision(False, "NO_ELIGIBLE_MODEL")
    if facts.daily_run_count >= facts.max_daily_runs_per_user:
        return GateDecision(False, "QUOTA_EXCEEDED")
    return GateDecision(True, "ALLOW")


def _enabled_policy(
    session: Session,
    principal: CurrentPrincipal,
) -> tuple[str, int, int, int] | None:
    row = session.exec(
        text(
            """
            SELECT
                policy_key,
                version,
                max_daily_runs_per_user,
                max_evidence_items
            FROM copilot_policy_versions
            WHERE organization_id = CAST(:organization_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND policy_key = 'governed_copilot'
              AND status = 'ENABLED'
            ORDER BY version DESC
            LIMIT 1
            """
        ),
        params={
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
        },
    ).first()
    if row is None:
        return None
    return str(row[0]), int(row[1]), int(row[2]), int(row[3])


def _enabled_prompt(
    session: Session,
    principal: CurrentPrincipal,
    *,
    intent: str,
) -> tuple[str, int, str] | None:
    row = session.exec(
        text(
            """
            SELECT prompt_key, version, output_schema_version
            FROM copilot_prompt_versions
            WHERE organization_id = CAST(:organization_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND intent = :intent
              AND status = 'ENABLED'
            ORDER BY version DESC
            LIMIT 1
            """
        ),
        params={
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
            "intent": intent,
        },
    ).first()
    if row is None:
        return None
    return str(row[0]), int(row[1]), str(row[2])


def _eligible_model(
    session: Session,
    principal: CurrentPrincipal,
) -> tuple[str, str, int] | None:
    row = session.exec(
        text(
            """
            SELECT provider_key, model_key, config_version
            FROM copilot_model_registry
            WHERE organization_id = CAST(:organization_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND enabled = true
              AND policy_eligible = true
            ORDER BY config_version DESC, provider_key, model_key
            LIMIT 1
            """
        ),
        params={
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
        },
    ).first()
    if row is None:
        return None
    return str(row[0]), str(row[1]), int(row[2])


def _daily_run_count(
    session: Session,
    principal: CurrentPrincipal,
) -> int:
    now = datetime.now(UTC)
    row = session.exec(
        text(
            """
            SELECT COUNT(*)
            FROM copilot_runs
            WHERE organization_id = CAST(:organization_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND actor_user_id = CAST(:actor_user_id AS uuid)
              AND created_at >= :day_start
            """
        ),
        params={
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
            "actor_user_id": str(principal.user_id),
            "day_start": now.replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            ),
        },
    ).one()
    return int(row[0])


def evaluate_pre_invocation_policy(
    session: Session,
    principal: CurrentPrincipal,
    *,
    intent: str,
    target_student_profile_id: UUID | None = None,
) -> GovernedSelection:
    policy = _enabled_policy(session, principal)
    prompt = _enabled_prompt(session, principal, intent=intent)
    model = _eligible_model(session, principal)

    manager = has_any_role(
        session,
        principal,
        COPILOT_MANAGER_ROLES,
    )
    teacher = is_teacher(session, principal)
    teacher_scope = False
    if target_student_profile_id is not None and teacher:
        teacher_scope = teacher_has_student_scope(
            session,
            principal,
            target_student_profile_id,
        )

    max_daily_runs = policy[2] if policy is not None else 1
    max_evidence_items = policy[3] if policy is not None else 0

    facts = GateFacts(
        intent=intent,
        has_use_permission=has_permission(
            session,
            principal,
            "copilot.use",
        ),
        is_manager=manager,
        is_teacher_actor=teacher,
        target_student_profile_id=target_student_profile_id,
        teacher_has_target_scope=teacher_scope,
        policy_enabled=policy is not None,
        prompt_enabled=prompt is not None,
        model_eligible=model is not None,
        daily_run_count=_daily_run_count(session, principal),
        max_daily_runs_per_user=max_daily_runs,
    )
    decision = decide_pre_invocation(facts)

    return GovernedSelection(
        decision=decision,
        policy_key=policy[0] if policy is not None else None,
        policy_version=policy[1] if policy is not None else None,
        prompt_key=prompt[0] if prompt is not None else None,
        prompt_version=prompt[1] if prompt is not None else None,
        output_schema_version=prompt[2] if prompt is not None else None,
        provider_key=model[0] if model is not None else None,
        model_key=model[1] if model is not None else None,
        model_config_version=model[2] if model is not None else None,
        max_evidence_items=max_evidence_items,
    )
