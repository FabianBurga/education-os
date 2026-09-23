from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.modules.accountability.identity import (
    IdentityCandidate,
    identity_key_sha256,
    resolve_identity,
)


def _base(**updates):
    value = {
        "organization_id": uuid4(),
        "institution_id": uuid4(),
        "subject_type": "STUDENT",
        "subject_id": uuid4(),
        "source_category": "ATTENDANCE_RISK",
        "episode_anchor": "2026-S1",
    }
    value.update(updates)
    return value


def test_identity_hash_is_deterministic_and_tenant_scoped():
    value = _base()
    identity_value = {key: value[key] for key in (
        "organization_id", "institution_id", "subject_type", "subject_id", "episode_anchor"
    )} | {"normalized_category": "SOURCE:ATTENDANCE_RISK"}
    assert identity_key_sha256(**identity_value) == identity_key_sha256(**identity_value)
    assert identity_key_sha256(**identity_value) != identity_key_sha256(
        **(identity_value | {"institution_id": uuid4()})
    )


def test_identity_distinguishes_active_reopen_related_and_category():
    value = _base()
    active = IdentityCandidate(uuid4(), value["subject_type"], value["subject_id"], "SOURCE:ATTENDANCE_RISK", value["episode_anchor"], "OPEN")
    assert resolve_identity(**value, candidates=(active,)).classification == "SAME_ACTIVE_EPISODE"

    resolved = IdentityCandidate(uuid4(), value["subject_type"], value["subject_id"], "SOURCE:ATTENDANCE_RISK", value["episode_anchor"], "RESOLVED", datetime.now(UTC))
    assert resolve_identity(**value, candidates=(resolved,), reopen_allowed=True).classification == "REOPENED_CASE"
    new_episode = resolve_identity(**(value | {"episode_anchor": "2027-S1"}), candidates=(resolved,))
    assert new_episode.classification == "NEW_RELATED_EPISODE"
    different = resolve_identity(
        **(value | {"source_category": "ACADEMIC_RISK"}), candidates=(active,)
    )
    assert different.classification == "NEW_CATEGORY_CASE"


def test_category_mapping_is_explicit_and_never_falls_back_to_ml():
    value = _base()
    decision = resolve_identity(**value, category_mapping={"ATTENDANCE_RISK": "ATTENDANCE"})
    assert decision.normalized_category == "ATTENDANCE"
    assert resolve_identity(**_base(source_category="opaque"), category_mapping={}).normalized_category == "SOURCE:opaque"


def test_identity_rejects_empty_components():
    with pytest.raises(ValueError):
        value = _base(episode_anchor="")
        identity_key_sha256(
            organization_id=value["organization_id"],
            institution_id=value["institution_id"],
            subject_type=value["subject_type"],
            subject_id=value["subject_id"],
            normalized_category="SOURCE:ATTENDANCE_RISK",
            episode_anchor=value["episode_anchor"],
        )
