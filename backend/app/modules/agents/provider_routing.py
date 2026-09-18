"""Tenant-scoped deterministic provider/model routing for M25-3B."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.agents.models import AgentModelRegistry
from app.modules.agents.providers import ProviderFailureCode, ProviderGatewayError

PROVIDER_OPTIONAL_POLICY = "PROVIDER_OPTIONAL_WITH_DETERMINISTIC_FALLBACK"


@dataclass(frozen=True, slots=True)
class RoutingRequirements:
    capability_class: str
    required_input_tokens: int
    required_output_tokens: int
    per_run_cost_limit_microusd: int


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    organization_id: UUID
    institution_id: UUID
    model_config_id: UUID
    provider_key: str
    model_key: str
    model_config_version: int
    capability_class: str
    routing_priority: int
    context_limit: int
    max_input_tokens: int
    max_output_tokens: int
    max_estimated_cost_microusd: int
    timeout_seconds: int
    max_attempts: int
    max_fallbacks: int


def load_enabled_model_configs(
    session: Session,
    principal: CurrentPrincipal,
    *,
    capability_class: str,
) -> list[AgentModelRegistry]:
    """Read only tenant-scoped rows; no caller may supply tenant identity."""
    return list(
        session.exec(
            select(AgentModelRegistry)
            .where(
                AgentModelRegistry.organization_id == principal.organization_id,
                AgentModelRegistry.institution_id == principal.institution_id,
                AgentModelRegistry.status == "ENABLED",
                AgentModelRegistry.capability_class == capability_class,
            )
            .order_by(
                AgentModelRegistry.routing_priority,
                AgentModelRegistry.provider_key,
                AgentModelRegistry.model_key,
                AgentModelRegistry.version.desc(),
            )
        ).all()
    )


def _eligible(row: AgentModelRegistry, requirements: RoutingRequirements) -> bool:
    return (
        row.max_input_tokens >= requirements.required_input_tokens
        and row.max_output_tokens >= requirements.required_output_tokens
        and row.context_limit >= requirements.required_input_tokens + requirements.required_output_tokens
        and row.max_estimated_cost_microusd <= requirements.per_run_cost_limit_microusd
    )


def select_deterministic_route(
    *,
    principal: CurrentPrincipal,
    provider_policy: str,
    requirements: RoutingRequirements,
    candidates: list[AgentModelRegistry],
) -> RoutingDecision:
    """Select the first policy-compliant configuration in stable order."""
    if provider_policy != PROVIDER_OPTIONAL_POLICY:
        raise ProviderGatewayError(ProviderFailureCode.POLICY_BLOCK)
    for row in candidates:
        if (
            row.organization_id != principal.organization_id
            or row.institution_id != principal.institution_id
            or row.status != "ENABLED"
            or row.capability_class != requirements.capability_class
            or not _eligible(row, requirements)
        ):
            continue
        return RoutingDecision(
            organization_id=principal.organization_id,
            institution_id=principal.institution_id,
            model_config_id=row.id,
            provider_key=row.provider_key,
            model_key=row.model_key,
            model_config_version=row.version,
            capability_class=row.capability_class,
            routing_priority=row.routing_priority,
            context_limit=row.context_limit,
            max_input_tokens=row.max_input_tokens,
            max_output_tokens=row.max_output_tokens,
            max_estimated_cost_microusd=row.max_estimated_cost_microusd,
            timeout_seconds=row.timeout_seconds,
            max_attempts=row.max_attempts,
            max_fallbacks=row.max_fallbacks,
        )
    raise ProviderGatewayError(ProviderFailureCode.POLICY_BLOCK)


def route_provider_model(
    session: Session,
    principal: CurrentPrincipal,
    *,
    provider_policy: str,
    requirements: RoutingRequirements,
) -> RoutingDecision:
    return select_deterministic_route(
        principal=principal,
        provider_policy=provider_policy,
        requirements=requirements,
        candidates=load_enabled_model_configs(
            session, principal, capability_class=requirements.capability_class,
        ),
    )
