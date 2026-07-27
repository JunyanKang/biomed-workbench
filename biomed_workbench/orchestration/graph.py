"""Deterministic capability graph derived entirely from module manifests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..kernel.identity import digest_value, freeze_mapping, thaw
from ..modules.registry import ModuleRegistry


RELATION_TYPES = (
    "consumes",
    "produces",
    "validates",
    "alternative-to",
    "complements",
    "addresses-intent",
    "addresses-question",
)
NODE_KINDS = frozenset({"module", "artifact", "intent", "question"})


@dataclass(frozen=True)
class GraphNode:
    id: str
    kind: str
    label: str
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id or self.kind not in NODE_KINDS or not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("graph node identity, kind, or label is invalid")
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "kind": self.kind, "label": self.label, "metadata": thaw(self.metadata)}


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    relation: str
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.source or not self.target or self.source == self.target or self.relation not in RELATION_TYPES:
            raise ValueError("graph edge is invalid")
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, object]:
        return {"source": self.source, "target": self.target, "relation": self.relation, "metadata": thaw(self.metadata)}


def _graph_basis(nodes: tuple[GraphNode, ...], edges: tuple[GraphEdge, ...], module_ids: tuple[str, ...], artifact_types: tuple[str, ...]) -> dict[str, object]:
    return {
        "nodes": [node.to_dict() for node in nodes],
        "edges": [edge.to_dict() for edge in edges],
        "module_ids": list(module_ids),
        "artifact_types": list(artifact_types),
        "relation_types": list(RELATION_TYPES),
    }


@dataclass(frozen=True)
class CapabilityGraph:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    module_ids: tuple[str, ...]
    artifact_types: tuple[str, ...]
    relation_types: tuple[str, ...]
    digest: str

    def __post_init__(self) -> None:
        if self.relation_types != RELATION_TYPES:
            raise ValueError("capability graph relation contract is invalid")
        if self.nodes != tuple(sorted(self.nodes, key=lambda item: item.id)):
            raise ValueError("capability graph nodes must be deterministically ordered")
        edge_key = lambda item: (item.source, item.target, item.relation, digest_value(item.metadata))
        if self.edges != tuple(sorted(self.edges, key=edge_key)):
            raise ValueError("capability graph edges must be deterministically ordered")
        node_ids = {node.id for node in self.nodes}
        if len(node_ids) != len(self.nodes) or any(edge.source not in node_ids or edge.target not in node_ids for edge in self.edges):
            raise ValueError("capability graph contains duplicate or unknown nodes")
        if self.module_ids != tuple(sorted(set(self.module_ids))) or self.artifact_types != tuple(sorted(set(self.artifact_types))):
            raise ValueError("capability graph indexes must be unique and sorted")
        if self.digest != digest_value(_graph_basis(self.nodes, self.edges, self.module_ids, self.artifact_types)):
            raise ValueError("capability graph digest does not match canonical graph")


def _module_node(module_id: str) -> str:
    return f"module_{module_id}"


def _artifact_node(artifact_type: str) -> str:
    return f"artifact_{artifact_type}"


def _semantic_node(kind: str, text: str) -> str:
    return f"{kind}_{digest_value({'text': text})[:16]}"


def build_capability_graph(registry: ModuleRegistry) -> CapabilityGraph:
    nodes: dict[str, GraphNode] = {}
    edge_values: dict[tuple[str, str, str, str], GraphEdge] = {}
    artifact_types = set()

    def add_node(node: GraphNode) -> None:
        existing = nodes.get(node.id)
        if existing is not None and existing != node:
            raise ValueError(f"graph node collision: {node.id}")
        nodes[node.id] = node

    def add_edge(edge: GraphEdge) -> None:
        key = (edge.source, edge.target, edge.relation, digest_value(edge.metadata))
        edge_values[key] = edge

    for manifest in registry.all():
        module_node = _module_node(manifest.id)
        add_node(
            GraphNode(
                module_node,
                "module",
                manifest.title,
                {
                    "module_id": manifest.id,
                    "module_version": manifest.version,
                    "module_type": manifest.module_type,
                    "domains": manifest.domains,
                    "maturity": manifest.maturity,
                    "access": manifest.access,
                },
            )
        )
        for direction, ports in (("consumes", manifest.input_artifacts), ("produces", manifest.output_artifacts)):
            for port in ports:
                artifact_types.add(port.artifact_type)
                artifact_node = _artifact_node(port.artifact_type)
                add_node(GraphNode(artifact_node, "artifact", port.artifact_type, {"artifact_type": port.artifact_type}))
                add_edge(
                    GraphEdge(
                        module_node,
                        artifact_node,
                        direction,
                        {
                            "module_id": manifest.id,
                            "port": port.name,
                            "formats": tuple(sorted(f"{fmt.name}@{version}" for fmt in port.formats for version in fmt.versions)),
                            "processing_levels": port.processing_levels,
                            "required_metadata": port.required_metadata,
                            "source_policy": port.source_policy,
                        },
                    )
                )
                if manifest.module_type == "validation" and direction == "consumes":
                    add_edge(GraphEdge(module_node, artifact_node, "validates", {"module_id": manifest.id, "port": port.name}))
        for relation, targets in (("alternative-to", manifest.alternatives), ("complements", manifest.complements)):
            for target in targets:
                add_edge(GraphEdge(module_node, _module_node(target), relation, {"module_id": manifest.id, "target_module_id": target}))
        for relation, kind, texts in (("addresses-intent", "intent", manifest.intents), ("addresses-question", "question", manifest.questions)):
            for text in texts:
                semantic_node = _semantic_node(kind, text)
                add_node(GraphNode(semantic_node, kind, text, {"text": text}))
                add_edge(GraphEdge(module_node, semantic_node, relation, {"module_id": manifest.id}))

    ordered_nodes = tuple(sorted(nodes.values(), key=lambda item: item.id))
    ordered_edges = tuple(sorted(edge_values.values(), key=lambda item: (item.source, item.target, item.relation, digest_value(item.metadata))))
    module_ids = tuple(sorted(manifest.id for manifest in registry.all()))
    artifact_index = tuple(sorted(artifact_types))
    return CapabilityGraph(
        nodes=ordered_nodes,
        edges=ordered_edges,
        module_ids=module_ids,
        artifact_types=artifact_index,
        relation_types=RELATION_TYPES,
        digest=digest_value(_graph_basis(ordered_nodes, ordered_edges, module_ids, artifact_index)),
    )


def producers(graph: CapabilityGraph, artifact_type: str) -> tuple[str, ...]:
    target = _artifact_node(artifact_type)
    return tuple(sorted({str(edge.metadata["module_id"]) for edge in graph.edges if edge.relation == "produces" and edge.target == target}))


def consumers(graph: CapabilityGraph, artifact_type: str) -> tuple[str, ...]:
    target = _artifact_node(artifact_type)
    return tuple(sorted({str(edge.metadata["module_id"]) for edge in graph.edges if edge.relation == "consumes" and edge.target == target}))
