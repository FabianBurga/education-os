#!/usr/bin/env python3
"""Build a small deterministic task context pack without scanning the repo."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIELDS = (
    "TASK_ID", "OWNER", "OBJECTIVE", "DEPENDENCIES", "MEMORY_REFS",
    "READ_SCOPE", "WRITE_SCOPE", "ROOT_LOCKED_FILES", "MUST_REUSE",
    "MUST_NOT_CREATE", "SECURITY_REQUIREMENTS", "TEST_EXPECTATIONS",
    "EXPECTED_OUTPUT", "STOP_CONDITIONS", "DO_NOT_REDISCOVER",
)


def parse_contract(text: str) -> dict[str, str]:
    result: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("```") or stripped.startswith("#"):
            continue
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            if key in FIELDS:
                current = key
                result.setdefault(key, []).append(value.strip())
                continue
        if current and (stripped.startswith("-") or stripped.startswith("*")):
            result[current].append(stripped)
    return {key: "\n".join(values).strip() for key, values in result.items()}


def build_context(contract_text: str, root: Path) -> str:
    contract = parse_contract(contract_text)
    lines = ["# Bounded task context", ""]
    for key in FIELDS:
        if contract.get(key):
            lines.extend((f"## {key}", contract[key], ""))
    refs = contract.get("MEMORY_REFS", "")
    for ref in refs.split():
        rel = ref.strip("`,;()[]")
        path = root / rel
        if rel.startswith("docs/memory/") and path.is_file():
            lines.extend((f"## Memory reference: {rel}", path.read_text(encoding="utf-8").strip(), ""))
    if not refs:
        lines.extend(("## Memory refs", "Add relevant `docs/memory/` paths to the Task Contract.", ""))
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--contract", type=Path, help="Task Contract file")
    source.add_argument("--task-id", help="Load docs/tasks/<TASK_ID>.md")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.task_id and not re.fullmatch(r"[A-Za-z0-9_.-]+", args.task_id):
        parser.error("TASK_ID may contain only letters, digits, dot, underscore and hyphen")
    path = args.contract.resolve() if args.contract else root / "docs/tasks" / f"{args.task_id}.md"
    try:
        print(build_context(path.read_text(encoding="utf-8"), root), end="")
    except OSError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
