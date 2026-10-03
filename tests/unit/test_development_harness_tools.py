from pathlib import Path

from tools.build_task_context import build_context, parse_contract
from tools.check_architecture import migration_graph
from tools.select_tests import recommend
from tools.validate_project_memory import validate


ROOT = Path(__file__).resolve().parents[2]


def test_memory_validates_against_current_branch_and_m28_baseline():
    assert validate(ROOT) == []


def test_migration_graph_reports_one_consistent_head():
    assert migration_graph(ROOT / "backend/alembic/versions") == []


def test_migration_graph_rejects_disconnected_cycle(tmp_path):
    (tmp_path / "root.py").write_text('revision = "root"\ndown_revision = None\n')
    (tmp_path / "head.py").write_text('revision = "head"\ndown_revision = "root"\n')
    (tmp_path / "cycle_a.py").write_text('revision = "cycle_a"\ndown_revision = "cycle_b"\n')
    (tmp_path / "cycle_b.py").write_text('revision = "cycle_b"\ndown_revision = "cycle_a"\n')
    errors = migration_graph(tmp_path)
    assert any("outside the single head chain" in error for error in errors)


def test_task_context_is_bounded_to_declared_fields_and_memory_refs():
    contract = """TASK_ID: SAMPLE-1
OWNER: A1
OBJECTIVE: Check one bounded service
MEMORY_REFS:
- docs/memory/AUTHORITY_MAP.md
READ_SCOPE: backend/app/modules/example
WRITE_SCOPE: backend/app/modules/example/service.py
DO_NOT_REDISCOVER: Existing M18 outbox owns canonical events.
"""
    parsed = parse_contract(contract)
    assert parsed["TASK_ID"] == "SAMPLE-1"
    output = build_context(contract, ROOT)
    assert "docs/memory/AUTHORITY_MAP.md" in output
    assert "backend/app/modules/example/service.py" in output
    assert "Candidate missing links" not in output


def test_test_selector_is_conservative_for_shared_security_and_unknown_paths():
    assert recommend(["backend/alembic/versions/new.py"])[0] == "FULL_REQUIRED"
    assert recommend(["backend/app/modules/attendance/service.py"])[0] == "FULL_REQUIRED"
    assert recommend(["unmapped/runtime.py"])[0] == "FULL_REQUIRED"
    assert recommend(["docs/memory/CURRENT_CONTEXT.md"])[0] == "FOCUSED"
    assert recommend(["frontend/src/pages/family.tsx"])[0] == "FOCUSED"
