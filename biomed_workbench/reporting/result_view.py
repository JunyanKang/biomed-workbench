"""Concise, results-first project view backed by the strict project state."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..kernel.project_governance import ResultStatusLedger
    from ..kernel.state import ProjectState


def build_result_view(
    state: "ProjectState",
    ledger: "ResultStatusLedger | None" = None,
) -> dict[str, object]:
    """Expose scientific findings while leaving detailed provenance in state."""
    review_by_artifact = {item.artifact_id: item for item in state.artifact_reviews}
    decision_by_artifact = {item.artifact_id: item for item in state.scientific_decisions}
    status_by_artifact: dict[str, str] = {}
    if ledger is not None:
        for event in ledger.events:
            status_by_artifact[event.artifact_id] = event.to_status
    results = []
    for artifact in state.artifacts:
        review = review_by_artifact.get(artifact.id)
        decision = decision_by_artifact.get(artifact.id)
        if review is None:
            continue
        panels = [
            {
                "panel_id": panel.panel_id,
                "result_zh": panel.results_zh,
                "result_en": panel.results_en,
                "conclusion_zh": panel.conclusion_zh,
                "conclusion_en": panel.conclusion_en,
            }
            for panel in review.panels
        ]
        results.append({
            "artifact_id": artifact.id,
            "artifact_type": artifact.artifact_type,
            "result_status": status_by_artifact.get(artifact.id, "UNCLASSIFIED"),
            "review_status": review.overall_status,
            "results_zh": review.results_zh,
            "results_en": review.results_en,
            "conclusion_zh": review.conclusion_zh,
            "conclusion_en": review.conclusion_en,
            "limitations_zh": list(review.limitations_zh),
            "limitations_en": list(review.limitations_en),
            "decision": decision.action if decision is not None else "awaiting-decision",
            "active_evidence": decision.active_evidence if decision is not None else False,
            "next_plan_node_ids": list(decision.next_plan_node_ids) if decision is not None else [],
            "panels": panels,
        })
    formal = sum(item["result_status"] == "FORMAL" for item in results)
    unresolved = sum(item["decision"] == "awaiting-decision" for item in results)
    return {
        "project_id": state.context.project_id,
        "scientific_question": state.context.scientific_question,
        "result_count": len(results),
        "formal_result_count": formal,
        "awaiting_decision_count": unresolved,
        "results": results,
        "next_decision": (
            "review unresolved results before expanding the method set"
            if unresolved
            else "advance only from retained evidence and the active research plan"
        ),
        "provenance_reference": {
            "project_state_digest": state.state_digest,
            "result_status_ledger_digest": ledger.digest if ledger is not None else None,
        },
    }
