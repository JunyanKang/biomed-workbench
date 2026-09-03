"""Select a minimal biological story from reviewed panel contributions."""

from __future__ import annotations

import re
from typing import Mapping, Sequence


STORY_ROLES = (
    "discovery",
    "source-or-context",
    "mechanistic-consistency",
    "orthogonal-validation",
    "boundary-or-null",
    "integration",
)


def _key(text: object) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(text).lower())


def build_scientific_story(panels: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Retain panels by unique scientific job, never by significance alone."""
    seen_ids: set[str] = set()
    seen_contributions: set[tuple[str, str]] = set()
    retained: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    for index, panel in enumerate(panels, start=1):
        identifier = str(panel.get("id") or panel.get("label") or "").strip()
        role = str(panel.get("story_role") or "").strip()
        contribution = str(panel.get("unique_information") or panel.get("claim") or "").strip()
        evidence_type = str(panel.get("evidence_type") or "unspecified").strip()
        dependencies = panel.get("upstream_panels", [])
        if not identifier or identifier in seen_ids:
            raise ValueError(f"panel {index} requires a unique identifier")
        if role not in STORY_ROLES:
            raise ValueError(f"panel {identifier} requires one supported story_role")
        if len(contribution) < 8:
            raise ValueError(f"panel {identifier} requires a specific scientific contribution")
        if not isinstance(dependencies, list) or any(not isinstance(item, str) for item in dependencies):
            raise ValueError(f"panel {identifier} upstream_panels must be a list of panel identifiers")
        seen_ids.add(identifier)
        contribution_key = (_key(contribution), _key(evidence_type))
        if contribution_key in seen_contributions:
            excluded.append({
                "panel": identifier,
                "reason": "duplicates the scientific contribution and evidence type of an earlier panel",
            })
            continue
        seen_contributions.add(contribution_key)
        retained.append({
            "panel": identifier,
            "role": role,
            "unique_information": contribution,
            "evidence_type": evidence_type,
            "upstream_panels": list(dependencies),
            "statistical_significance_used_for_selection": False,
        })
    retained_ids = {item["panel"] for item in retained}
    missing = sorted({dep for item in retained for dep in item["upstream_panels"] if dep not in retained_ids})
    if missing:
        raise ValueError("story dependencies reference absent or excluded panels: " + ", ".join(missing))
    role_counts = {role: sum(item["role"] == role for item in retained) for role in STORY_ROLES}
    return {
        "retained_panels": retained,
        "excluded_panels": excluded,
        "role_counts": role_counts,
        "ready": bool(retained) and role_counts["discovery"] > 0 and role_counts["integration"] > 0,
        "selection_rule": "retain each panel only when it contributes a distinct biological observation, context, test, boundary, or synthesis step",
    }
