from __future__ import annotations

import inspect
import re

from app.modules.family_portal import service

_UNTYPED_UUID_COMPARISON = re.compile(
    r"(?:\b[A-Za-z_][A-Za-z0-9_]*\.)?(?:id|[A-Za-z_][A-Za-z0-9_]*_id)"
    r"\s*=\s*:[A-Za-z_][A-Za-z0-9_]*_id\b"
)


def test_family_portal_uuid_filters_are_explicitly_typed() -> None:
    source = inspect.getsource(service)

    assert "pa.guardian_profile_id = CAST(:guardian_profile_id AS uuid)" in source
    assert not _UNTYPED_UUID_COMPARISON.search(source)
