"""Bounded fake-provider execution for M25-3B; no live adapter is enabled."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256

from pydantic import ValidationError
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.agents.budget import (
    BudgetLimits,
    finalize_budget,
    release_budget,
    reservation_key_for,
    reserve_budget,
)
from app.modules.agents.evidence import EvidencePack, validate_provider_citations
from app.modules.agents.models import AgentProviderCall, AgentRun
from app.modules.agents.prompt_contract import ProviderExplanationOutput
from app.modules.agents.provider_routing import PROVIDER_OPTIONAL_POLICY, RoutingDecision
from app.modules.agents.providers import (
    ProviderAdapterRegistry,
    ProviderFailureCode,
    ProviderGatewayError,
    ProviderRequest,
)


@dataclass(frozen=True, slots=True)
class ProviderExecutionResult:
    output: ProviderExplanationOutput | None
    fallback_used: bool
    failure_code: ProviderFailureCode | None
    provider_call_id: object | None


def _sha(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _validate_output(pack: EvidencePack, payload: dict) -> ProviderExplanationOutput:
    output = ProviderExplanationOutput.model_validate(payload)
    citations = list(output.evidence_refs)
    for finding in output.key_findings:
        citations.extend(finding.evidence_refs)
    validate_provider_citations(pack, citations)
    return output


def _fake_cost_microusd(input_tokens: int, output_tokens: int) -> int:
    """Test-only estimate; `provider_key=fake` makes its non-billing nature explicit."""
    return input_tokens * 10 + output_tokens * 20


def _append_provider_call(
    session: Session,
    principal: CurrentPrincipal,
    *,
    run: AgentRun,
    decision: RoutingDecision,
    pack: EvidencePack,
    prompt_contract_sha256: str,
    request_hash: str,
    response_hash: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    estimated_cost_microusd: int,
    latency_ms: int | None,
    outcome: str,
    error_code: ProviderFailureCode | None,
    attempt_number: int,
) -> AgentProviderCall:
    call = AgentProviderCall(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        agent_run_id=run.id,
        model_registry_id=decision.model_config_id,
        attempt_number=attempt_number,
        provider_key=decision.provider_key,
        model_key=decision.model_key,
        model_version=decision.model_config_version,
        evidence_manifest_sha256=pack.manifest_sha256,
        prompt_contract_sha256=prompt_contract_sha256,
        request_sha256=request_hash,
        response_sha256=response_hash,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_microusd=estimated_cost_microusd,
        latency_ms=latency_ms,
        normalized_outcome=outcome,
        normalized_error_code=error_code.value if error_code else None,
    )
    session.add(call)
    session.flush()
    return call


def execute_fake_provider(
    session: Session,
    principal: CurrentPrincipal,
    *,
    run: AgentRun,
    decision: RoutingDecision,
    provider_policy: str,
    pack: EvidencePack,
    prompt_contract_sha256: str,
    prompt: dict,
    budget_limits: BudgetLimits,
    adapters: ProviderAdapterRegistry,
    deterministic_fallback: Callable[[], ProviderExplanationOutput],
) -> ProviderExecutionResult:
    """Execute only the fake adapter with policy/budget/audit boundaries intact."""
    if provider_policy != PROVIDER_OPTIONAL_POLICY:
        raise ProviderGatewayError(ProviderFailureCode.POLICY_BLOCK)
    reservation_key = reservation_key_for(
        run_id=run.id,
        evidence_manifest_sha256=pack.manifest_sha256,
        model_config_id=decision.model_config_id,
    )
    try:
        reservation = reserve_budget(
            session, principal, run=run, decision=decision,
            limits=budget_limits, reservation_key=reservation_key,
        )
    except ProviderGatewayError as error:
        if error.code == ProviderFailureCode.BUDGET_EXCEEDED:
            return ProviderExecutionResult(deterministic_fallback(), True, error.code, None)
        raise
    request = ProviderRequest(
        prompt_contract_sha256=prompt_contract_sha256,
        evidence_manifest_sha256=pack.manifest_sha256,
        prompt=prompt,
        max_output_tokens=decision.max_output_tokens,
    )
    request_hash = _sha(request.prompt)
    try:
        adapter = adapters.resolve(decision.provider_key)
        result = adapter.invoke(request)
        output = _validate_output(pack, result.payload)
        actual_cost = _fake_cost_microusd(result.input_tokens, result.output_tokens)
        if actual_cost > reservation.amount_microusd:
            raise ProviderGatewayError(ProviderFailureCode.BUDGET_EXCEEDED)
        call = _append_provider_call(
            session, principal, run=run, decision=decision, pack=pack,
            prompt_contract_sha256=prompt_contract_sha256, request_hash=request_hash,
            response_hash=_sha(result.payload), input_tokens=result.input_tokens,
            output_tokens=result.output_tokens, estimated_cost_microusd=actual_cost,
            latency_ms=result.latency_ms, outcome="SUCCEEDED", error_code=None, attempt_number=1,
        )
        finalize_budget(
            session, principal, run=run, decision=decision, reservation=reservation,
            actual_cost_microusd=actual_cost, provider_call_id=call.id,
        )
        return ProviderExecutionResult(output, False, None, call.id)
    except ValidationError:
        error = ProviderGatewayError(ProviderFailureCode.INVALID_RESPONSE)
    except ValueError:
        error = ProviderGatewayError(ProviderFailureCode.INVALID_RESPONSE)
    except ProviderGatewayError as caught:
        error = caught
    call = _append_provider_call(
        session, principal, run=run, decision=decision, pack=pack,
        prompt_contract_sha256=prompt_contract_sha256, request_hash=request_hash,
        response_hash=None, input_tokens=None, output_tokens=None,
        estimated_cost_microusd=0, latency_ms=None, outcome="FAILED",
        error_code=error.code, attempt_number=1,
    )
    release_budget(session, principal, run=run, decision=decision, reservation=reservation)
    return ProviderExecutionResult(deterministic_fallback(), True, error.code, call.id)
