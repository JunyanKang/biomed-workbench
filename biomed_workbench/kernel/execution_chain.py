"""Cross-event validation for observed execution, reload, review, and delivery state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .identity import digest_value

if TYPE_CHECKING:
    from .state import ProjectState


def validate_artifact_execution_chain(state: "ProjectState", artifact_id: str) -> str:
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
    if node is None or node.status != "completed":
        raise ValueError("produced artifact belongs to an unfinished plan node")
    return node.id


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


def validated_delivery_publication_is_current(state: "ProjectState") -> bool:
    if not state.evidence_map_versions:
        return False
    publication = state.evidence_map_versions[-1]
    return (
        publication.map_kind == "validated-delivery"
        and publication.delivery_slice_digest == delivery_slice_digest(state)
        and set(publication.active_artifact_ids)
        == {item.artifact_id for item in state.scientific_decisions if item.active_evidence}
    )
