"""Non-overwriting migration of map-bound legacy project states."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..kernel.context import ProjectContext
from ..kernel.decisions import DecisionEvent
from ..kernel.identity import digest_value, thaw, validate_identifier
from ..kernel.execution_chain import validate_delivery_prerequisites
from ..kernel.plans import ResearchDAG
from ..kernel.scientific_evidence_map import EvidenceMapPublication
from ..kernel.scientific_dependency import LegacyAnalysisAdmissionRecovery
from ..kernel.state import (
    LegacyEvidenceMapRecord,
    ProjectState,
    StateMigrationContractUpgrade,
    StateMigrationRecord,
    apply_event,
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
    delivery_checks: list[dict[str, str]] = []
    for node_id in delivery_node_ids:
        try:
            validate_delivery_prerequisites(state, node_id)
        except ValueError as error:
            delivery_checks.append({
                "delivery_node_id": node_id,
                "status": "blocked",
                "blocker": str(error),
            })
        else:
            delivery_checks.append({"delivery_node_id": node_id, "status": "satisfied"})
    delivery_status = (
        "not-assessed"
        if not delivery_checks
        else (
            "satisfied"
            if all(item["status"] == "satisfied" for item in delivery_checks)
            else "blocked"
        )
    )
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
        "delivery_prerequisite_assessment_status": delivery_status,
        "delivery_prerequisites_currently_satisfied": (
            None if delivery_status == "not-assessed" else delivery_status == "satisfied"
        ),
        "delivery_prerequisite_checks": delivery_checks,
    }


def migrate_map_bound_v1_state(
    payload: Mapping[str, Any],
    *,
    evidence_map_root: Path,
) -> ProjectState:
    """Verify every immutable legacy map, then return a blocked v2 successor state."""
    if payload.get("schema_version") != 1:
        if any(
            isinstance(item, Mapping) and item.get("contract_version") == "1.1.0"
            for item in payload.get("state_migrations", ())
        ):
            raise ValueError(
                "contract-1.1.0 v2 state requires project upgrade-state-migration-1-1; "
                "migrate-state-v1 cannot rewrite it"
            )
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


_CONTRACT_UPGRADE_REASON = (
    "Recover explicit evidence-map coverage status from the verified immutable map store "
    "without claiming or reconstructing historical scientific admission."
)


def _legacy_v2_state_basis(payload: Mapping[str, Any]) -> dict[str, object]:
    """Reconstruct the exact schema-v2 state basis used by contract 1.1.0."""
    decisions = []
    for raw_event in payload.get("decisions", ()):
        event = dict(raw_event)
        event.pop("resulting_state_digest", None)
        decisions.append(event)
    basis: dict[str, object] = {
        "schema_version": 2,
        "context": payload["context"],
        "artifacts": payload.get("artifacts", []),
        "hypotheses": payload.get("hypotheses", []),
        "evidence": payload.get("evidence", []),
        "decisions": decisions,
        "plans": payload.get("plans", []),
        "active_plan_id": payload.get("active_plan_id"),
        "revision": payload.get("revision"),
    }
    migrations = payload.get("state_migrations", [])
    if migrations:
        basis["state_migrations"] = migrations
    gate_adjudications = payload.get("gate_adjudications", [])
    if gate_adjudications:
        basis["gate_adjudications"] = gate_adjudications
    dependency_fields = (
        "analysis_admissions",
        "artifact_reviews",
        "scientific_decisions",
        "evidence_map_versions",
    )
    if any(payload.get(field, []) for field in dependency_fields):
        basis.update({field: payload.get(field, []) for field in dependency_fields})
    receipt_fields = (
        "execution_handoffs",
        "observed_executions",
        "artifact_reloads",
        "execution_reviews",
    )
    if any(payload.get(field, []) for field in receipt_fields):
        basis.update({field: payload.get(field, []) for field in receipt_fields})
    return basis


def _validate_legacy_contract_1_1_recovery(
    payload: Mapping[str, Any],
    *,
    source_state_digest: str,
    map_digests: set[str],
) -> dict[str, Any]:
    values = dict(payload)
    if values.pop("record_type", None) != "legacy-analysis-admission-recovery":
        raise ValueError("contract 1.1.0 recovery record type is invalid")
    expected = {
        "id", "plan_node_id", "hypothesis_ids", "expected_artifact_types",
        "source_state_digest", "source_map_digest", "rationale_zh", "rationale_en",
        "recovery_status", "evidence_scope", "approved_before_execution", "digest",
    }
    if set(values) != expected:
        raise ValueError("contract 1.1.0 recovery uses an unsupported field set")
    validate_identifier(str(values["id"]), "legacy_contract_1_1_recovery.id")
    validate_identifier(str(values["plan_node_id"]), "legacy_contract_1_1_recovery.plan_node_id")
    if values["source_state_digest"] != source_state_digest:
        raise ValueError("contract 1.1.0 recovery source state differs from its migration")
    if values["source_map_digest"] not in map_digests:
        raise ValueError("contract 1.1.0 recovery source map is not a verified migration map")
    if (
        values["recovery_status"] != "historical-unavailable"
        or values["evidence_scope"] != "project-snapshot-only"
        or values["approved_before_execution"] is not False
    ):
        raise ValueError("contract 1.1.0 recovery overstates historical scientific admission")
    digest = values.pop("digest")
    if digest != digest_value(values):
        raise ValueError("contract 1.1.0 recovery digest is invalid")
    values["digest"] = digest
    return values


def _validate_legacy_contract_1_1_state(
    payload: Mapping[str, Any],
    *,
    evidence_map_root: Path,
) -> tuple[dict[str, Any], tuple[LegacyEvidenceMapRecord, ...], tuple[dict[str, Any], ...]]:
    """Validate the prior state, old record digests, event chain, and immutable maps."""
    expected = {
        "schema_version", "context", "artifacts", "hypotheses", "evidence",
        "gate_adjudications", "analysis_admissions", "artifact_reviews",
        "scientific_decisions", "evidence_map_versions", "execution_handoffs",
        "observed_executions", "artifact_reloads", "execution_reviews",
        "state_migrations", "decisions", "plans", "active_plan_id", "revision",
        "state_digest",
    }
    if payload.get("schema_version") != 2 or frozenset(payload) not in {
        frozenset(expected),
        frozenset(expected - {"gate_adjudications"}),
    }:
        raise ValueError("contract 1.1.0 upgrade requires an exact schema-v2 project state")
    migrations = payload.get("state_migrations")
    if not isinstance(migrations, list) or len(migrations) != 1 or not isinstance(migrations[0], Mapping):
        raise ValueError("contract 1.1.0 upgrade requires exactly one prior migration record")
    migration = dict(migrations[0])
    optional = {"legacy_evidence_maps", "legacy_analysis_admission_recoveries"}
    required = {
        "id", "from_schema_version", "to_schema_version", "source_state_digest",
        "source_revision", "migrated_event_count", "contract_version", "digest",
    }
    if not required <= set(migration) or set(migration) - required - optional:
        raise ValueError("contract 1.1.0 migration record uses an unsupported field set")
    if (
        migration["contract_version"] != "1.1.0"
        or (migration["from_schema_version"], migration["to_schema_version"]) != (1, 2)
        or migration["source_revision"] != migration["migrated_event_count"]
    ):
        raise ValueError("state is not a valid contract 1.1.0 migration")
    validate_identifier(str(migration["id"]), "legacy_contract_1_1_migration.id")
    maps = tuple(
        LegacyEvidenceMapRecord.from_dict(item)
        for item in migration.get("legacy_evidence_maps", ())
    )
    if not maps or tuple(item.publication.version.revision for item in maps) != tuple(range(1, len(maps) + 1)):
        raise ValueError("contract 1.1.0 upgrade requires a continuous verified legacy map history")
    map_digests = {item.publication.map_digest for item in maps}
    recoveries = tuple(
        _validate_legacy_contract_1_1_recovery(
            item,
            source_state_digest=str(migration["source_state_digest"]),
            map_digests=map_digests,
        )
        for item in migration.get("legacy_analysis_admission_recoveries", ())
    )
    if not recoveries or len({item["plan_node_id"] for item in recoveries}) != len(recoveries):
        raise ValueError("contract 1.1.0 upgrade requires unique legacy admission recoveries")
    migration_digest = migration.pop("digest")
    if migration_digest != digest_value(migration):
        raise ValueError("contract 1.1.0 migration digest is invalid")
    migration["digest"] = migration_digest

    for record in maps:
        entry = verify_evidence_map_publication_store(evidence_map_root, record.publication)
        if digest_value(entry) != record.store_entry_digest:
            raise ValueError("contract 1.1.0 legacy map store entry digest is invalid")

    if payload["state_digest"] != digest_value(_legacy_v2_state_basis(payload)):
        raise ValueError("contract 1.1.0 project state digest is invalid")
    initial_basis = {
        "schema_version": 2,
        "context": payload["context"],
        "artifacts": [], "hypotheses": [], "evidence": [], "decisions": [],
        "plans": [], "active_plan_id": None, "revision": 0,
        "state_migrations": payload["state_migrations"],
    }
    expected_prior = digest_value(initial_basis)
    decisions = payload.get("decisions", [])
    if not isinstance(decisions, list) or payload.get("revision") != len(decisions):
        raise ValueError("contract 1.1.0 project event count is inconsistent")
    for sequence, raw_event in enumerate(decisions, start=1):
        event = DecisionEvent.from_dict(raw_event)
        if event.sequence != sequence or event.prior_state_digest != expected_prior:
            raise ValueError("contract 1.1.0 project event chain is broken")
        identity_basis = {
            "sequence": sequence,
            "event_type": event.event_type,
            "payload": thaw(event.payload),
            "prior_state_digest": expected_prior,
        }
        if event.id != f"event-{sequence:06d}-{digest_value(identity_basis)[:12]}":
            raise ValueError("contract 1.1.0 project event identity is invalid")
        expected_prior = event.resulting_state_digest
    if expected_prior != payload["state_digest"]:
        raise ValueError("contract 1.1.0 event chain does not terminate at its project state digest")
    return migration, maps, recoveries


def upgrade_state_migration_contract_1_1(
    payload: Mapping[str, Any],
    *,
    evidence_map_root: Path,
) -> ProjectState:
    """Create a distinct contract-1.2.0 successor after validating a 1.1.0 state."""
    prior_migration, records, old_recoveries = _validate_legacy_contract_1_1_state(
        payload,
        evidence_map_root=evidence_map_root,
    )
    maps_by_digest = {item.publication.map_digest: item.publication for item in records}
    recoveries = []
    plan_nodes = {
        node.id: node
        for plan_payload in payload.get("plans", ())
        for node in ResearchDAG.from_dict(plan_payload).nodes
    }
    for old in old_recoveries:
        node = plan_nodes.get(str(old["plan_node_id"]))
        if node is None:
            raise ValueError("contract 1.1.0 recovery references an unknown migrated plan node")
        if (
            tuple(old["hypothesis_ids"]) != node.target_hypothesis_ids
            or tuple(old["expected_artifact_types"]) != node.expected_output_artifact_types
        ):
            raise ValueError("contract 1.1.0 recovery differs from its migrated plan-node contract")
        publication = maps_by_digest[str(old["source_map_digest"])]
        recoveries.append(
            LegacyAnalysisAdmissionRecovery.create(
                plan_node_id=node.id,
                hypothesis_ids=node.target_hypothesis_ids,
                expected_artifact_types=node.expected_output_artifact_types,
                source_state_digest=str(old["source_state_digest"]),
                source_map_digest=publication.map_digest,
                source_map_coverage_status=(
                    "covered" if node.id in publication.covered_node_ids else "not-covered"
                ),
            )
        )
    upgrade = StateMigrationContractUpgrade.create(
        source_migration_digest=str(prior_migration["digest"]),
        source_project_state_digest=str(payload["state_digest"]),
        reason=_CONTRACT_UPGRADE_REASON,
    )
    migration = StateMigrationRecord.create(
        source_state_digest=str(prior_migration["source_state_digest"]),
        source_revision=int(prior_migration["source_revision"]),
        legacy_evidence_maps=records,
        legacy_analysis_admission_recoveries=tuple(recoveries),
        contract_upgrade=upgrade,
    )
    state = ProjectState.create(
        ProjectContext.from_dict(payload["context"]),
        state_migrations=(migration,),
    )
    for raw_event in payload.get("decisions", ()):
        event = DecisionEvent.from_dict(raw_event)
        state = apply_event(
            state,
            event.event_type,
            thaw(event.payload),
            rationale=event.rationale,
            trigger_finding_ids=event.trigger_finding_ids,
            affected_artifact_ids=event.affected_artifact_ids,
            affected_hypothesis_ids=event.affected_hypothesis_ids,
            superseded_action_ids=event.superseded_action_ids,
            replacement_action_ids=event.replacement_action_ids,
            prior_results_valid=event.prior_results_valid,
        )
    actual = state.to_dict()
    for field in (
        "context", "artifacts", "hypotheses", "evidence", "gate_adjudications",
        "analysis_admissions", "artifact_reviews", "scientific_decisions",
        "evidence_map_versions", "execution_handoffs", "observed_executions",
        "artifact_reloads", "execution_reviews", "plans", "active_plan_id", "revision",
    ):
        if actual.get(field, []) != payload.get(field, []):
            raise ValueError(f"contract 1.1.0 replay differs from serialized state field: {field}")
    if ProjectState.from_dict(state.to_dict()) != state:
        raise ValueError("contract 1.2.0 successor does not round-trip through current state validation")
    return state
