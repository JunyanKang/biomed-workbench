"""Human-readable project results backed by, but separated from, strict provenance."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..kernel.project_governance import ResultStatusLedger
    from ..kernel.state import ProjectState


PROGRESS_STEPS = (
    "PLANNED",
    "EXECUTED",
    "RELOADED",
    "SCIENTIFICALLY_REVIEWED",
    "FORMALLY_INCLUDED",
)


def _latest_statuses(ledger: "ResultStatusLedger | None") -> dict[str, str]:
    statuses: dict[str, str] = {}
    if ledger is not None:
        for event in ledger.events:
            statuses[event.artifact_id] = event.to_status
    return statuses


def _progress_for_artifact(state: "ProjectState", artifact_id: str, result_status: str) -> str:
    if result_status == "FORMAL":
        return "FORMALLY_INCLUDED"
    if any(item.artifact_id == artifact_id for item in state.artifact_reviews):
        return "SCIENTIFICALLY_REVIEWED"
    if any(item.artifact_id == artifact_id for item in state.artifact_reloads):
        return "RELOADED"
    if any(artifact_id in item.output_artifact_digests for item in state.observed_executions):
        return "EXECUTED"
    return "PLANNED"


def build_result_view(
    state: "ProjectState",
    ledger: "ResultStatusLedger | None" = None,
    *,
    include_reproducibility: bool = False,
    project_root: Path | None = None,
) -> dict[str, object]:
    """Return the thin scientific view; expose provenance only on explicit request."""
    review_by_artifact = {item.artifact_id: item for item in state.artifact_reviews}
    decision_by_artifact = {item.artifact_id: item for item in state.scientific_decisions}
    status_by_artifact = _latest_statuses(ledger)
    results: list[dict[str, object]] = []
    progress_counts = {step: 0 for step in PROGRESS_STEPS}
    for artifact in state.artifacts:
        result_status = status_by_artifact.get(artifact.id, "UNCLASSIFIED")
        progress = _progress_for_artifact(state, artifact.id, result_status)
        progress_counts[progress] += 1
        review = review_by_artifact.get(artifact.id)
        decision = decision_by_artifact.get(artifact.id)
        if review is None:
            continue
        panels = [
            {
                "panel": panel.panel_id,
                "observation_zh": panel.results_zh,
                "observation_en": panel.results_en,
                "interpretation_zh": panel.conclusion_zh,
                "interpretation_en": panel.conclusion_en,
            }
            for panel in review.panels
        ]
        item: dict[str, object] = {
            "progress": progress,
            "observation_zh": review.results_zh,
            "observation_en": review.results_en,
            "interpretation_zh": review.conclusion_zh,
            "interpretation_en": review.conclusion_en,
            "evidence_boundary_zh": list(review.limitations_zh),
            "evidence_boundary_en": list(review.limitations_en),
            "next_decision": decision.action if decision is not None else "scientific-decision-required",
            "included_in_current_story": bool(decision and decision.active_evidence),
            "experimental_unit": getattr(artifact, "experimental_unit", "not-recorded"),
            "panels": panels,
        }
        if project_root is not None and getattr(artifact, "payloads", ()):
            store = project_root.expanduser().resolve() / ".biomed-workbench" / "artifacts"
            item["evidence_links"] = [
                {
                    "label": payload.role,
                    "path": (store / payload.object_key).as_posix(),
                    "sha256": payload.sha256,
                }
                for payload in artifact.payloads
            ]
        if include_reproducibility:
            item["reproducibility"] = {
                "artifact_id": artifact.id,
                "artifact_type": artifact.artifact_type,
                "result_status": result_status,
                "review_status": review.overall_status,
                "next_plan_node_ids": list(decision.next_plan_node_ids) if decision is not None else [],
            }
        results.append(item)
    unresolved = sum(item["next_decision"] == "scientific-decision-required" for item in results)
    payload: dict[str, object] = {
        "project": state.context.project_id,
        "biological_question": state.context.scientific_question,
        "scientific_results": results,
        "progress": {"states": list(PROGRESS_STEPS), "artifact_counts": progress_counts},
        "next_decision": (
            "review the unresolved scientific results before adding another method"
            if unresolved
            else "advance only from results retained in the current scientific story"
        ),
    }
    if include_reproducibility:
        payload["reproducibility"] = {
            "project_state_digest": state.state_digest,
            "result_status_ledger_digest": ledger.digest if ledger is not None else None,
            "reviewed_result_count": len(results),
            "formal_result_count": sum(
                item.get("reproducibility", {}).get("result_status") == "FORMAL"
                for item in results
            ),
        }
    return payload
