from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.observability.configuration import production_runtime_errors  # noqa: E402


def production_migration_errors(
    values: Mapping[str, object],
) -> list[str]:
    if str(values.get("APP_ENV", "")).lower() != "production":
        return []

    errors: list[str] = []
    owner_url = str(values.get("OWNER_DATABASE_URL", "") or "")
    if not owner_url.startswith("postgresql"):
        errors.append("OWNER_DATABASE_URL is required for production migrations")
    if "_dev" in owner_url:
        errors.append(
            "OWNER_DATABASE_URL must not use development credentials"
        )

    runtime_url = str(values.get("DATABASE_URL", "") or "")
    if owner_url and runtime_url and owner_url == runtime_url:
        errors.append(
            "Runtime and migration database credentials must be separated"
        )
    return errors


def _ci_contract() -> None:
    valid_runtime = {
        "APP_ENV": "production",
        "SECRET_KEY": "m17-production-contract-secret-0123456789",
        "DATABASE_URL": (
            "postgresql+psycopg://education_app:"
            "runtime-secret@db.internal:5432/education_os"
        ),
        "PUBLIC_BASE_URL": "https://education.example.org",
        "FRONTEND_REQUIRED_FOR_READINESS": True,
        "OWNER_DATABASE_URL": None,
    }
    assert production_runtime_errors(valid_runtime) == []

    bad_runtime = dict(valid_runtime)
    bad_runtime["SECRET_KEY"] = "change-me"
    bad_runtime["DATABASE_URL"] = (
        "postgresql+psycopg://education_owner:"
        "education_owner_dev@db:5432/education_os"
    )
    bad_runtime["PUBLIC_BASE_URL"] = "http://education.example.org"
    bad_runtime["FRONTEND_REQUIRED_FOR_READINESS"] = False
    bad_runtime["OWNER_DATABASE_URL"] = (
        "postgresql+psycopg://education_owner:owner@db:5432/education_os"
    )
    assert len(production_runtime_errors(bad_runtime)) >= 5

    valid_migration = {
        "APP_ENV": "production",
        "DATABASE_URL": (
            "postgresql+psycopg://education_app:"
            "runtime-secret@db.internal:5432/education_os"
        ),
        "OWNER_DATABASE_URL": (
            "postgresql+psycopg://education_owner:"
            "migration-secret@db.internal:5432/education_os"
        ),
    }
    assert production_migration_errors(valid_migration) == []

    bad_migration = dict(valid_migration)
    bad_migration["OWNER_DATABASE_URL"] = (
        "postgresql+psycopg://education_owner:"
        "education_owner_dev@db.internal:5432/education_os"
    )
    assert production_migration_errors(bad_migration)

    print("M17 production environment validation contract: PASSED")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ci-contract",
        action="store_true",
        help="Validate M17 production-safety rules with synthetic values.",
    )
    parser.add_argument(
        "--runtime",
        action="store_true",
        help="Validate the current environment as a production runtime.",
    )
    parser.add_argument(
        "--migration",
        action="store_true",
        help="Validate the current environment for production migrations.",
    )
    args = parser.parse_args()

    if args.ci_contract:
        _ci_contract()
        return

    values = dict(os.environ)
    errors: list[str] = []
    if args.runtime:
        if str(values.get("APP_ENV", "")).lower() != "production":
            errors.append("APP_ENV must be production for runtime validation")
        errors.extend(production_runtime_errors(values))
    if args.migration:
        if str(values.get("APP_ENV", "")).lower() != "production":
            errors.append("APP_ENV must be production for migration validation")
        errors.extend(production_migration_errors(values))
    if not args.runtime and not args.migration:
        parser.error("choose --ci-contract, --runtime, or --migration")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(2)

    print("M17 production environment validation: PASSED")


if __name__ == "__main__":
    main()
