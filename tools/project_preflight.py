#!/usr/bin/env python3
"""Print a compact, read-only repository and project-memory preflight."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "docs/memory/PROJECT_STATE.json"


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def main() -> int:
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        branch = git("branch", "--show-current")
        head = git("rev-parse", "HEAD")
        dirty = bool(git("status", "--porcelain=v1", "--untracked-files=all"))
        anchor = state["memory_anchor_commit"]
        current = state["current"]
        database = state["database"]
        baseline = state["baseline_release"]
        print(f"project: {state['project']}")
        print(f"branch: {branch}")
        print(f"HEAD: {head}")
        print(f"working_tree: {'DIRTY' if dirty else 'CLEAN'}")
        print(f"memory_anchor: {anchor}")
        print(f"memory_status: {'FRESH' if head == anchor else 'STALE'}")
        print(f"current_milestone: {current['milestone']}")
        print(f"current_stage: {current['stage']}")
        print(f"known_migration_head: {database['migration_head']}")
        print(f"last_validation: {state['last_validation_baseline']}")
        print(f"baseline_release: {baseline['tag']} @ {baseline['commit']}")
        print(f"next_step: {state['next_expected_step']}")
        return 0
    except (OSError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"preflight error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
