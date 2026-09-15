from datetime import date, timedelta

from app.modules.copilot.evidence import (
    canonical_hash,
    freshness_from_snapshot,
)


def test_evidence_hash_is_canonical_for_dict_order():
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash(
        {"b": 2, "a": 1}
    )


def test_snapshot_freshness_is_explicit():
    today = date.today()
    assert freshness_from_snapshot(today) == "CURRENT"
    assert freshness_from_snapshot(today - timedelta(days=1)) == "DELAYED"
    assert freshness_from_snapshot(today - timedelta(days=2)) == "STALE"
