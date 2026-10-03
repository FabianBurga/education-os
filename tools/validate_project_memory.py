#!/usr/bin/env python3
"""Validate compact project memory against required files and local Git."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


REQUIRED_FILES = (
    "docs/memory/PROJECT_STATE.json",
    "docs/memory/CURRENT_CONTEXT.md",
    "docs/memory/AUTHORITY_MAP.md",
    "docs/memory/DECISION_INDEX.md",
    "docs/memory/VALIDATION_BASELINE.md",
    "docs/memory/MEMORY_CHANGELOG.md",
)
REQUIRED_AUTHORITIES = tuple(f"M{i}" for i in range(17, 29))


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    state_path = root / REQUIRED_FILES[0]
    missing = [path for path in REQUIRED_FILES if not (root / path).is_file()]
    errors.extend(f"required memory file missing: {path}" for path in missing)
    if not state_path.is_file():
        return errors
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"PROJECT_STATE invalid: {exc}"]

    for key in ("memory_version", "project", "canonical_branch", "baseline_release", "current", "database", "orchestration", "memory_anchor_commit"):
        if key not in state:
            errors.append(f"PROJECT_STATE missing key: {key}")
    for group, keys in {
        "baseline_release": ("milestone", "tag", "commit"),
        "current": ("milestone", "stage", "status"),
        "database": ("migration_head",),
        "orchestration": ("mode", "root_agent", "max_concurrent_subagents"),
    }.items():
        value = state.get(group)
        if not isinstance(value, dict):
            errors.append(f"PROJECT_STATE.{group} must be an object")
            continue
        for key in keys:
            if not value.get(key):
                errors.append(f"PROJECT_STATE.{group}.{key} is required")

    try:
        branch = _git(root, "branch", "--show-current")
        if branch != state.get("canonical_branch"):
            errors.append(
                f"branch mismatch: expected {state.get('canonical_branch')}, found {branch}"
            )
        anchor = state.get("memory_anchor_commit", "")
        _git(root, "cat-file", "-e", f"{anchor}^{{commit}}")
        head = _git(root, "rev-parse", "HEAD")
        _git(root, "merge-base", "--is-ancestor", anchor, head)
        release = state.get("baseline_release", {})
        peeled = _git(root, "rev-parse", f"{release.get('tag')}^{{commit}}")
        if peeled != release.get("commit"):
            errors.append("baseline tag peeled commit does not match PROJECT_STATE")
    except (subprocess.CalledProcessError, OSError) as exc:
        errors.append(f"Git memory check failed: {exc}")

    authority_path = root / "docs/memory/AUTHORITY_MAP.md"
    if authority_path.is_file():
        authority_text = authority_path.read_text(encoding="utf-8")
        for authority in REQUIRED_AUTHORITIES:
            if not re.search(rf"\b{authority}\b", authority_text):
                errors.append(f"authority map missing {authority}")

    for relative in REQUIRED_FILES[1:]:
        path = root / relative
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)#]+\.md)\)", content):
            if not (path.parent / target).is_file():
                errors.append(f"broken memory reference in {relative}: {target}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors = validate(args.root.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("PROJECT_MEMORY=VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
