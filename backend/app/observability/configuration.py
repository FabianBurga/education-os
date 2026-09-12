from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings

_INSECURE_SECRETS = {
    "",
    "change-me",
    "change-me-in-real-environments",
    "ci-only-secret",
    "test-secret",
}


def production_runtime_errors(
    values: Settings | Mapping[str, object],
) -> list[str]:
    def get(name: str, default: object = None) -> object:
        if isinstance(values, Mapping):
            return values.get(name, default)
        return getattr(values, name, default)

    if str(get("APP_ENV", "")).lower() != "production":
        return []

    errors: list[str] = []

    secret = str(get("SECRET_KEY", "") or "")
    if secret in _INSECURE_SECRETS or len(secret) < 32:
        errors.append(
            "SECRET_KEY must be a non-default secret with at least 32 characters"
        )

    database_url = str(get("DATABASE_URL", "") or "")
    if not database_url.startswith("postgresql"):
        errors.append("DATABASE_URL must use PostgreSQL in production")
    if "education_owner" in database_url:
        errors.append(
            "DATABASE_URL must use the restricted runtime role, not education_owner"
        )
    if "_dev" in database_url:
        errors.append("DATABASE_URL must not use development credentials")

    public_base_url = str(get("PUBLIC_BASE_URL", "") or "")
    if not public_base_url.startswith("https://"):
        errors.append("PUBLIC_BASE_URL must use HTTPS in production")

    if not bool(get("FRONTEND_REQUIRED_FOR_READINESS", False)):
        errors.append(
            "FRONTEND_REQUIRED_FOR_READINESS must be true in production"
        )

    owner_url = get("OWNER_DATABASE_URL")
    if owner_url:
        errors.append(
            "OWNER_DATABASE_URL must not be injected into the runtime application process"
        )

    return errors


def assert_production_runtime_configuration(settings: Settings) -> None:
    errors = production_runtime_errors(settings)
    if errors:
        detail = "; ".join(errors)
        raise RuntimeError(f"Unsafe production runtime configuration: {detail}")
