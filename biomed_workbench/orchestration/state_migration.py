"""Non-overwriting migration of map-bound legacy project states."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..kernel.identity import digest_value
from ..kernel.execution_chain import validate_delivery_prerequisites
from ..kernel.scientific_evidence_map import EvidenceMapPublication
from ..kernel.state import (
    LegacyEvidenceMapRecord,
    ProjectState,
    migrate_v1_project_state_with_verified_maps,
)
from ..reporting.evidence_map_versions import verify_evidence_map_publication_store


def assess_republication_prerequisites(
    state: ProjectState,
    *,
    delivery_node_ids: tuple[str, ...] = (),
) -> dict[str, object]:
    """Report exact recovery work before a migrated state can publish a new snapshot."""
    plan_node_ids = {node.id for plan in state.plans for node in plan.nodes}
    admitted_node_ids = {item.plan_node_id for item in state.analysis_admissions}
    recovered_node_ids = {
        recovery.plan_node_id
        for migration in state.state_migrations
        for recovery in migration.legacy_analysis_admission_recoveries
    }
    artifact_ids = {item.id for item in state.artifacts}
    reviewed_artifact_ids = {item.artifact_id for item in state.artifact_reviews}
    decided_artifact_ids = {item.artifact_id for item in state.scientific_decisions}
    legacy_maps = tuple(
        record
        for migration in state.state_migrations
        for record in migration.legacy_evidence_maps
    )
    missing_admissions = tuple(sorted(plan_node_ids - admitted_node_ids - recovered_node_ids))
    missing_reviews = tuple(sorted(artifact_ids - reviewed_artifact_ids))
    missing_decisions = tuple(sorted(artifact_ids - decided_artifact_ids))
    unresolved_gates = tuple(sorted(
        item.id for item in state.gate_adjudications if item.status == "unresolved"
    ))
    blockers = bool(missing_admissions or missing_reviews or missing_decisions)
    delivery_checks = []
    for node_id in delivery_node_ids:
        try:
            validate_delivery_prerequisites(state, node_id)
        except ValueError:
            delivery_checks.append(False)
        else:
            delivery_checks.append(True)
    return {
        "migration_status": (
            "awaiting-scientific-dependency-recovery"
            if blockers
            else "ready-for-evidence-map-republication"
        ),
        "missing_analysis_admission_node_ids": list(missing_admissions),
        "legacy_admission_recovery_node_ids": sorted(recovered_node_ids),
        "missing_artifact_review_ids": list(missing_reviews),
        "missing_scientific_decision_artifact_ids": list(missing_decisions),
        "unresolved_gate_ids": list(unresolved_gates),
        "required_next_map_revision": len(legacy_maps) + len(state.evidence_map_versions) + 1,
        "required_parent_map_digest": (
            state.evidence_map_versions[-1].map_digest
            if state.evidence_map_versions
            else (legacy_maps[-1].publication.map_digest if legacy_maps else None)
        ),
        "delivery_permanently_blocked_by_legacy_recovery": bool(recovered_node_ids),
        "delivery_prerequisites_currently_satisfied": bool(delivery_checks) and all(delivery_checks),
    }


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
