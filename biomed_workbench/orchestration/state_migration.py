"""Non-overwriting migration of map-bound legacy project states."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..kernel.identity import digest_value
from ..kernel.scientific_evidence_map import EvidenceMapPublication
from ..kernel.state import (
    LegacyEvidenceMapRecord,
    ProjectState,
    migrate_v1_project_state_with_verified_maps,
)
from ..reporting.evidence_map_versions import verify_evidence_map_publication_store


def migrate_map_bound_v1_state(
    payload: Mapping[str, Any],
    *,
    evidence_map_root: Path,
) -> ProjectState:
    """Verify every immutable legacy map, then return a blocked v2 successor state."""
    if payload.get("schema_version") != 1:
        raise ValueError("map-bound migration requires a schema v1 project state")
    publications = tuple(
        EvidenceMapPublication.from_dict(item)
        for item in payload.get("evidence_map_versions", ())
    )
    if not publications:
        raise ValueError("map-bound migration requires at least one legacy evidence-map publication")
    records = []
    for publication in publications:
        entry = verify_evidence_map_publication_store(evidence_map_root, publication)
        records.append(
            LegacyEvidenceMapRecord.create(
                publication,
                store_entry_digest=digest_value(entry),
            )
        )
    return migrate_v1_project_state_with_verified_maps(payload, tuple(records))
