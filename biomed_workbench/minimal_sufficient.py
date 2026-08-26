"""Select the smallest analysis set that can change a scientific decision.

Routing answers which modules are semantically eligible.  This layer answers a
different question: which of those eligible modules should actually be run for
the current scientific question.  The default quota is one primary analysis
and one orthogonal validation per question.  Sensitivity analyses are retained
as candidates until a concrete decision-information gain is recorded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .modules.contract import ModuleManifest
from .scientific_semantics import ScientificSemanticBrief, module_semantic_concepts


PRIMARY_ROLE = "primary"
ORTHOGONAL_ROLE = "orthogonal-validation"
SENSITIVITY_ROLE = "sensitivity"


@dataclass(frozen=True)
class AnalysisChoice:
    module_id: str
    role: str
    branch_ids: tuple[str, ...]
    decision_information: str

    def to_dict(self) -> dict[str, object]:
        return {
            "module_id": self.module_id,
            "role": self.role,
            "branch_ids": list(self.branch_ids),
            "decision_information": self.decision_information,
        }


def _role(module: ModuleManifest) -> str:
    if module.scientific_semantics is None:
        return "supporting"
    return module.scientific_semantics.analysis_role


def _branch_specs(brief: ScientificSemanticBrief) -> list[tuple[str, str, str]]:
    """Prefer biological relations, then retain uncovered targets and assays."""
    branches: list[tuple[str, str, str]] = []
    for concept in brief.concepts["relations"]:
        if concept != "orthogonal-validation":
            branches.append((f"relation:{concept}", "relations", concept))

    def represented(axis: str, concept: str) -> bool:
        for _branch_id, branch_axis, branch_concept in branches:
            if branch_axis == axis and branch_concept == concept:
                return True
        return False

    for concept in brief.concepts["targets"]:
        if not represented("targets", concept):
            branches.append((f"target:{concept}", "targets", concept))
    for concept in brief.concepts["assays"]:
        if not represented("assays", concept):
            branches.append((f"assay:{concept}", "assays", concept))
    return branches


def _ranked_eligible(
    modules: Iterable[ModuleManifest],
    *,
    axis: str,
    concept: str,
    scores: Mapping[str, float],
) -> list[ModuleManifest]:
    return sorted(
        (
            module
            for module in modules
            if concept in module_semantic_concepts(module)[axis]
        ),
        key=lambda module: (-scores.get(module.id, 0.0), module.id),
    )


def select_minimal_sufficient(
    modules: Iterable[ModuleManifest],
    brief: ScientificSemanticBrief,
    *,
    scores: Mapping[str, float] | None = None,
    dependencies: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, object]:
    """Approve at most one primary and one orthogonal module per question."""
    module_values = tuple(modules)
    candidates = tuple(dict.fromkeys(module.id for module in module_values))
    by_id = {module.id: module for module in module_values}
    score_map = scores or {}
    dependency_map = {key: tuple(value) for key, value in (dependencies or {}).items()}
    branches = []
    approved_roles: dict[str, set[str]] = {}
    approved_branches: dict[str, set[str]] = {}
    withheld_reasons: dict[str, str] = {}

    for branch_id, axis, concept in _branch_specs(brief):
        eligible = _ranked_eligible(by_id.values(), axis=axis, concept=concept, scores=score_map)
        primary = next((module for module in eligible if _role(module) == PRIMARY_ROLE), None)
        orthogonal = next((module for module in eligible if _role(module) == ORTHOGONAL_ROLE), None)
        chosen: list[ModuleManifest] = []
        if primary is not None:
            chosen.append(primary)
        if orthogonal is not None and orthogonal.id not in {module.id for module in chosen}:
            chosen.append(orthogonal)
        for module in chosen:
            approved_roles.setdefault(module.id, set()).add(_role(module))
            approved_branches.setdefault(module.id, set()).add(branch_id)
        for module in eligible:
            if module.id in {item.id for item in chosen}:
                continue
            role = _role(module)
            if role == SENSITIVITY_ROLE:
                withheld_reasons[module.id] = (
                    "sensitivity analysis withheld until it replaces an existing analysis or adds declared decision information"
                )
            elif role in {PRIMARY_ROLE, ORTHOGONAL_ROLE}:
                withheld_reasons[module.id] = f"{role} quota already filled for {branch_id}"
        branches.append(
            {
                "id": branch_id,
                "axis": axis,
                "concept": concept,
                "primary_module_id": primary.id if primary is not None else None,
                "orthogonal_module_id": orthogonal.id if orthogonal is not None else None,
                "status": "approved" if primary is not None else "missing-primary-analysis",
                "eligible_module_ids": [module.id for module in eligible],
            }
        )

    # Registered integration and delivery nodes are not alternatives to a
    # scientific branch.  They remain eligible only after branch artifacts
    # have been observed and reviewed.
    for module in by_id.values():
        role = _role(module)
        if role in {"integration", "delivery"}:
            approved_roles.setdefault(module.id, set()).add(role)
            approved_branches.setdefault(module.id, set()).add("post-review")

    # Preserve manifest-required producers of an approved scientific module.
    stack = list(approved_roles)
    while stack:
        current = stack.pop()
        for upstream in dependency_map.get(current, ()):
            if upstream not in by_id or upstream in approved_roles:
                continue
            approved_roles[upstream] = {"required-upstream"}
            approved_branches[upstream] = {f"upstream-of:{current}"}
            stack.append(upstream)

    approved_ids = [module_id for module_id in candidates if module_id in approved_roles]
    withheld = []
    for module_id in candidates:
        if module_id in approved_roles:
            continue
        withheld.append(
            {
                "module_id": module_id,
                "role": _role(by_id[module_id]),
                "reason": withheld_reasons.get(
                    module_id,
                    "module is semantically related but does not fill an unoccupied primary or orthogonal decision role",
                ),
                "required_to_enter_execution": (
                    "name the analysis it replaces or record the additional decision information it will provide"
                ),
            }
        )

    choices = [
        AnalysisChoice(
            module_id=module_id,
            role=sorted(approved_roles[module_id])[0],
            branch_ids=tuple(sorted(approved_branches[module_id])),
            decision_information=(
                "primary estimate for the declared scientific question"
                if PRIMARY_ROLE in approved_roles[module_id]
                else "independent or assumption-distinct check of the primary result"
                if ORTHOGONAL_ROLE in approved_roles[module_id]
                else "required upstream evidence production"
            ),
        ).to_dict()
        for module_id in approved_ids
    ]
    return {
        "policy_version": "1.0.0",
        "default_quota": {"primary": 1, "orthogonal_validation": 1, "per_scientific_question": True},
        "approved_module_ids": approved_ids,
        "approved_choices": choices,
        "withheld_candidates": withheld,
        "branches": branches,
        "execution_gate": (
            "A new method enters execution only when it replaces a named analysis or contributes declared decision information not supplied by the approved primary and orthogonal pair."
        ),
    }


def assess_method_addition(
    *,
    proposed_module_id: str,
    replaces_module_id: str | None = None,
    decision_information_gain: str | None = None,
) -> dict[str, object]:
    """Return a deterministic admission decision for method proliferation."""
    gain = (decision_information_gain or "").strip()
    replacement = (replaces_module_id or "").strip()
    approved = bool(replacement or gain)
    return {
        "proposed_module_id": proposed_module_id,
        "approved": approved,
        "replaces_module_id": replacement or None,
        "decision_information_gain": gain or None,
        "reason": (
            "method addition has an explicit replacement or decision-information role"
            if approved
            else "method addition would increase method count without changing a declared decision"
        ),
    }
