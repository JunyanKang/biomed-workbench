"""Canonical project state, validated transitions, serialization, and replay."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from .artifacts import ScientificArtifact
from .context import ProjectContext
from .decisions import DecisionEvent
from .evidence import EvidenceRecord, add_evidence
from .hypotheses import Hypothesis, add_hypothesis, attach_evidence
from .identity import digest_value, freeze_mapping, thaw
from .plans import NODE_STATUSES, PlanNode, ResearchDAG
from .scientific_dependency import AnalysisAdmission, ArtifactReview, ScientificDecision
from .scientific_evidence_map import EvidenceMapPublication


EVENT_TYPES = frozenset(
    {
        "artifact_registered",
        "hypothesis_added",
        "hypothesis_revised",
        "hypothesis_assessed",
        "evidence_added",
        "plan_created",
        "plan_revised",
        "node_status_changed",
        "node_execution_recorded",
        "quality_finding_recorded",
        "analysis_admission_recorded",
        "artifact_review_recorded",
        "scientific_decision_recorded",
        "evidence_map_published",
    }
)


def _state_basis(
    context: ProjectContext,
    artifacts: tuple[ScientificArtifact, ...],
    hypotheses: tuple[Hypothesis, ...],
    evidence: tuple[EvidenceRecord, ...],
    admissions: tuple[AnalysisAdmission, ...],
    artifact_reviews: tuple[ArtifactReview, ...],
    scientific_decisions: tuple[ScientificDecision, ...],
    evidence_map_versions: tuple[EvidenceMapPublication, ...],
    decisions: tuple[DecisionEvent, ...],
    plans: tuple[ResearchDAG, ...],
    active_plan_id: str | None,
    revision: int,
) -> dict[str, object]:
    basis = {
        "schema_version": 1,
        "context": context.to_dict(),
        "artifacts": [item.to_dict() for item in artifacts],
        "hypotheses": [item.to_dict() for item in hypotheses],
        "evidence": [item.to_dict() for item in evidence],
        "decisions": [item.digest_basis() for item in decisions],
        "plans": [item.to_dict() for item in plans],
        "active_plan_id": active_plan_id,
        "revision": revision,
    }
    if admissions or artifact_reviews or scientific_decisions or evidence_map_versions:
        basis.update(
            {
                "analysis_admissions": [item.to_dict() for item in admissions],
                "artifact_reviews": [item.to_dict() for item in artifact_reviews],
                "scientific_decisions": [item.to_dict() for item in scientific_decisions],
                "evidence_map_versions": [item.to_dict() for item in evidence_map_versions],
            }
        )
    return basis


@dataclass(frozen=True)
class ProjectState:
    schema_version: int
    context: ProjectContext
    artifacts: tuple[ScientificArtifact, ...]
    hypotheses: tuple[Hypothesis, ...]
    evidence: tuple[EvidenceRecord, ...]
    analysis_admissions: tuple[AnalysisAdmission, ...]
    artifact_reviews: tuple[ArtifactReview, ...]
    scientific_decisions: tuple[ScientificDecision, ...]
    evidence_map_versions: tuple[EvidenceMapPublication, ...]
    decisions: tuple[DecisionEvent, ...]
    plans: tuple[ResearchDAG, ...]
    active_plan_id: str | None
    revision: int
    state_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != 1 or not isinstance(self.context, ProjectContext):
            raise ValueError("project state schema or context is invalid")
        for field, expected in (
            ("artifacts", ScientificArtifact),
            ("hypotheses", Hypothesis),
            ("evidence", EvidenceRecord),
            ("analysis_admissions", AnalysisAdmission),
            ("artifact_reviews", ArtifactReview),
            ("scientific_decisions", ScientificDecision),
            ("evidence_map_versions", EvidenceMapPublication),
            ("decisions", DecisionEvent),
            ("plans", ResearchDAG),
        ):
            values = tuple(getattr(self, field))
            if any(not isinstance(item, expected) for item in values) or len({item.id for item in values}) != len(values):
                raise ValueError(f"project state {field} must be valid and uniquely identified")
            object.__setattr__(self, field, values)
        if not isinstance(self.revision, int) or self.revision < 0 or self.revision != len(self.decisions):
            raise ValueError("project state revision must equal its event count")
        if tuple(event.sequence for event in self.decisions) != tuple(range(1, self.revision + 1)):
            raise ValueError("project state event sequences must be monotonic")
        artifact_ids = {item.id for item in self.artifacts}
        hypothesis_ids = {item.id for item in self.hypotheses}
        plan_ids = {item.id for item in self.plans}
        plan_nodes = {node.id: node for plan in self.plans for node in plan.nodes}
        if any(not set(item.source_artifact_ids) <= artifact_ids for item in self.artifacts):
            raise ValueError("artifact lineage references unknown inputs")
        if any(item.parent_hypothesis_id is not None and item.parent_hypothesis_id not in hypothesis_ids for item in self.hypotheses):
            raise ValueError("hypothesis lineage references an unknown parent")
        if any(item.artifact_id not in artifact_ids or item.hypothesis_id not in hypothesis_ids for item in self.evidence):
            raise ValueError("evidence references unknown state objects")
        if self.active_plan_id is not None and self.active_plan_id not in plan_ids:
            raise ValueError("active plan is not present in project state")
        if any(item.plan_node_id not in plan_nodes or not set(item.hypothesis_ids) <= hypothesis_ids for item in self.analysis_admissions):
            raise ValueError("analysis admission references unknown plan or hypothesis objects")
        if len({item.plan_node_id for item in self.analysis_admissions}) != len(self.analysis_admissions):
            raise ValueError("each plan node may have only one analysis admission")
        if any(item.artifact_id not in artifact_ids for item in self.artifact_reviews):
            raise ValueError("artifact review references an unknown artifact")
        review_by_id = {item.id: item for item in self.artifact_reviews}
        if len({item.artifact_id for item in self.artifact_reviews}) != len(self.artifact_reviews):
            raise ValueError("each artifact may have only one scientific review")
        for item in self.scientific_decisions:
            review = review_by_id.get(item.review_id)
            if review is None or review.artifact_id != item.artifact_id or not set(item.hypothesis_ids) <= hypothesis_ids:
                raise ValueError("scientific decision references an unknown or mismatched review")
            if item.active_evidence and review.overall_status in {"major", "fatal", "unassessed"}:
                raise ValueError("blocking or unassessed artifacts cannot become active evidence")
        if len({item.artifact_id for item in self.scientific_decisions}) != len(self.scientific_decisions):
            raise ValueError("each artifact may have only one scientific decision")
        if tuple(item.version.revision for item in self.evidence_map_versions) != tuple(range(1, len(self.evidence_map_versions) + 1)):
            raise ValueError("evidence map publications must have continuous revisions")
        expected = digest_value(
            _state_basis(
                self.context,
                self.artifacts,
                self.hypotheses,
                self.evidence,
                self.analysis_admissions,
                self.artifact_reviews,
                self.scientific_decisions,
                self.evidence_map_versions,
                self.decisions,
                self.plans,
                self.active_plan_id,
                self.revision,
            )
        )
        if self.state_digest != expected:
            raise ValueError("project state digest does not match canonical state")
        if self.decisions and self.decisions[-1].resulting_state_digest != self.state_digest:
            raise ValueError("latest decision does not resolve to the project state digest")

    @classmethod
    def create(cls, context: ProjectContext) -> "ProjectState":
        basis = _state_basis(context, (), (), (), (), (), (), (), (), (), None, 0)
        return cls(1, context, (), (), (), (), (), (), (), (), (), None, 0, digest_value(basis))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "context": self.context.to_dict(),
            "artifacts": [item.to_dict() for item in self.artifacts],
            "hypotheses": [item.to_dict() for item in self.hypotheses],
            "evidence": [item.to_dict() for item in self.evidence],
            "analysis_admissions": [item.to_dict() for item in self.analysis_admissions],
            "artifact_reviews": [item.to_dict() for item in self.artifact_reviews],
            "scientific_decisions": [item.to_dict() for item in self.scientific_decisions],
            "evidence_map_versions": [item.to_dict() for item in self.evidence_map_versions],
            "decisions": [item.to_dict() for item in self.decisions],
            "plans": [item.to_dict() for item in self.plans],
            "active_plan_id": self.active_plan_id,
            "revision": self.revision,
            "state_digest": self.state_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProjectState":
        expected_fields = {"schema_version", "context", "artifacts", "hypotheses", "evidence", "analysis_admissions", "artifact_reviews", "scientific_decisions", "evidence_map_versions", "decisions", "plans", "active_plan_id", "revision", "state_digest"}
        legacy_fields = expected_fields - {"analysis_admissions", "artifact_reviews", "scientific_decisions", "evidence_map_versions"}
        if frozenset(payload) not in {frozenset(expected_fields), frozenset(legacy_fields)}:
            raise ValueError("project state uses an unsupported serialized field set")
        normalized = dict(payload)
        for field in ("analysis_admissions", "artifact_reviews", "scientific_decisions", "evidence_map_versions"):
            normalized.setdefault(field, [])
        state = cls(
            schema_version=normalized["schema_version"],
            context=ProjectContext.from_dict(normalized["context"]),
            artifacts=tuple(ScientificArtifact.from_dict(item) for item in normalized["artifacts"]),
            hypotheses=tuple(Hypothesis.from_dict(item) for item in normalized["hypotheses"]),
            evidence=tuple(EvidenceRecord.from_dict(item) for item in normalized["evidence"]),
            analysis_admissions=tuple(AnalysisAdmission.from_dict(item) for item in normalized["analysis_admissions"]),
            artifact_reviews=tuple(ArtifactReview.from_dict(item) for item in normalized["artifact_reviews"]),
            scientific_decisions=tuple(ScientificDecision.from_dict(item) for item in normalized["scientific_decisions"]),
            evidence_map_versions=tuple(EvidenceMapPublication.from_dict(item) for item in normalized["evidence_map_versions"]),
            decisions=tuple(DecisionEvent.from_dict(item) for item in normalized["decisions"]),
            plans=tuple(ResearchDAG.from_dict(item) for item in normalized["plans"]),
            active_plan_id=normalized["active_plan_id"],
            revision=normalized["revision"],
            state_digest=normalized["state_digest"],
        )
        if replay(state.context, state.decisions).to_dict() != state.to_dict():
            raise ValueError("serialized project state does not match event replay")
        return state


def _apply_payload(state: ProjectState, event_type: str, payload: Mapping[str, Any]):
    artifacts, hypotheses, evidence = state.artifacts, state.hypotheses, state.evidence
    admissions, reviews = state.analysis_admissions, state.artifact_reviews
    scientific_decisions, evidence_map_versions = state.scientific_decisions, state.evidence_map_versions
    plans, active_plan_id = state.plans, state.active_plan_id
    if event_type == "artifact_registered":
        if set(payload) != {"artifact"}:
            raise ValueError("artifact_registered payload must contain exactly artifact")
        item = ScientificArtifact.from_dict(payload["artifact"])
        if item.id in {value.id for value in artifacts} or not set(item.source_artifact_ids) <= {value.id for value in artifacts}:
            raise ValueError("artifact registration has duplicate or unknown lineage")
        artifacts = (*artifacts, item)
    elif event_type in {"hypothesis_added", "hypothesis_revised"}:
        if set(payload) != {"hypothesis"}:
            raise ValueError(f"{event_type} payload must contain exactly hypothesis")
        item = Hypothesis.from_dict(payload["hypothesis"])
        if event_type == "hypothesis_added" and item.parent_hypothesis_id is not None:
            raise ValueError("hypothesis_added cannot introduce a revision")
        if event_type == "hypothesis_revised" and item.parent_hypothesis_id is None:
            raise ValueError("hypothesis_revised requires a parent")
        hypotheses = add_hypothesis(hypotheses, item)
    elif event_type == "evidence_added":
        if set(payload) != {"evidence"}:
            raise ValueError("evidence_added payload must contain exactly evidence")
        item = EvidenceRecord.from_dict(payload["evidence"])
        if item.artifact_id not in {value.id for value in artifacts} or item.hypothesis_id not in {value.id for value in hypotheses}:
            raise ValueError("evidence references unknown state objects")
        evidence = add_evidence(evidence, item)
        hypotheses = tuple(attach_evidence(value, item) if value.id == item.hypothesis_id else value for value in hypotheses)
    elif event_type in {"plan_created", "plan_revised"}:
        if set(payload) != {"plan", "activate"} or not isinstance(payload["activate"], bool):
            raise ValueError(f"{event_type} payload must contain exactly plan and boolean activate")
        item = ResearchDAG.from_dict(payload["plan"])
        if item.id in {value.id for value in plans}:
            raise ValueError("plan ID already exists")
        if event_type == "plan_created" and item.parent_plan_id is not None:
            raise ValueError("plan_created cannot introduce a revision")
        if event_type == "plan_revised" and (item.parent_plan_id is None or item.parent_plan_id not in {value.id for value in plans}):
            raise ValueError("plan_revised requires a known parent")
        artifact_ids = {value.id for value in artifacts}
        hypothesis_ids = {value.id for value in hypotheses}
        output_owner = {artifact_id: node.id for node in item.nodes for artifact_id in node.planned_output_artifact_ids.values()}
        if set(output_owner) & artifact_ids:
            raise ValueError("planned outputs cannot overwrite registered artifacts")
        for node in item.nodes:
            if not set(node.target_hypothesis_ids) <= hypothesis_ids:
                raise ValueError("plan nodes reference unknown hypotheses")
            for artifact_id in node.input_bindings.values():
                if artifact_id in artifact_ids:
                    continue
                owner = output_owner.get(artifact_id)
                if owner is None or owner not in node.dependencies:
                    raise ValueError("plan nodes reference unknown artifacts or undeclared producer dependencies")
        plans = (*plans, item)
        if payload["activate"]:
            active_plan_id = item.id
    elif event_type == "node_status_changed":
        if set(payload) != {"plan_id", "node_id", "status", "attempt"} or payload["status"] not in NODE_STATUSES:
            raise ValueError("node_status_changed payload is invalid")
        if not isinstance(payload["attempt"], int) or payload["attempt"] < 0:
            raise ValueError("node status attempt must be nonnegative")
        plan_index = next((index for index, value in enumerate(plans) if value.id == payload["plan_id"]), None)
        if plan_index is None:
            raise ValueError("node status references an unknown plan")
        plan = plans[plan_index]
        if payload["node_id"] not in {node.id for node in plan.nodes}:
            raise ValueError("node status references an unknown node")
        nodes = tuple(
            replace(node, status=payload["status"], attempt=payload["attempt"])
            if node.id == payload["node_id"]
            else node
            for node in plan.nodes
        )
        updated = ResearchDAG.create(
            id=plan.id,
            objective=plan.objective,
            nodes=nodes,
            required_output_artifact_types=plan.required_output_artifact_types,
            plan_type=plan.plan_type,
            revision=plan.revision,
            parent_plan_id=plan.parent_plan_id,
            rationale=plan.rationale,
        )
        plans = tuple(updated if index == plan_index else value for index, value in enumerate(plans))
    elif event_type == "hypothesis_assessed":
        if set(payload) != {"hypothesis_id", "status"}:
            raise ValueError("hypothesis_assessed payload is invalid")
        if payload["hypothesis_id"] not in {item.id for item in hypotheses}:
            raise ValueError("hypothesis assessment references an unknown hypothesis")
        hypotheses = tuple(replace(item, status=payload["status"]) if item.id == payload["hypothesis_id"] else item for item in hypotheses)
    elif event_type == "node_execution_recorded":
        if set(payload) != {"execution"} or not isinstance(payload["execution"], dict):
            raise ValueError("node_execution_recorded payload is invalid")
    elif event_type == "quality_finding_recorded":
        if set(payload) != {"finding"} or not isinstance(payload["finding"], dict):
            raise ValueError("quality_finding_recorded payload is invalid")
    elif event_type == "analysis_admission_recorded":
        if set(payload) != {"admission"}:
            raise ValueError("analysis_admission_recorded payload is invalid")
        item = AnalysisAdmission.from_dict(payload["admission"])
        plan_nodes = {node.id: node for plan in plans for node in plan.nodes}
        if item.plan_node_id not in plan_nodes or item.plan_node_id in {value.plan_node_id for value in admissions}:
            raise ValueError("analysis admission requires one known, previously unadmitted plan node")
        if not set(item.hypothesis_ids) <= {value.id for value in hypotheses}:
            raise ValueError("analysis admission references an unknown hypothesis")
        if item.approved and not set(plan_nodes[item.plan_node_id].expected_output_artifact_types) <= set(item.expected_artifact_types):
            raise ValueError("approved analysis admission omits planned output types")
        admissions = (*admissions, item)
    elif event_type == "artifact_review_recorded":
        if set(payload) != {"review"}:
            raise ValueError("artifact_review_recorded payload is invalid")
        item = ArtifactReview.from_dict(payload["review"])
        if item.artifact_id not in {value.id for value in artifacts} or item.artifact_id in {value.artifact_id for value in reviews}:
            raise ValueError("artifact review requires one known, previously unreviewed artifact")
        reviews = (*reviews, item)
    elif event_type == "scientific_decision_recorded":
        if set(payload) != {"decision"}:
            raise ValueError("scientific_decision_recorded payload is invalid")
        item = ScientificDecision.from_dict(payload["decision"])
        review = next((value for value in reviews if value.id == item.review_id), None)
        if review is None or review.artifact_id != item.artifact_id or item.artifact_id in {value.artifact_id for value in scientific_decisions}:
            raise ValueError("scientific decision requires the matching, previously undecided review")
        if item.active_evidence and review.overall_status in {"major", "fatal", "unassessed"}:
            raise ValueError("blocking or unassessed review cannot release active evidence")
        scientific_decisions = (*scientific_decisions, item)
    elif event_type == "evidence_map_published":
        if set(payload) != {"publication"}:
            raise ValueError("evidence_map_published payload is invalid")
        item = EvidenceMapPublication.from_dict(payload["publication"])
        if item.source_state_digest != state.state_digest:
            raise ValueError("evidence map publication must bind the immediately preceding project state")
        if item.version.revision != len(evidence_map_versions) + 1:
            raise ValueError("evidence map publication revision is not continuous")
        if evidence_map_versions and item.version.parent_map_digest != evidence_map_versions[-1].map_digest:
            raise ValueError("evidence map publication parent does not match the active map")
        evidence_map_versions = (*evidence_map_versions, item)
    return artifacts, hypotheses, evidence, admissions, reviews, scientific_decisions, evidence_map_versions, plans, active_plan_id


def apply_event(
    state: ProjectState,
    event_type: str,
    payload: Mapping[str, Any],
    *,
    rationale: str,
    trigger_finding_ids: tuple[str, ...] = (),
    affected_artifact_ids: tuple[str, ...] = (),
    affected_hypothesis_ids: tuple[str, ...] = (),
    superseded_action_ids: tuple[str, ...] = (),
    replacement_action_ids: tuple[str, ...] = (),
    prior_results_valid: bool = True,
) -> ProjectState:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported project event type: {event_type}")
    safe_payload = thaw(freeze_mapping(payload))
    artifacts, hypotheses, evidence, admissions, reviews, scientific_decisions, evidence_map_versions, plans, active_plan_id = _apply_payload(state, event_type, safe_payload)
    known_artifacts = {item.id for item in artifacts}
    known_hypotheses = {item.id for item in hypotheses}
    if not set(affected_artifact_ids) <= known_artifacts or not set(affected_hypothesis_ids) <= known_hypotheses:
        raise ValueError("decision metadata references unknown affected state objects")
    known_actions = {node.id for plan in plans for node in plan.nodes}
    if not set(superseded_action_ids) <= known_actions or not set(replacement_action_ids) <= known_actions:
        raise ValueError("decision metadata references unknown plan actions")
    sequence = state.revision + 1
    identity_basis = {
        "sequence": sequence,
        "event_type": event_type,
        "payload": safe_payload,
        "prior_state_digest": state.state_digest,
    }
    event_id = f"event-{sequence:06d}-{digest_value(identity_basis)[:12]}"
    provisional = DecisionEvent(
        id=event_id,
        sequence=sequence,
        event_type=event_type,
        rationale=rationale,
        trigger_finding_ids=trigger_finding_ids,
        affected_artifact_ids=affected_artifact_ids,
        affected_hypothesis_ids=affected_hypothesis_ids,
        superseded_action_ids=superseded_action_ids,
        replacement_action_ids=replacement_action_ids,
        prior_results_valid=prior_results_valid,
        payload=safe_payload,
        prior_state_digest=state.state_digest,
        resulting_state_digest="0" * 64,
    )
    decisions = (*state.decisions, provisional)
    resulting_digest = digest_value(
        _state_basis(
            state.context,
            artifacts,
            hypotheses,
            evidence,
            admissions,
            reviews,
            scientific_decisions,
            evidence_map_versions,
            decisions,
            plans,
            active_plan_id,
            sequence,
        )
    )
    final_event = replace(provisional, resulting_state_digest=resulting_digest)
    return ProjectState(
        1,
        state.context,
        artifacts,
        hypotheses,
        evidence,
        admissions,
        reviews,
        scientific_decisions,
        evidence_map_versions,
        (*state.decisions, final_event),
        plans,
        active_plan_id,
        sequence,
        resulting_digest,
    )


def replay(context: ProjectContext, decisions: tuple[DecisionEvent, ...]) -> ProjectState:
    state = ProjectState.create(context)
    for expected in decisions:
        if expected.sequence != state.revision + 1 or expected.prior_state_digest != state.state_digest:
            raise ValueError("decision sequence or prior-state chain is broken")
        generated = apply_event(
            state,
            expected.event_type,
            thaw(expected.payload),
            rationale=expected.rationale,
            trigger_finding_ids=expected.trigger_finding_ids,
            affected_artifact_ids=expected.affected_artifact_ids,
            affected_hypothesis_ids=expected.affected_hypothesis_ids,
            superseded_action_ids=expected.superseded_action_ids,
            replacement_action_ids=expected.replacement_action_ids,
            prior_results_valid=expected.prior_results_valid,
        )
        if generated.decisions[-1] != expected:
            raise ValueError("decision event does not match deterministic replay")
        state = generated
    return state
