"""Project-level scientific dependency, review, and decision contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping

from .identity import digest_value, freeze_mapping, thaw, validate_identifier
from .execution_chain import validate_artifact_execution_chain, validate_validated_delivery_state
if TYPE_CHECKING:
    from .state import ProjectState


DECISION_ACTIONS = frozenset(
    {
        "retain-as-evidence",
        "retain-with-caveat",
        "exclude-invalid",
        "exclude-noninformative",
        "rerun-same-method",
        "rerun-adjusted-parameters",
        "switch-method",
        "acquire-more-data",
        "revise-hypothesis",
        "revise-project-scope",
        "stop-branch",
    }
)
REVIEW_STATUSES = frozenset({"passed", "warning", "major", "fatal", "unassessed"})
ARTIFACT_KINDS = frozenset({"data", "table", "figure", "model", "report", "other"})
EDGE_RELATIONS = (
    "motivates",
    "tests",
    "consumes",
    "produces",
    "derived-from",
    "reviews",
    "adjudicates",
    "supports",
    "weakens",
    "refutes",
    "inconclusive",
    "retains",
    "excludes",
    "triggers",
)
EVIDENCE_MAP_KINDS = frozenset({"project-snapshot", "validated-delivery"})


def _text(value: str, location: str, minimum: int = 12) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise ValueError(f"{location} must be meaningful bilingual scientific text")
    freeze_mapping({location: value.strip()})
    return value.strip()


def _ids(values: tuple[str, ...], location: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    result = tuple(validate_identifier(value, location) for value in values)
    if (not allow_empty and not result) or len(set(result)) != len(result):
        raise ValueError(f"{location} must be a unique {'possibly empty ' if allow_empty else 'nonempty '}list")
    return result


def _urls(values: tuple[str, ...], location: str) -> tuple[str, ...]:
    if not values or any(not isinstance(value, str) or not value.startswith(("https://", "http://")) for value in values):
        raise ValueError(f"{location} requires official or primary HTTP sources")
    if len(set(values)) != len(values):
        raise ValueError(f"{location} contains duplicate sources")
    return tuple(values)


@dataclass(frozen=True)
class AnalysisAdmission:
    id: str
    plan_node_id: str
    hypothesis_ids: tuple[str, ...]
    rationale_zh: str
    rationale_en: str
    method: str
    official_sources: tuple[str, ...]
    alternatives_considered: tuple[str, ...]
    assumptions: tuple[str, ...]
    parameter_justifications: Mapping[str, str]
    acceptance_criteria: tuple[str, ...]
    falsification_criteria: tuple[str, ...]
    expected_artifact_types: tuple[str, ...]
    approved: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "analysis_admission.id"))
        object.__setattr__(self, "plan_node_id", validate_identifier(self.plan_node_id, "analysis_admission.plan_node_id"))
        object.__setattr__(self, "hypothesis_ids", _ids(tuple(self.hypothesis_ids), "analysis_admission.hypothesis_ids"))
        object.__setattr__(self, "rationale_zh", _text(self.rationale_zh, "analysis_admission.rationale_zh"))
        object.__setattr__(self, "rationale_en", _text(self.rationale_en, "analysis_admission.rationale_en"))
        object.__setattr__(self, "method", _text(self.method, "analysis_admission.method"))
        object.__setattr__(self, "official_sources", _urls(tuple(self.official_sources), "analysis_admission.official_sources"))
        for field in ("alternatives_considered", "assumptions", "acceptance_criteria", "falsification_criteria"):
            values = tuple(_text(value, f"analysis_admission.{field}") for value in getattr(self, field))
            if not values or len(set(values)) != len(values):
                raise ValueError(f"analysis_admission.{field} must be nonempty and unique")
            object.__setattr__(self, field, values)
        object.__setattr__(
            self,
            "expected_artifact_types",
            _ids(tuple(self.expected_artifact_types), "analysis_admission.expected_artifact_types"),
        )
        justifications = freeze_mapping(self.parameter_justifications)
        if not justifications or any(not isinstance(value, str) or len(value.strip()) < 12 for value in justifications.values()):
            raise ValueError("analysis_admission.parameter_justifications must explain every adjustable parameter")
        object.__setattr__(self, "parameter_justifications", justifications)
        if not isinstance(self.approved, bool):
            raise ValueError("analysis_admission.approved must be boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "plan_node_id": self.plan_node_id,
            "hypothesis_ids": list(self.hypothesis_ids),
            "rationale_zh": self.rationale_zh,
            "rationale_en": self.rationale_en,
            "method": self.method,
            "official_sources": list(self.official_sources),
            "alternatives_considered": list(self.alternatives_considered),
            "assumptions": list(self.assumptions),
            "parameter_justifications": thaw(self.parameter_justifications),
            "acceptance_criteria": list(self.acceptance_criteria),
            "falsification_criteria": list(self.falsification_criteria),
            "expected_artifact_types": list(self.expected_artifact_types),
            "approved": self.approved,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AnalysisAdmission":
        values = dict(payload)
        for field in (
            "hypothesis_ids",
            "official_sources",
            "alternatives_considered",
            "assumptions",
            "acceptance_criteria",
            "falsification_criteria",
            "expected_artifact_types",
        ):
            values[field] = tuple(values[field])
        return cls(**values)


@dataclass(frozen=True)
class PanelInterpretation:
    panel_id: str
    rationale_zh: str
    rationale_en: str
    methods_zh: str
    methods_en: str
    results_zh: str
    results_en: str
    conclusion_zh: str
    conclusion_en: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "panel_id", validate_identifier(self.panel_id, "panel.panel_id"))
        for field in (
            "rationale_zh", "rationale_en", "methods_zh", "methods_en",
            "results_zh", "results_en", "conclusion_zh", "conclusion_en",
        ):
            object.__setattr__(self, field, _text(getattr(self, field), f"panel.{field}"))

    def to_dict(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PanelInterpretation":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ArtifactReview:
    id: str
    artifact_id: str
    artifact_kind: str
    rationale_zh: str
    rationale_en: str
    methods_zh: str
    methods_en: str
    results_zh: str
    results_en: str
    conclusion_zh: str
    conclusion_en: str
    panels: tuple[PanelInterpretation, ...]
    technical_status: str
    statistical_status: str
    biological_status: str
    robustness_status: str
    limitations_zh: tuple[str, ...]
    limitations_en: tuple[str, ...]
    recommended_action: str
    source_urls: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "artifact_review.id"))
        object.__setattr__(self, "artifact_id", validate_identifier(self.artifact_id, "artifact_review.artifact_id"))
        if self.artifact_kind not in ARTIFACT_KINDS:
            raise ValueError("artifact_review.artifact_kind is unsupported")
        for field in (
            "rationale_zh", "rationale_en", "methods_zh", "methods_en",
            "results_zh", "results_en", "conclusion_zh", "conclusion_en",
        ):
            object.__setattr__(self, field, _text(getattr(self, field), f"artifact_review.{field}"))
        panels = tuple(self.panels)
        if any(not isinstance(panel, PanelInterpretation) for panel in panels) or len({panel.panel_id for panel in panels}) != len(panels):
            raise ValueError("artifact_review panels must be valid and uniquely identified")
        if self.artifact_kind == "figure" and not panels:
            raise ValueError("figure reviews require panel-specific interpretations")
        if self.artifact_kind != "figure" and panels:
            raise ValueError("only figure reviews may contain panel interpretations")
        object.__setattr__(self, "panels", panels)
        for field in ("technical_status", "statistical_status", "biological_status", "robustness_status"):
            if getattr(self, field) not in REVIEW_STATUSES:
                raise ValueError(f"artifact_review.{field} is unsupported")
        for field in ("limitations_zh", "limitations_en"):
            values = tuple(_text(value, f"artifact_review.{field}") for value in getattr(self, field))
            if not values:
                raise ValueError(f"artifact_review.{field} must state limitations")
            object.__setattr__(self, field, values)
        if self.recommended_action not in DECISION_ACTIONS:
            raise ValueError("artifact_review.recommended_action is unsupported")
        object.__setattr__(self, "source_urls", _urls(tuple(self.source_urls), "artifact_review.source_urls"))

    @property
    def overall_status(self) -> str:
        rank = {"unassessed": 0, "passed": 1, "warning": 2, "major": 3, "fatal": 4}
        return max(
            (self.technical_status, self.statistical_status, self.biological_status, self.robustness_status),
            key=rank.__getitem__,
        )

    def to_dict(self) -> dict[str, object]:
        payload = {field: getattr(self, field) for field in self.__dataclass_fields__}
        payload["panels"] = [panel.to_dict() for panel in self.panels]
        payload["limitations_zh"] = list(self.limitations_zh)
        payload["limitations_en"] = list(self.limitations_en)
        payload["source_urls"] = list(self.source_urls)
        payload["overall_status"] = self.overall_status
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactReview":
        values = dict(payload)
        values.pop("overall_status", None)
        values["panels"] = tuple(PanelInterpretation.from_dict(item) for item in values["panels"])
        values["limitations_zh"] = tuple(values["limitations_zh"])
        values["limitations_en"] = tuple(values["limitations_en"])
        values["source_urls"] = tuple(values["source_urls"])
        return cls(**values)


@dataclass(frozen=True)
class ScientificDecision:
    id: str
    review_id: str
    artifact_id: str
    hypothesis_ids: tuple[str, ...]
    action: str
    rationale_zh: str
    rationale_en: str
    active_evidence: bool
    next_plan_node_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "scientific_decision.id"))
        object.__setattr__(self, "review_id", validate_identifier(self.review_id, "scientific_decision.review_id"))
        object.__setattr__(self, "artifact_id", validate_identifier(self.artifact_id, "scientific_decision.artifact_id"))
        object.__setattr__(self, "hypothesis_ids", _ids(tuple(self.hypothesis_ids), "scientific_decision.hypothesis_ids", allow_empty=True))
        if self.action not in DECISION_ACTIONS:
            raise ValueError("scientific_decision.action is unsupported")
        object.__setattr__(self, "rationale_zh", _text(self.rationale_zh, "scientific_decision.rationale_zh"))
        object.__setattr__(self, "rationale_en", _text(self.rationale_en, "scientific_decision.rationale_en"))
        object.__setattr__(self, "next_plan_node_ids", _ids(tuple(self.next_plan_node_ids), "scientific_decision.next_plan_node_ids", allow_empty=True))
        retain = self.action in {"retain-as-evidence", "retain-with-caveat"}
        if self.active_evidence != retain:
            raise ValueError("active_evidence must be true exactly for retained decisions")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "review_id": self.review_id,
            "artifact_id": self.artifact_id,
            "hypothesis_ids": list(self.hypothesis_ids),
            "action": self.action,
            "rationale_zh": self.rationale_zh,
            "rationale_en": self.rationale_en,
            "active_evidence": self.active_evidence,
            "next_plan_node_ids": list(self.next_plan_node_ids),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificDecision":
        values = dict(payload)
        values["hypothesis_ids"] = tuple(values["hypothesis_ids"])
        values["next_plan_node_ids"] = tuple(values["next_plan_node_ids"])
        return cls(**values)


@dataclass(frozen=True)
class DependencyNode:
    id: str
    kind: str
    label: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "kind": self.kind, "label": self.label}


@dataclass(frozen=True)
class DependencyEdge:
    source: str
    target: str
    relation: str

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "target": self.target, "relation": self.relation}


@dataclass(frozen=True)
class ScientificDependencyBundle:
    admissions: tuple[AnalysisAdmission, ...]
    reviews: tuple[ArtifactReview, ...]
    decisions: tuple[ScientificDecision, ...]
    map_kind: str
    digest: str

    @classmethod
    def create(
        cls,
        state: ProjectState,
        *,
        admissions: tuple[AnalysisAdmission, ...],
        reviews: tuple[ArtifactReview, ...],
        decisions: tuple[ScientificDecision, ...],
        map_kind: str = "project-snapshot",
    ) -> "ScientificDependencyBundle":
        if map_kind not in EVIDENCE_MAP_KINDS:
            raise ValueError("scientific dependency bundle map kind is unsupported")
        values = cls(tuple(admissions), tuple(reviews), tuple(decisions), map_kind, "0" * 64)
        values._validate(state)
        basis = {
            "admissions": [item.to_dict() for item in values.admissions],
            "reviews": [item.to_dict() for item in values.reviews],
            "decisions": [item.to_dict() for item in values.decisions],
            "map_kind": values.map_kind,
        }
        return cls(values.admissions, values.reviews, values.decisions, values.map_kind, digest_value(basis))

    def _validate(self, state: ProjectState) -> None:
        plan_nodes = {node.id: node for plan in state.plans for node in plan.nodes}
        hypotheses = {item.id for item in state.hypotheses}
        artifacts = {item.id: item for item in state.artifacts}
        if len({item.id for item in self.admissions}) != len(self.admissions):
            raise ValueError("analysis admissions contain duplicate IDs")
        if set(item.plan_node_id for item in self.admissions) != set(plan_nodes):
            raise ValueError("every plan node requires exactly one analysis admission")
        for item in self.admissions:
            if not set(item.hypothesis_ids) <= hypotheses:
                raise ValueError("analysis admission references an unknown hypothesis")
            if item.approved and not set(plan_nodes[item.plan_node_id].expected_output_artifact_types) <= set(item.expected_artifact_types):
                raise ValueError("approved analysis admission omits planned output types")
        if len({item.artifact_id for item in self.reviews}) != len(self.reviews) or {item.artifact_id for item in self.reviews} != set(artifacts):
            raise ValueError("every registered artifact requires exactly one bilingual review")
        for review in self.reviews:
            artifact = artifacts[review.artifact_id]
            panel_ids = artifact.content.get("panel_ids")
            if review.artifact_kind == "figure" and isinstance(panel_ids, tuple):
                if {panel.panel_id for panel in review.panels} != set(panel_ids):
                    raise ValueError("figure review panel coverage differs from artifact panel_ids")
        reviews = {item.id: item for item in self.reviews}
        if len({item.artifact_id for item in self.decisions}) != len(self.decisions) or {item.artifact_id for item in self.decisions} != set(artifacts):
            raise ValueError("every reviewed artifact requires exactly one scientific decision")
        for decision in self.decisions:
            review = reviews.get(decision.review_id)
            if review is None or review.artifact_id != decision.artifact_id:
                raise ValueError("scientific decision references the wrong review")
            if not set(decision.hypothesis_ids) <= hypotheses or not set(decision.next_plan_node_ids) <= set(plan_nodes):
                raise ValueError("scientific decision references unknown hypothesis or next analysis")
            if decision.active_evidence and review.overall_status in {"major", "fatal", "unassessed"}:
                raise ValueError("blocking or unassessed artifacts cannot become active evidence")
        if self.map_kind == "validated-delivery":
            active = {item.artifact_id for item in self.decisions if item.active_evidence}
            if not active:
                raise ValueError("validated-delivery evidence map requires retained active evidence")
            active_produced = {artifact_id for artifact_id in active if artifacts[artifact_id].producing_module_id is not None}
            if not active_produced:
                raise ValueError("validated-delivery evidence map requires an executed, reloaded, reviewed, and retained result")
            for artifact_id in active_produced:
                validate_artifact_execution_chain(state, artifact_id)
            active_plan = next((item for item in state.plans if item.id == state.active_plan_id), None)
            validate_validated_delivery_state(state)
            active_types = {artifacts[artifact_id].artifact_type for artifact_id in active_produced}
            if not set(active_plan.required_output_artifact_types) <= active_types:
                raise ValueError("validated-delivery active evidence does not satisfy the plan's required outputs")


@dataclass(frozen=True)
class ScientificDependencyGraph:
    nodes: tuple[DependencyNode, ...]
    edges: tuple[DependencyEdge, ...]
    active_evidence_artifact_ids: tuple[str, ...]
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "active_evidence_artifact_ids": list(self.active_evidence_artifact_ids),
            "digest": self.digest,
        }


def build_scientific_dependency_graph(
    state: ProjectState, bundle: ScientificDependencyBundle
) -> ScientificDependencyGraph:
    bundle._validate(state)
    nodes: dict[str, DependencyNode] = {}
    edges: set[tuple[str, str, str]] = set()

    def node(identifier: str, kind: str, label: str) -> None:
        nodes[identifier] = DependencyNode(identifier, kind, label)

    def edge(source: str, target: str, relation: str) -> None:
        if relation not in EDGE_RELATIONS:
            raise ValueError("unsupported scientific dependency relation")
        edges.add((source, target, relation))

    question_id = f"question-{state.context.project_id}"
    node(question_id, "research-question", state.context.scientific_question)
    for hypothesis in state.hypotheses:
        node(hypothesis.id, "hypothesis", hypothesis.statement)
        edge(question_id, hypothesis.id, "motivates")
    admission_by_node = {item.plan_node_id: item for item in bundle.admissions}
    for plan in state.plans:
        for action in plan.nodes:
            node(action.id, "analysis", action.module_id)
            admission = admission_by_node[action.id]
            node(admission.id, "analysis-admission", admission.method)
            edge(admission.id, action.id, "triggers")
            for hypothesis_id in admission.hypothesis_ids:
                edge(hypothesis_id, action.id, "tests")
            for artifact_id in action.input_bindings.values():
                if artifact_id in {item.id for item in state.artifacts}:
                    edge(artifact_id, action.id, "consumes")
            for artifact_id in action.planned_output_artifact_ids.values():
                if artifact_id in {item.id for item in state.artifacts}:
                    edge(action.id, artifact_id, "produces")
    for artifact in state.artifacts:
        node(artifact.id, "artifact", artifact.artifact_type)
        for source in artifact.source_artifact_ids:
            edge(artifact.id, source, "derived-from")
    for evidence in state.evidence:
        node(evidence.id, "evidence", evidence.evidence_type)
        edge(evidence.artifact_id, evidence.id, "supports")
        edge(evidence.id, evidence.hypothesis_id, evidence.relation)
    review_by_id = {item.id: item for item in bundle.reviews}
    for review in bundle.reviews:
        node(review.id, "artifact-review", review.overall_status)
        edge(review.id, review.artifact_id, "reviews")
    active = []
    for decision in bundle.decisions:
        node(decision.id, "scientific-decision", decision.action)
        edge(decision.id, decision.review_id, "adjudicates")
        edge(decision.id, decision.artifact_id, "retains" if decision.active_evidence else "excludes")
        for next_node in decision.next_plan_node_ids:
            edge(decision.id, next_node, "triggers")
        if decision.active_evidence:
            active.append(decision.artifact_id)
    ordered_nodes = tuple(sorted(nodes.values(), key=lambda item: item.id))
    ordered_edges = tuple(DependencyEdge(*values) for values in sorted(edges))
    basis = {
        "nodes": [item.to_dict() for item in ordered_nodes],
        "edges": [item.to_dict() for item in ordered_edges],
        "active_evidence_artifact_ids": sorted(active),
        "state_digest": state.state_digest,
        "review_statuses": {key: value.overall_status for key, value in review_by_id.items()},
    }
    return ScientificDependencyGraph(
        ordered_nodes,
        ordered_edges,
        tuple(sorted(active)),
        digest_value(basis),
    )
