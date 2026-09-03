"""Three explicit working modes that keep exploration separate from submission evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .kernel.state import ProjectState


MODES = ("EXPLORE", "FORMALIZE", "SUBMISSION")


def assess_research_mode(state: "ProjectState", mode: str) -> dict[str, object]:
    normalized = mode.upper()
    if normalized not in MODES:
        raise ValueError("mode must be EXPLORE, FORMALIZE, or SUBMISSION")
    active_plan = next((item for item in state.plans if item.id == state.active_plan_id), None)
    rules = {
        "EXPLORE": {
            "purpose": "rapid hypothesis and visualization iteration",
            "allowed_result_statuses": ["CANDIDATE", "SENSITIVITY", "DEPRECATED"],
            "required_now": ["biological question", "experimental unit", "typed inputs"],
            "formal_inclusion_allowed": False,
            "full_submission_checks": False,
        },
        "FORMALIZE": {
            "purpose": "freeze analysis units, parameters, source data, and interpretable outputs",
            "allowed_result_statuses": ["CANDIDATE", "SENSITIVITY", "FORMAL", "DEPRECATED"],
            "required_now": ["approved analysis", "observed execution", "output reload", "scientific review", "project lock"],
            "formal_inclusion_allowed": True,
            "full_submission_checks": False,
        },
        "SUBMISSION": {
            "purpose": "reproduce and visually inspect the complete publication package",
            "allowed_result_statuses": ["FORMAL", "DEPRECATED"],
            "required_now": ["active project lock", "formal source data", "figure contracts", "evidence map", "clean-room reproduction", "privacy and integrity review"],
            "formal_inclusion_allowed": True,
            "full_submission_checks": True,
        },
    }[normalized]
    blockers: list[str] = []
    if active_plan is None:
        blockers.append("no active research plan")
    if normalized in {"FORMALIZE", "SUBMISSION"} and not state.analysis_admissions:
        blockers.append("no project-specific approved analysis")
    if normalized == "SUBMISSION" and not state.evidence_map_versions:
        blockers.append("no published scientific evidence map")
    return {
        "mode": normalized,
        **rules,
        "ready": not blockers,
        "blockers": blockers,
        "user_view": "results-first",
        "background_record": "full provenance retained without appearing in the default scientific report",
    }
