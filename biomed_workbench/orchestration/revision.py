"""Registry-validated preparation of review-triggered plan revisions."""

from __future__ import annotations

from typing import Any, Mapping

from ..kernel.identity import digest_value, thaw
from ..kernel.plans import PlanNode, ResearchDAG, RevisionTargetContract
from ..kernel.state import ProjectState
from ..modules.contract import (
    RevisionAlternative,
    manifest_to_dict,
    module_manifest_digest,
    revision_alternative_to_dict,
)
from ..modules.registry import ModuleRegistry
from ..modules.scientific_command import normalized_scientific_command_parameters
from ..runner import validate_schema_value


def _merge_inputs(state: ProjectState, bindings: Mapping[str, str], overrides: Mapping[str, Any]) -> dict[str, Any]:
    artifacts = {item.id: item for item in state.artifacts}
    merged: dict[str, Any] = {}
    for artifact_id in bindings.values():
        artifact = artifacts.get(artifact_id)
        if artifact is None:
            raise ValueError("revision target input is not a materialized project artifact")
        for key, value in artifact.content.items():
            detached = thaw(value)
            if key in merged and merged[key] != detached:
                raise ValueError(f"revision inputs contain conflicting field: {key}")
            merged[key] = detached
    for key, value in overrides.items():
        merged[str(key)] = thaw(value)
    return merged


def _target_bindings(
    state: ProjectState,
    source: PlanNode,
    target_manifest: object,
    relation: RevisionAlternative,
    explicit_bindings: Mapping[str, str],
) -> dict[str, str]:
    artifacts = {item.id: item for item in state.artifacts}
    target_ports = {port.name: port for port in target_manifest.input_artifacts}
    if set(explicit_bindings) - set(target_ports):
        raise ValueError("revision target input bindings contain an unknown target port")
    if set(explicit_bindings) & set(relation.input_binding_map):
        raise ValueError("revision target input bindings cannot override a frozen source-port mapping")
    bindings: dict[str, str] = {
        target_port: source.input_bindings[source_port]
        for target_port, source_port in relation.input_binding_map.items()
    }
    bindings.update({str(port): str(artifact_id) for port, artifact_id in explicit_bindings.items()})
    for port in target_manifest.input_artifacts:
        artifact_id = bindings.get(port.name)
        artifact = artifacts.get(artifact_id or "")
        if artifact is None:
            raise ValueError(f"revision target input port {port.name} requires one registered artifact binding")
        if artifact.artifact_type != port.artifact_type:
            raise ValueError(f"revision target input port {port.name} has an incompatible artifact type")
    return bindings


def _descendants(plan: ResearchDAG, source_id: str) -> set[str]:
    result: set[str] = set()
    changed = True
    while changed:
        changed = False
        for node in plan.nodes:
            if node.id not in result and any(value == source_id or value in result for value in node.dependencies):
                result.add(node.id)
                changed = True
    return result


def prepare_plan_revision(
    state: ProjectState,
    registry: ModuleRegistry,
    *,
    source_artifact_id: str,
    action: str,
    target_module_id: str | None,
    parameter_overrides: Mapping[str, Any],
    rationale: str,
    target_input_bindings: Mapping[str, str] | None = None,
) -> ResearchDAG:
    """Create one child plan containing a frozen, dormant node-level replacement."""
    if action not in {"rerun-same-method", "rerun-adjusted-parameters", "switch-method"}:
        raise ValueError("plan revision action must rerun or switch method")
    active = next((item for item in state.plans if item.id == state.active_plan_id), None)
    if active is None:
        raise ValueError("plan revision requires one active plan")
    source = next(
        (node for node in active.nodes if source_artifact_id in node.planned_output_artifact_ids.values()),
        None,
    )
    if source is None:
        raise ValueError("plan revision source artifact has no producer in the active plan")
    source_outputs = set(source.planned_output_artifact_ids.values())
    registered_ids = {item.id for item in state.artifacts}
    reviewed_ids = {item.artifact_id for item in state.artifact_reviews}
    decided_ids = {item.artifact_id for item in state.scientific_decisions}
    if source.status != "awaiting_review" or not source_outputs <= registered_ids or not source_outputs <= reviewed_ids:
        raise ValueError("plan revision requires every source-node output to be materialized and reviewed")
    if source_outputs & decided_ids:
        raise ValueError("plan revision must be prepared before any source-node output decision")
    if any(node.revision_of_node_id == source.id for node in active.nodes):
        raise ValueError("source node already has a prepared revision target")

    source_manifest = registry.get(source.module_id)
    selected_module_id = target_module_id or source.module_id
    if action in {"rerun-same-method", "rerun-adjusted-parameters"} and selected_module_id != source.module_id:
        raise ValueError("same-method revision must retain the source module")
    relation = next(
        (
            item for item in source_manifest.revision_alternatives
            if item.target_module_id == selected_module_id
        ),
        None,
    )
    if action == "switch-method" and relation is None:
        raise ValueError("method switch must select a declared revision-compatible alternative")
    target_manifest = registry.get(selected_module_id)
    explicit_bindings = dict(target_input_bindings or {})
    if selected_module_id == source.module_id:
        if explicit_bindings:
            raise ValueError("same-method revision cannot replace input artifact bindings")
        bindings = dict(source.input_bindings)
        output_binding_map = {port.name: port.name for port in source_manifest.output_artifacts}
        relation_payload: dict[str, object] = {
            "kind": "same-method",
            "source_module_id": source.module_id,
        }
    else:
        assert relation is not None
        bindings = _target_bindings(state, source, target_manifest, relation, explicit_bindings)
        output_binding_map = dict(relation.output_binding_map)
        relation_payload = revision_alternative_to_dict(relation)
    overrides = dict(parameter_overrides)
    if action == "rerun-same-method" and overrides:
        raise ValueError("same-method rerun cannot introduce parameter overrides")
    if action == "rerun-adjusted-parameters" and not overrides:
        raise ValueError("adjusted-parameter rerun requires structured parameter overrides")
    merged_inputs = _merge_inputs(state, bindings, overrides)
    validate_schema_value(target_manifest.input_schema, merged_inputs, "revision input")
    if target_manifest.execution.kind == "command":
        command = target_manifest.execution.command
        if command is None:
            raise ValueError("revision target command contract is unavailable")
        request_basis = normalized_scientific_command_parameters(
            command,
            {name: merged_inputs[name] for name in command.parameter_names},
        )
    else:
        request_basis = merged_inputs
    target_request_digest = digest_value(request_basis)
    observed = tuple(item for item in state.observed_executions if item.plan_node_id == source.id)
    if len(observed) != 1:
        raise ValueError("plan revision source lacks one exact observed request")
    source_request_digest = observed[0].parameters_digest
    if action == "rerun-same-method" and target_request_digest != source_request_digest:
        raise ValueError("same-method rerun cannot reconstruct the exact observed request")
    if action == "rerun-adjusted-parameters" and target_request_digest == source_request_digest:
        raise ValueError("adjusted-parameter rerun must change the observed request identity")
    target_output_types = tuple(dict.fromkeys(port.artifact_type for port in target_manifest.output_artifacts))
    if target_output_types != source.expected_output_artifact_types:
        raise ValueError("revision target output types differ from the source scientific contract")

    target_seed = {
        "parent_plan_id": active.id,
        "source_node_id": source.id,
        "action": action,
        "target_module_id": selected_module_id,
        "target_request_digest": target_request_digest,
    }
    target_id = f"node-revision-{digest_value(target_seed)[:20]}"
    target_outputs = {
        port.name: f"artifact-revision-{digest_value({'node': target_id, 'port': port.name})[:20]}"
        for port in target_manifest.output_artifacts
    }
    target_manifest_payload = manifest_to_dict(target_manifest)
    contract = RevisionTargetContract.create(
        id=f"revision-contract-{digest_value(target_seed)[:20]}",
        source_node_id=source.id,
        target_node_id=target_id,
        action=action,
        source_module_id=source.module_id,
        target_module_id=selected_module_id,
        source_manifest_digest=module_manifest_digest(source_manifest),
        target_manifest_digest=module_manifest_digest(target_manifest),
        alternative_relation_digest=digest_value(relation_payload),
        input_contract_digest=digest_value({
            "target_ports": target_manifest_payload["input_artifacts"],
            "bindings": bindings,
        }),
        output_contract_digest=digest_value({
            "source_types": list(source.expected_output_artifact_types),
            "target_ports": target_manifest_payload["output_artifacts"],
            "output_binding_map": output_binding_map,
        }),
        source_request_digest=source_request_digest,
        target_request_digest=target_request_digest,
        rationale=rationale,
    )
    target = PlanNode(
        id=target_id,
        module_id=selected_module_id,
        input_bindings=bindings,
        dependencies=source.dependencies,
        branch_id=source.branch_id,
        target_hypothesis_ids=source.target_hypothesis_ids,
        expected_evidence_types=source.expected_evidence_types,
        expected_output_artifact_types=source.expected_output_artifact_types,
        planned_output_artifact_ids=target_outputs,
        compatibility_row_candidates=tuple(row.id for row in target_manifest.compatibility_matrix),
        status="pending",
        attempt=0,
        planned_request_digest=target_request_digest,
        revision_of_node_id=source.id,
        parameter_overrides=overrides,
        revision_contract=contract,
    )

    descendants = _descendants(active, source.id)
    if any(node.status not in {"pending", "ready"} for node in active.nodes if node.id in descendants):
        raise ValueError("a plan revision cannot rewrite a downstream node that already started")
    node_id_map = {source.id: target.id}
    artifact_id_map = {
        source.planned_output_artifact_ids[source_port]: target_outputs[target_port]
        for source_port, target_port in output_binding_map.items()
    }
    revised_nodes: list[PlanNode] = [node for node in active.nodes if node.id not in descendants]
    revised_nodes.append(target)
    pending_descendants = [node for node in active.nodes if node.id in descendants]
    while pending_descendants:
        node = next(
            (
                candidate
                for candidate in pending_descendants
                if all(
                    dependency not in descendants or dependency in node_id_map
                    for dependency in candidate.dependencies
                )
            ),
            None,
        )
        if node is None:
            raise ValueError("plan revision cannot topologically rebuild its downstream nodes")
        pending_descendants.remove(node)
        bindings_rewritten = {
            port: artifact_id_map.get(artifact_id, artifact_id)
            for port, artifact_id in node.input_bindings.items()
        }
        dependencies_rewritten = tuple(node_id_map.get(value, value) for value in node.dependencies)
        clone_seed = {
            "parent_plan_id": active.id,
            "old_node_id": node.id,
            "bindings": bindings_rewritten,
            "dependencies": dependencies_rewritten,
        }
        clone_id = f"node-replanned-{digest_value(clone_seed)[:20]}"
        clone_outputs = {
            port: f"artifact-replanned-{digest_value({'node': clone_id, 'port': port})[:20]}"
            for port in node.planned_output_artifact_ids
        }
        clone = PlanNode(
            id=clone_id,
            module_id=node.module_id,
            input_bindings=bindings_rewritten,
            dependencies=dependencies_rewritten,
            branch_id=node.branch_id,
            target_hypothesis_ids=node.target_hypothesis_ids,
            expected_evidence_types=node.expected_evidence_types,
            expected_output_artifact_types=node.expected_output_artifact_types,
            planned_output_artifact_ids=clone_outputs,
            compatibility_row_candidates=node.compatibility_row_candidates,
            status="pending",
            attempt=0,
        )
        node_id_map[node.id] = clone.id
        artifact_id_map.update(
            {old: clone_outputs[port] for port, old in node.planned_output_artifact_ids.items()}
        )
        revised_nodes.append(clone)

    plan_seed = {
        "parent_plan_id": active.id,
        "revision_contract_digest": contract.digest,
        "nodes": [node.to_dict() for node in revised_nodes],
    }
    return ResearchDAG.create(
        id=f"plan-revision-{digest_value(plan_seed)[:20]}",
        objective=active.objective,
        nodes=tuple(revised_nodes),
        required_output_artifact_types=active.required_output_artifact_types,
        plan_type=active.plan_type,
        revision=active.revision + 1,
        parent_plan_id=active.id,
        rationale=(*active.rationale, rationale),
    )
