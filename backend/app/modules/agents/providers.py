"""Closed provider adapter contract.  No live transport is enabled in M25-3A."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ProviderFailureCode(StrEnum):
    AUTH = "PROVIDER_AUTH"
    RATE_LIMIT = "PROVIDER_RATE_LIMIT"
    TIMEOUT = "PROVIDER_TIMEOUT"
    UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    INVALID_RESPONSE = "PROVIDER_INVALID_RESPONSE"
    BUDGET_EXCEEDED = "PROVIDER_BUDGET_EXCEEDED"
    POLICY_BLOCK = "PROVIDER_POLICY_BLOCK"
    CONTEXT_TOO_LARGE = "PROVIDER_CONTEXT_TOO_LARGE"
    FALLBACK_EXHAUSTED = "PROVIDER_FALLBACK_EXHAUSTED"


class ProviderGatewayError(RuntimeError):
    def __init__(self, code: ProviderFailureCode) -> None:
        super().__init__(code.value)
        self.code = code


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    prompt_contract_sha256: str
    evidence_manifest_sha256: str
    prompt: dict
    max_output_tokens: int


@dataclass(frozen=True, slots=True)
class ProviderResult:
    payload: dict
    input_tokens: int
    output_tokens: int
    latency_ms: int


class ProviderAdapter(Protocol):
    def invoke(self, request: ProviderRequest) -> ProviderResult: ...


class FakeProvider:
    """Deterministic test double.  It never sends network traffic."""

    def __init__(self, *, outcome: str = "VALID", payload: dict | None = None) -> None:
        self.outcome = outcome
        self.payload = payload or {
            "summary": "Governed evidence summary.",
            "key_findings": [{"text": "The run evidence is available.", "evidence_refs": ["ev_01"]}],
            "caveats": [],
            "evidence_refs": [],
        }
        self.calls = 0

    def invoke(self, request: ProviderRequest) -> ProviderResult:
        self.calls += 1
        outcomes = {
            "TIMEOUT": ProviderFailureCode.TIMEOUT,
            "RATE_LIMIT": ProviderFailureCode.RATE_LIMIT,
            "UNAVAILABLE": ProviderFailureCode.UNAVAILABLE,
            "AUTH": ProviderFailureCode.AUTH,
            "AUTH_ERROR": ProviderFailureCode.AUTH,
            "CONTEXT_TOO_LARGE": ProviderFailureCode.CONTEXT_TOO_LARGE,
        }
        if self.outcome in outcomes:
            raise ProviderGatewayError(outcomes[self.outcome])
        if self.outcome in {"MALFORMED", "MALFORMED_RESPONSE"}:
            return ProviderResult(payload={"not": "the required schema"}, input_tokens=1, output_tokens=1, latency_ms=0)
        if self.outcome == "FABRICATED_CITATION":
            payload = {**self.payload, "evidence_refs": ["ev_99"]}
            return ProviderResult(payload=payload, input_tokens=1, output_tokens=1, latency_ms=0)
        return ProviderResult(payload=self.payload, input_tokens=1, output_tokens=1, latency_ms=0)


class ProviderAdapterRegistry:
    """Code-owned fixed keys; unavailable providers cannot be dispatched."""

    _known_keys = frozenset({"fake", "openai", "anthropic", "local"})

    def __init__(self, *, fake: ProviderAdapter | None = None) -> None:
        self._fake = fake

    def resolve(self, provider_key: str) -> ProviderAdapter:
        if provider_key not in self._known_keys or provider_key != "fake" or self._fake is None:
            raise ProviderGatewayError(ProviderFailureCode.POLICY_BLOCK)
        return self._fake
