from __future__ import annotations

import hashlib
from uuid import UUID

from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.audit.service import record_audit
from app.modules.copilot.evidence import assemble_governed_evidence
from app.modules.copilot.models import CopilotEvidenceRef, CopilotRun
from app.modules.copilot.policy import evaluate_pre_invocation_policy
from app.modules.events.service import enqueue_canonical_event


def request_sha256(request_text: str) -> str:
    return hashlib.sha256(request_text.encode("utf-8")).hexdigest()


def begin_copilot_preflight(
    session: Session,
    principal: CurrentPrincipal,
    *,
    intent: str,
    request_text: str,
    target_student_profile_id: UUID | None = None,
) -> CopilotRun:
    selection = evaluate_pre_invocation_policy(
        session,
        principal,
        intent=intent,
        target_student_profile_id=target_student_profile_id,
    )

    run = CopilotRun(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        intent=intent,
        status="REQUESTED",
        request_sha256=request_sha256(request_text),
        target_student_profile_id=target_student_profile_id,
        policy_key=selection.policy_key,
        policy_version=selection.policy_version,
        prompt_key=selection.prompt_key,
        prompt_version=selection.prompt_version,
        provider_key=selection.provider_key,
        model_key=selection.model_key,
        model_config_version=selection.model_config_version,
        output_schema_version=selection.output_schema_version,
    )
    session.add(run)

    if not selection.decision.allowed:
        run.status = "REFUSED"
        run.failure_code = selection.decision.code
        record_audit(
            session,
            institution_id=principal.institution_id,
            actor_user_id=principal.user_id,
            action="copilot.preflight.refused",
            entity_type="copilot_run",
            entity_id=run.id,
            metadata={
                "intent": intent,
                "failure_code": selection.decision.code,
                "request_sha256": run.request_sha256,
            },
        )
        enqueue_canonical_event(
            session,
            institution_id=principal.institution_id,
            event_type="copilot.run.refused",
            event_version=1,
            aggregate_type="copilot_run",
            aggregate_id=run.id,
            actor_user_id=principal.user_id,
            payload={
                "intent": intent,
                "failure_code": selection.decision.code,
            },
        )
        return run

    # The evidence FORCE RLS policy verifies the parent Copilot run by run_id.
    # Persist the allowed parent first so that check is deterministic and does
    # not depend on ORM flush ordering between unrelated mapped objects.
    session.flush()

    bundle = assemble_governed_evidence(
        session,
        principal,
        intent=intent,
        target_student_profile_id=target_student_profile_id,
    )
    if len(bundle.items) > selection.max_evidence_items:
        run.status = "REFUSED"
        run.failure_code = "EVIDENCE_LIMIT_EXCEEDED"
        return run

    run.evidence_manifest_sha256 = bundle.manifest_sha256
    for item in bundle.items:
        session.add(
            CopilotEvidenceRef(
                organization_id=principal.organization_id,
                institution_id=principal.institution_id,
                run_id=run.id,
                evidence_type=item.evidence_type,
                source_module=item.source_module,
                source_entity_type=item.source_entity_type,
                source_entity_id=item.source_entity_id,
                reference_key=item.reference_key,
                freshness_status=item.freshness_status,
                source_version=item.source_version,
                evidence_sha256=item.evidence_sha256,
                scope_json=item.scope,
                content_json=item.content,
            )
        )

    run.status = "READY"
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="copilot.preflight.ready",
        entity_type="copilot_run",
        entity_id=run.id,
        metadata={
            "intent": intent,
            "evidence_manifest_sha256": bundle.manifest_sha256,
            "evidence_count": len(bundle.items),
            "policy_key": selection.policy_key,
            "policy_version": selection.policy_version,
            "prompt_key": selection.prompt_key,
            "prompt_version": selection.prompt_version,
            "provider_key": selection.provider_key,
            "model_key": selection.model_key,
        },
    )
    return run
