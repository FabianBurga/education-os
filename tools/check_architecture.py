#!/usr/bin/env python3
"""Run small deterministic structural checks; this is not a security review."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

try:  # Script invocation and package import (unit tests) are both supported.
    from .validate_project_memory import validate as validate_memory
except ImportError:  # pragma: no cover - exercised by direct script execution
    from validate_project_memory import validate as validate_memory


REQUIRED_M29_DOCS = (
    "M29_SCOPE.md", "M29_CAPABILITY_INVENTORY.md", "M29_CONTINUITY_MAP.md",
    "M29_DOMAIN_BOUNDARIES.md", "M29_PRIVACY_BOUNDARY.md",
    "M29_EVENT_CONTINUITY.md", "M29_IMPLEMENTATION_PLAN.md",
)
DUPLICATE_AUTHORITY_DIRS = (
    "m29_timeline", "m29_interventions", "m29_accountability", "m29_events",
    "m29_communications", "m29_offline",
)


def migration_graph(directory: Path) -> list[str]:
    errors: list[str] = []
    revisions: dict[str, str | None] = {}
    for path in directory.glob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            errors.append(f"cannot parse migration {path.name}: {exc}")
            continue
        values: dict[str, object] = {}
        for node in tree.body:
            target: ast.expr | None = None
            value: ast.expr | None = None
            if isinstance(node, ast.AnnAssign):
                target, value = node.target, node.value
            elif isinstance(node, ast.Assign) and len(node.targets) == 1:
                target, value = node.targets[0], node.value
            if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"} and value:
                try:
                    values[target.id] = ast.literal_eval(value)
                except (ValueError, TypeError):
                    errors.append(f"non-literal {target.id} in {path.name}")
        revision = values.get("revision")
        down = values.get("down_revision")
        if not isinstance(revision, str):
            continue
        if revision in revisions:
            errors.append(f"duplicate Alembic revision: {revision}")
        if down is not None and not isinstance(down, str):
            errors.append(f"branch/merge migration requires manual review: {path.name}")
        revisions[revision] = down if isinstance(down, str) else None
    referenced = {down for down in revisions.values() if down}
    missing = sorted(referenced - revisions.keys())
    if missing:
        errors.append(f"unknown Alembic down_revision(s): {', '.join(missing)}")
    heads = sorted(set(revisions) - referenced)
    if len(heads) != 1:
        errors.append(f"expected one Alembic head, found {len(heads)}: {heads}")
    elif heads:
        visited: set[str] = set()
        current: str | None = heads[0]
        while current is not None and current in revisions and current not in visited:
            visited.add(current)
            current = revisions[current]
        if current in visited:
            errors.append(f"cycle in Alembic down_revision chain at {current}")
        disconnected = sorted(set(revisions) - visited)
        if disconnected:
            errors.append(f"migration(s) are outside the single head chain: {disconnected}")
    return errors


def check(root: Path) -> list[str]:
    errors = validate_memory(root)
    errors.extend(migration_graph(root / "backend/alembic/versions"))
    docs = root / "docs/m29"
    for name in REQUIRED_M29_DOCS:
        if not (docs / name).is_file():
            errors.append(f"required M29 contract missing: docs/m29/{name}")
    modules = root / "backend/app/modules"
    for name in DUPLICATE_AUTHORITY_DIRS:
        if (modules / name).exists():
            errors.append(f"possible duplicate M29 authority module requires review: {name}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors = check(args.root.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("ARCHITECTURE_CHECK=PASS (structural checks only; A3 review remains required)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
