from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


class ProviderGatewayError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    model_key: str
    instructions: str
    input_text: str
    output_schema: dict[str, object]
    max_output_tokens: int


@dataclass(frozen=True, slots=True)
class ProviderResult:
    response_id: str | None
    payload: dict[str, object]
    input_tokens: int
    output_tokens: int
    total_tokens: int
    provider_status: str


class AdvisoryProvider(Protocol):
    def invoke(self, request: ProviderRequest) -> ProviderResult: ...


class OpenAIResponsesProvider:
    endpoint = "https://api.openai.com/v1/responses"

    def __init__(
        self,
        *,
        api_key_env: str = "OPENAI_API_KEY",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds

    def build_payload(self, request: ProviderRequest) -> dict[str, object]:
        return {
            "model": request.model_key,
            "instructions": request.instructions,
            "input": request.input_text,
            "store": False,
            "truncation": "disabled",
            "max_output_tokens": request.max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "education_os_advisory_answer",
                    "strict": True,
                    "schema": request.output_schema,
                }
            },
        }

    @staticmethod
    def _extract_output_text(data: dict[str, object]) -> str:
        output = data.get("output")
        if not isinstance(output, list):
            raise ProviderGatewayError(
                "PROVIDER_MALFORMED_RESPONSE",
                "Provider response does not contain output items.",
            )

        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "refusal":
                    raise ProviderGatewayError(
                        "PROVIDER_REFUSAL",
                        "Provider refused the governed advisory request.",
                    )
                if part.get("type") == "output_text":
                    value = part.get("text")
                    if isinstance(value, str) and value:
                        return value

        raise ProviderGatewayError(
            "PROVIDER_MALFORMED_RESPONSE",
            "Provider response does not contain structured output text.",
        )

    def invoke(self, request: ProviderRequest) -> ProviderResult:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise ProviderGatewayError(
                "PROVIDER_CREDENTIAL_MISSING",
                f"Environment variable {self.api_key_env} is not configured.",
            )

        body = json.dumps(
            self.build_payload(request),
            separators=(",", ":"),
        ).encode("utf-8")
        http_request = urllib.request.Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(
                http_request,
                timeout=self.timeout_seconds,
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise ProviderGatewayError(
                f"PROVIDER_HTTP_{exc.code}",
                "Provider returned an HTTP error.",
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ProviderGatewayError(
                "PROVIDER_UNAVAILABLE",
                "Provider is unavailable or timed out.",
            ) from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderGatewayError(
                "PROVIDER_MALFORMED_RESPONSE",
                "Provider returned invalid JSON.",
            ) from exc

        if not isinstance(data, dict):
            raise ProviderGatewayError(
                "PROVIDER_MALFORMED_RESPONSE",
                "Provider returned an unexpected response shape.",
            )

        status = str(data.get("status") or "unknown")
        if status != "completed":
            raise ProviderGatewayError(
                f"PROVIDER_STATUS_{status.upper()}",
                f"Provider response status is {status}.",
            )

        text_output = self._extract_output_text(data)
        try:
            payload = json.loads(text_output)
        except json.JSONDecodeError as exc:
            raise ProviderGatewayError(
                "PROVIDER_SCHEMA_DECODE_FAILED",
                "Structured provider output is not valid JSON.",
            ) from exc

        if not isinstance(payload, dict):
            raise ProviderGatewayError(
                "PROVIDER_SCHEMA_DECODE_FAILED",
                "Structured provider output must be an object.",
            )

        usage = data.get("usage")
        if not isinstance(usage, dict):
            usage = {}

        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        total_tokens = int(
            usage.get("total_tokens") or input_tokens + output_tokens
        )

        response_id = data.get("id")
        return ProviderResult(
            response_id=str(response_id) if response_id else None,
            payload=payload,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            provider_status=status,
        )


class ProviderGateway:
    def __init__(
        self,
        providers: dict[str, AdvisoryProvider] | None = None,
    ) -> None:
        self._providers = providers or {
            "openai": OpenAIResponsesProvider(),
        }

    def invoke(
        self,
        provider_key: str,
        request: ProviderRequest,
    ) -> ProviderResult:
        provider = self._providers.get(provider_key)
        if provider is None:
            raise ProviderGatewayError(
                "PROVIDER_NOT_SUPPORTED",
                f"Provider {provider_key!r} is not supported.",
            )
        return provider.invoke(request)
