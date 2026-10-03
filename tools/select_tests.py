#!/usr/bin/env python3
"""Recommend validation scope from changed paths; never executes tests."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECURITY_OR_SHARED = (
    "alembic/", "migrations/", "security", "auth", "permission", "rls",
    "modules/events/", "modules/interventions/", "accountability",
    "modules/tenancy/", "modules/access/",
)
DOC_ONLY = ("docs/", "agents.md", "readme.md")


def recommend(paths: list[str]) -> tuple[str, str]:
    normalized = [path.replace("\\", "/").lower() for path in paths if path]
    if not normalized:
        return "FULL_REQUIRED", "No changed paths supplied; impact is unknown."
    if any(any(token in path for token in SECURITY_OR_SHARED) for path in normalized):
        return "FULL_REQUIRED", "Migration, authorization, RLS, event, intervention/accountability, or shared security path changed."
    if all(path.startswith(DOC_ONLY) or path.startswith("docs/memory/") or path.startswith("docs/agent_orchestration/") for path in normalized):
        return "FOCUSED", "Documentation-only change: diff check and relevant format/reference validation."
    if all(path.startswith("tools/") or path.startswith("tests/unit/test_development_harness_tools.py") for path in normalized):
        return "FOCUSED", "Development helper change: run helper-specific tests and cheap validation."
    if all(path.startswith("frontend/") for path in normalized):
        if any(path.startswith(("frontend/src/types/", "frontend/src/lib/api")) for path in normalized):
            return "DIRECTED", "Frontend shared API/type surface: focused tests plus typecheck/build and affected consumers."
        return "FOCUSED", "Localized frontend change: focused frontend tests, typecheck and build."
    if all(path.startswith("backend/") for path in normalized):
        if any(path.startswith("backend/app/modules/") for path in normalized):
            return "FULL_REQUIRED", "Backend module/domain source changed; shared authority impact is presumed until A0 documents a narrower impact."
        if any(path.startswith("backend/app/") for path in normalized):
            return "FULL_REQUIRED", "Backend application infrastructure changed; shared impact is presumed."
        return "FOCUSED", "Backend-local tests/config changed without an identified shared boundary."
    if all(path.startswith(("docs/", "tools/", "tests/unit/test_development_harness_tools.py")) for path in normalized):
        return "FOCUSED", "Non-product docs/helper change; run targeted helper validation."
    return "FULL_REQUIRED", "Mixed or unmapped paths; conservative broader validation required."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Changed paths")
    parser.add_argument("--base", help="Instead derive changed paths from BASE...HEAD")
    args = parser.parse_args()
    paths = args.paths
    if args.base:
        commands = (
            ["git", "diff", "--name-only", f"{args.base}...HEAD"],
            ["git", "diff", "--name-only"],
            ["git", "diff", "--cached", "--name-only"],
            ["git", "ls-files", "--others", "--exclude-standard"],
        )
        collected: set[str] = set()
        for command in commands:
            result = subprocess.run(
                command, cwd=ROOT, check=True, capture_output=True, text=True
            )
            collected.update(result.stdout.splitlines())
        paths = sorted(collected)
    level, reason = recommend(paths)
    print(f"RECOMMENDATION: {level}")
    print(f"REASON: {reason}")
    print("AUTOMATIC_TEST_EXECUTION: NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
