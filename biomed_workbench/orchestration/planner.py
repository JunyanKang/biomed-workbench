"""Constrained, deterministic research-DAG planning over module artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..kernel.artifacts import ScientificArtifact
from ..kernel.identity import digest_value, validate_identifier
from ..kernel.plans import PlanNode, ResearchDAG
from ..kernel.state import ProjectState
from ..modules.contract import ArtifactPort, FormatContract, ModuleManifest
from ..modules.registry import ModuleRegistry
from .graph import CapabilityGraph, producers


class PlanningError(RuntimeError):
    """Raised when no scientifically compatible artifact path can be planned."""


@dataclass(frozen=True)
class PlanningRequest:
    id: str
    output_artifact_type: str
    target_hypothesis_ids: tuple[str, ...]
    required_evidence_types: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "planning_request.id"))
        object.__setattr__(self, "output_artifact_type", validate_identifier(self.output_artifact_type, "planning_request.output_artifact_type"))
        for field in ("target_hypothesis_ids", "required_evidence_types"):
            values = tuple(validate_identifier(value, f"planning_request.{field}") for value in getattr(self, field))
            if len(set(values)) != len(values):
                raise ValueError(f"planning_request.{field} contains duplicates")
            object.__setattr__(self, field, values)


@dataclass(frozen=True)
class _BuiltPath:
    nodes: tuple[PlanNode, ...]
    artifact_id: str
    output_port: ArtifactPort
    producer_node_id: str
    score: tuple[object, ...]


_MATURITY_RANK = {"reference": 0, "validated": 1, "experimental": 2}
_QUALITY_RANK = {"passed": 0, "warning": 1, "unassessed": 2, "major": 3, "fatal": 4}


def _format_matches(artifact: ScientificArtifact, contract: FormatContract) -> bool:
    if artifact.format_version not in contract.versions or artifact.compression not in contract.compression or artifact.orientation not in contract.orientations:
        return False
    if not set(contract.required_indexes) <= set(artifact.indexes):
        return False
    if contract.coordinate_systems and artifact.coordinate_system not in contract.coordinate_systems:
        return False
    if contract.genome_build_policy != "not_applicable" and artifact.genome_build not in contract.genome_builds:
        return False
    if contract.annotation_releases and artifact.annotation_release not in contract.annotation_releases:
        return False
    return True


def _artifact_matches_port(artifact: ScientificArtifact, port: ArtifactPort) -> bool:
    if artifact.artifact_type != port.artifact_type or artifact.quality_status in {"major", "fatal"}:
        return False
    if not any(artifact.format_name == contract.name and _format_matches(artifact, contract) for contract in port.formats):
        return False
    metadata = set(artifact.scientific_scope) | set(artifact.content)
    return set(port.required_metadata) <= metadata


def _ports_compatible(output: ArtifactPort, required_input: ArtifactPort) -> bool:
    if output.artifact_type != required_input.artifact_type:
        return False
    for produced in output.formats:
        for consumed in required_input.formats:
            if produced.name != consumed.name or not set(produced.versions) & set(consumed.versions):
                continue
            if not set(produced.compression) & set(consumed.compression) or not set(produced.orientations) & set(consumed.orientations):
                continue
            if consumed.required_indexes and not set(consumed.required_indexes) <= set(produced.required_indexes):
                continue
            if consumed.coordinate_systems and not set(produced.coordinate_systems) & set(consumed.coordinate_systems):
                continue
            if consumed.genome_build_policy != "not_applicable" and not set(produced.genome_builds) & set(consumed.genome_builds):
                continue
            if consumed.annotation_releases and not set(produced.annotation_releases) & set(consumed.annotation_releases):
                continue
            return True
    return False


def _topological(nodes: tuple[PlanNode, ...]) -> tuple[PlanNode, ...]:
    by_id = {node.id: node for node in nodes}
    remaining = {node.id: set(node.dependencies) for node in nodes}
    ordered = []
    while remaining:
        ready = sorted(node_id for node_id, dependencies in remaining.items() if not dependencies)
        if not ready:
            raise PlanningError("planned module path contains a dependency cycle")
        for node_id in ready:
            ordered.append(by_id[node_id])
            del remaining[node_id]
        for dependencies in remaining.values():
            dependencies.difference_update(ready)
    return tuple(ordered)


def plan_research(
    state: ProjectState,
    registry: ModuleRegistry,
    graph: CapabilityGraph,
    requests: tuple[PlanningRequest, ...],
    *,
    compatible_module_ids: tuple[str, ...] | None = None,
) -> ResearchDAG:
    if not requests or len({request.id for request in requests}) != len(requests):
        raise ValueError("planning requires uniquely identified requests")
    if graph.module_ids != tuple(module.id for module in registry.all()):
        raise ValueError("capability graph and module registry differ")
    hypothesis_ids = {item.id for item in state.hypotheses}
    if any(not set(request.target_hypothesis_ids) <= hypothesis_ids for request in requests):
        raise PlanningError("planning request references an unknown hypothesis")
    compatible = set(compatible_module_ids) if compatible_module_ids is not None else None
    manifests = {manifest.id: manifest for manifest in registry.all()}
    available = tuple(state.artifacts)

    def build(output_type: str, branch_id: str, required_port: ArtifactPort | None, stack: tuple[str, ...]) -> _BuiltPath:
        if output_type in stack:
            raise PlanningError(f"artifact planning cycle detected at {output_type}")
        candidates = []
        for module_id in producers(graph, output_type):
            if compatible is not None and module_id not in compatible:
                continue
            manifest = manifests[module_id]
            for output_port in (port for port in manifest.output_artifacts if port.artifact_type == output_type):
                if required_port is not None and not _ports_compatible(output_port, required_port):
                    continue
                input_bindings = {}
                dependencies = []
                upstream_nodes = []
                warning_risk = 0
                feasible = True
                for input_port in manifest.input_artifacts:
                    matched = sorted(
                        (artifact for artifact in available if _artifact_matches_port(artifact, input_port)),
                        key=lambda artifact: (_QUALITY_RANK[artifact.quality_status], artifact.id),
                    )
                    if matched:
                        selected = matched[0]
                        input_bindings[input_port.name] = selected.id
                        warning_risk += _QUALITY_RANK[selected.quality_status]
                        continue
                    try:
                        upstream = build(input_port.artifact_type, branch_id, input_port, (*stack, output_type))
                    except PlanningError:
                        feasible = False
                        break
                    input_bindings[input_port.name] = upstream.artifact_id
                    dependencies.append(upstream.producer_node_id)
                    upstream_nodes.extend(upstream.nodes)
                if not feasible:
                    continue
                node_seed = {"module_id": module_id, "branch_id": branch_id, "input_bindings": input_bindings}
                node_id = f"node-{module_id}-{digest_value(node_seed)[:10]}"
                planned_outputs = {
                    port.name: f"artifact-planned-{digest_value({'node': node_id, 'port': port.name})[:16]}"
                    for port in manifest.output_artifacts
                }
                node = PlanNode(
                    id=node_id,
                    module_id=module_id,
                    input_bindings=input_bindings,
                    dependencies=tuple(sorted(set(dependencies))),
                    branch_id=branch_id,
                    target_hypothesis_ids=(),
                    expected_evidence_types=(),
                    expected_output_artifact_types=tuple(port.artifact_type for port in manifest.output_artifacts),
                    planned_output_artifact_ids=planned_outputs,
                    compatibility_row_candidates=tuple(row.id for row in manifest.compatibility_matrix),
                    status="pending",
                    attempt=0,
                )
                combined = {item.id: item for item in upstream_nodes}
                combined[node.id] = node
                nodes = _topological(tuple(combined.values()))
                score = (_MATURITY_RANK[manifest.maturity], len(manifest.credentials), warning_risk, len(nodes), module_id)
                candidates.append(_BuiltPath(nodes, planned_outputs[output_port.name], output_port, node.id, score))
        if not candidates:
            raise PlanningError(f"no validated module path can produce artifact type: {output_type}")
        return min(candidates, key=lambda item: item.score)

    all_nodes = {}
    for request in requests:
        branch_id = f"branch-{request.id}"
        built = build(request.output_artifact_type, branch_id, None, ())
        for node in built.nodes:
            existing = all_nodes.get(node.id)
            if existing is not None and existing != node:
                raise PlanningError("deterministic planner produced a node identity collision")
            all_nodes[node.id] = node
        producer = all_nodes[built.producer_node_id]
        all_nodes[built.producer_node_id] = PlanNode(
            **{
                **producer.__dict__,
                "target_hypothesis_ids": tuple(sorted(set(producer.target_hypothesis_ids) | set(request.target_hypothesis_ids))),
                "expected_evidence_types": tuple(sorted(set(producer.expected_evidence_types) | set(request.required_evidence_types))),
            }
        )
    nodes = _topological(tuple(all_nodes.values()))
    has_dependencies = any(node.dependencies for node in nodes)
    root_branches = {node.branch_id for node in nodes if not node.dependencies}
    if len(nodes) == 1:
        plan_type = "single"
    elif has_dependencies and len(root_branches) > 1:
        plan_type = "mixed"
    elif has_dependencies:
        plan_type = "serial"
    else:
        plan_type = "parallel"
    plan_seed = {"state": state.state_digest, "requests": [request.__dict__ for request in requests], "nodes": [node.to_dict() for node in nodes]}
    return ResearchDAG.create(
        id=f"plan-{digest_value(plan_seed)[:20]}",
        objective=state.context.objective,
        nodes=nodes,
        required_output_artifact_types=tuple(sorted({request.output_artifact_type for request in requests})),
        plan_type=plan_type,
        revision=1,
        parent_plan_id=None,
        rationale=(
            "The plan follows validated artifact contracts from available project inputs to requested scientific outputs.",
            "Module ranking prioritizes compatibility, maturity, low credential burden, input quality, and directness.",
        ),
    )
