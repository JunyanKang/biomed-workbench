"""Cross-event validation for observed execution, reload, review, and delivery state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .identity import digest_value

if TYPE_CHECKING:
    from .state import ProjectState


@dataclass(frozen=True)
class DeliveryPrerequisiteScope:
    plan_id: str
    delivery_node_id: str
    covered_node_ids: tuple[str, ...]
    covered_artifact_ids: tuple[str, ...]
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "delivery_node_id": self.delivery_node_id,
            "covered_node_ids": list(self.covered_node_ids),
            "covered_artifact_ids": list(self.covered_artifact_ids),
            "digest": self.digest,
        }


def validate_artifact_execution_chain(
    state: "ProjectState",
    artifact_id: str,
    *,
    require_completed_node: bool = True,
) -> str:
    """Return the producing node ID after validating one complete receipt chain."""
    artifact = next((item for item in state.artifacts if item.id == artifact_id), None)
    if artifact is None:
        raise ValueError("execution chain references an unknown artifact")
    if artifact.producing_module_id is None:
        raise ValueError("project input artifacts use input qualification, not execution receipts")
    reload_receipt = next((item for item in state.artifact_reloads if item.artifact_id == artifact_id), None)
    if reload_receipt is None or reload_receipt.content_digest != artifact.content_digest:
        raise ValueError("produced artifact has no matching reload receipt")
    observed = next(
        (item for item in state.observed_executions if item.id == reload_receipt.observed_execution_receipt_id),
        None,
    )
    if (
        observed is None
        or observed.module_id != artifact.producing_module_id
        or observed.module_version != artifact.producing_module_version
        or observed.output_artifact_digests.get(artifact_id) != artifact.content_digest
    ):
        raise ValueError("produced artifact has no matching observed execution receipt")
    integrity_review = next(
        (
            item
            for item in state.execution_reviews
            if item.observed_execution_receipt_id == observed.id
            and reload_receipt.id in item.artifact_reload_receipt_ids
        ),
        None,
    )
    if integrity_review is None or not integrity_review.active_evidence_allowed:
        raise ValueError("produced artifact has no accepted execution-integrity review")
    node = next(
        (
            item
            for plan in state.plans
            for item in plan.nodes
            if item.id == observed.plan_node_id and artifact_id in item.planned_output_artifact_ids.values()
        ),
        None,
    )
    if node is None or (require_completed_node and node.status != "completed"):
        raise ValueError("produced artifact belongs to an unfinished plan node")
    return node.id


def validate_node_execution_chain(
    state: "ProjectState",
    node_id: str,
    *,
    require_completed_node: bool = True,
    require_active_decisions: bool = False,
) -> tuple[str, ...]:
    """Validate every planned output of one node as one closed execution slice."""
    node = next((item for plan in state.plans for item in plan.nodes if item.id == node_id), None)
    if node is None:
        raise ValueError("execution chain references an unknown plan node")
    output_ids = tuple(node.planned_output_artifact_ids.values())
    if not output_ids:
        raise ValueError("execution chain node has no planned outputs")
    observed = tuple(item for item in state.observed_executions if item.plan_node_id == node_id)
    if len(observed) != 1 or set(observed[0].output_artifact_digests) != set(output_ids):
        raise ValueError("plan node has no exact observed execution covering every output")
    for artifact_id in output_ids:
        if validate_artifact_execution_chain(
            state,
            artifact_id,
            require_completed_node=require_completed_node,
        ) != node_id:
            raise ValueError("plan node output is bound to another producer")
    if require_active_decisions:
        active = {item.artifact_id for item in state.scientific_decisions if item.active_evidence}
        if not set(output_ids) <= active:
            raise ValueError("plan node outputs lack retained scientific decisions")
    return output_ids


def validate_validated_delivery_state(state: "ProjectState") -> tuple[str, ...]:
    """Require a terminal active plan and identity-level retained leaf deliverables."""
    active_plan = next((item for item in state.plans if item.id == state.active_plan_id), None)
    if active_plan is None or any(node.status != "completed" for node in active_plan.nodes):
        raise ValueError("validated-delivery requires every active plan node to be completed")
    dependency_ids = {dependency for node in active_plan.nodes for dependency in node.dependencies}
    leaf_nodes = tuple(node for node in active_plan.nodes if node.id not in dependency_ids)
    required_ids = tuple(
        artifact_id
        for node in leaf_nodes
        for artifact_id in node.planned_output_artifact_ids.values()
    )
    active_ids = {item.artifact_id for item in state.scientific_decisions if item.active_evidence}
    if not required_ids or not set(required_ids) <= active_ids:
        raise ValueError("validated-delivery lacks one or more retained leaf deliverable identities")
    for node in leaf_nodes:
        validate_node_execution_chain(
            state,
            node.id,
            require_completed_node=True,
            require_active_decisions=True,
        )
    return required_ids


def validate_delivery_prerequisites(
    state: "ProjectState",
    delivery_node_id: str,
) -> DeliveryPrerequisiteScope:
    """Validate the exact retained upstream slice that may authorize delivery."""
    active_plan = next((item for item in state.plans if item.id == state.active_plan_id), None)
    if active_plan is None:
        raise ValueError("delivery authorization requires an active plan")
    nodes = {item.id: item for item in active_plan.nodes}
    delivery = nodes.get(delivery_node_id)
    if delivery is None:
        raise ValueError("delivery authorization references a node outside the active plan")
    if delivery.status not in {"pending", "ready"}:
        raise ValueError("delivery authorization requires a not-yet-executed delivery node")
    ancestor_ids: set[str] = set()
    frontier = list(delivery.dependencies)
    while frontier:
        node_id = frontier.pop()
        if node_id in ancestor_ids:
            continue
        ancestor = nodes.get(node_id)
        if ancestor is None:
            raise ValueError("delivery authorization has an unknown upstream dependency")
        ancestor_ids.add(node_id)
        frontier.extend(ancestor.dependencies)
    if any(nodes[node_id].status != "completed" for node_id in ancestor_ids):
        raise ValueError("delivery authorization requires every transitive ancestor to be completed")
    ancestor_artifact_ids: set[str] = set()
    for node_id in sorted(ancestor_ids):
        ancestor_artifact_ids.update(
            validate_node_execution_chain(
                state,
                node_id,
                require_completed_node=True,
                require_active_decisions=True,
            )
        )
    input_artifact_ids = set(delivery.input_bindings.values())
    registered_artifacts = {item.id: item for item in state.artifacts}
    if not input_artifact_ids or not input_artifact_ids <= set(registered_artifacts):
        raise ValueError("delivery authorization requires exact registered input artifact bindings")
    active_decisions = {
        item.artifact_id: item for item in state.scientific_decisions if item.active_evidence
    }
    if not input_artifact_ids <= set(active_decisions):
        raise ValueError("delivery authorization inputs lack retained scientific decisions")
    for artifact_id in input_artifact_ids:
        artifact = registered_artifacts[artifact_id]
        if artifact.producing_module_id is not None:
            producing_node_id = validate_artifact_execution_chain(state, artifact_id)
            if producing_node_id not in ancestor_ids:
                raise ValueError("delivery input was not produced by an authorized ancestor")
    covered_artifact_ids = tuple(sorted(ancestor_artifact_ids | input_artifact_ids))
    covered_node_ids = tuple(sorted(ancestor_ids))
    observed_ids = {
        item.observed_execution_receipt_id
        for item in state.artifact_reloads
        if item.artifact_id in covered_artifact_ids
    }
    reload_ids = {
        item.id for item in state.artifact_reloads if item.artifact_id in covered_artifact_ids
    }
    review_ids = {active_decisions[item].review_id for item in covered_artifact_ids}
    basis = {
        "project_id": state.context.project_id,
        "plan_id": active_plan.id,
        "delivery_node": delivery.to_dict(),
        "covered_nodes": [nodes[item].to_dict() for item in covered_node_ids],
        "covered_artifacts": [registered_artifacts[item].to_dict() for item in covered_artifact_ids],
        "analysis_admissions": [
            item.to_dict()
            for item in sorted(state.analysis_admissions, key=lambda value: value.id)
            if item.plan_node_id in {*covered_node_ids, delivery_node_id}
        ],
        "artifact_reviews": [
            item.to_dict()
            for item in sorted(state.artifact_reviews, key=lambda value: value.id)
            if item.id in review_ids
        ],
        "active_decisions": [active_decisions[item].to_dict() for item in covered_artifact_ids],
        "observed_executions": [
            item.to_dict()
            for item in sorted(state.observed_executions, key=lambda value: value.id)
            if item.id in observed_ids
        ],
        "artifact_reloads": [
            item.to_dict()
            for item in sorted(state.artifact_reloads, key=lambda value: value.id)
            if item.id in reload_ids
        ],
        "execution_reviews": [
            item.to_dict()
            for item in sorted(state.execution_reviews, key=lambda value: value.id)
            if item.observed_execution_receipt_id in observed_ids
        ],
    }
    return DeliveryPrerequisiteScope(
        plan_id=active_plan.id,
        delivery_node_id=delivery_node_id,
        covered_node_ids=covered_node_ids,
        covered_artifact_ids=covered_artifact_ids,
        digest=digest_value(basis),
    )


def delivery_slice_digest(state: "ProjectState") -> str:
    """Digest only state that can change the validity of a delivery evidence map."""
    active_decisions = tuple(sorted((item for item in state.scientific_decisions if item.active_evidence), key=lambda item: item.id))
    active_artifact_ids = {item.artifact_id for item in active_decisions}
    observed_ids = {
        item.observed_execution_receipt_id
        for item in state.artifact_reloads
        if item.artifact_id in active_artifact_ids
    }
    reload_ids = {
        item.id for item in state.artifact_reloads if item.artifact_id in active_artifact_ids
    }
    active_plan = next((item for item in state.plans if item.id == state.active_plan_id), None)
    basis = {
        "project_id": state.context.project_id,
        "required_deliverables": list(state.context.required_deliverables),
        "required_evidence_types": list(state.context.required_evidence_types),
        "active_plan": active_plan.to_dict() if active_plan is not None else None,
        "active_artifacts": [
            item.to_dict() for item in sorted(state.artifacts, key=lambda value: value.id) if item.id in active_artifact_ids
        ],
        "active_decisions": [item.to_dict() for item in active_decisions],
        "observed_executions": [
            item.to_dict() for item in sorted(state.observed_executions, key=lambda value: value.id) if item.id in observed_ids
        ],
        "artifact_reloads": [
            item.to_dict() for item in sorted(state.artifact_reloads, key=lambda value: value.id) if item.id in reload_ids
        ],
        "execution_reviews": [
            item.to_dict()
            for item in sorted(state.execution_reviews, key=lambda value: value.id)
            if item.observed_execution_receipt_id in observed_ids
        ],
    }
    return digest_value(basis)


def validated_delivery_publication_is_current(state: "ProjectState", delivery_node_id: str | None = None) -> bool:
    if not state.evidence_map_versions:
        return False
    if delivery_node_id is not None:
        try:
            scope = validate_delivery_prerequisites(state, delivery_node_id)
        except ValueError:
            return False
        publication = next(
            (
                item
                for item in reversed(state.evidence_map_versions)
                if item.map_kind == "delivery-authorization"
                and delivery_node_id in item.authorized_delivery_node_ids
            ),
            None,
        )
        if publication is None:
            return False
        return (
            publication.covered_plan_id == scope.plan_id
            and delivery_node_id in publication.authorized_delivery_node_ids
            and tuple(publication.covered_node_ids) == scope.covered_node_ids
            and tuple(publication.covered_artifact_ids) == scope.covered_artifact_ids
            and publication.delivery_scope_digest == scope.digest
        )
    publication = state.evidence_map_versions[-1]
    return (
        publication.map_kind == "validated-delivery"
        and publication.delivery_slice_digest == delivery_slice_digest(state)
        and set(publication.active_artifact_ids)
        == {item.artifact_id for item in state.scientific_decisions if item.active_evidence}
    )
