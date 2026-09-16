import hashlib


def integration_idempotency_key(
    *,
    organization_id: str,
    institution_id: str,
    connector_id: str,
    external_source: str,
    source_record_identity: str,
    canonical_entity_type: str,
    operation_class: str,
) -> str:
    """Return a tenant-qualified, deterministic M24 idempotency fingerprint."""
    material = "\x1f".join(
        (
            organization_id,
            institution_id,
            connector_id,
            external_source,
            source_record_identity,
            canonical_entity_type,
            operation_class,
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
