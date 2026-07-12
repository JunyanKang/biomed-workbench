"""Rule-explicit hypothesis adjudication from directional scientific evidence."""

from __future__ import annotations

from dataclasses import dataclass

from ..kernel.evidence import EvidenceRecord, independent_evidence_groups
from ..kernel.hypotheses import Hypothesis
from .quality import QualityFinding


_USABLE_QUALITY = frozenset({"passed", "warning"})
_CAUSAL_DESIGNS = frozenset({"randomized", "randomized-controlled", "interventional", "controlled-perturbation"})


@dataclass(frozen=True)
class HypothesisAssessment:
    hypothesis_id: str
    previous_status: str
    new_status: str
    supporting_ids: tuple[str, ...]
    conflicting_ids: tuple[str, ...]
    independent_support_groups: tuple[str, ...]
    missing_evidence_types: tuple[str, ...]
    alternative_explanations_to_test: tuple[str, ...]
    rationale: str

    def to_dict(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "previous_status": self.previous_status,
            "new_status": self.new_status,
            "supporting_ids": list(self.supporting_ids),
            "conflicting_ids": list(self.conflicting_ids),
            "independent_support_groups": list(self.independent_support_groups),
            "missing_evidence_types": list(self.missing_evidence_types),
            "alternative_explanations_to_test": list(self.alternative_explanations_to_test),
            "rationale": self.rationale,
        }


def assess_hypothesis(
    hypothesis: Hypothesis,
    evidence: tuple[EvidenceRecord, ...],
    findings: tuple[QualityFinding, ...],
) -> HypothesisAssessment:
    relevant = tuple(item for item in evidence if item.hypothesis_id == hypothesis.id)
    usable = tuple(item for item in relevant if item.quality_status in _USABLE_QUALITY)
    supporting = tuple(item for item in usable if item.relation == "supports")
    weakening = tuple(item for item in usable if item.relation == "weakens")
    refuting = tuple(item for item in usable if item.relation == "refutes")
    support_groups = independent_evidence_groups(supporting)
    observed_types = {item.evidence_type for item in supporting}
    missing = tuple(item for item in hypothesis.required_evidence_types if item not in observed_types)
    blocking = tuple(
        finding
        for finding in findings
        if finding.blocks_interpretation and (hypothesis.id in finding.subject_ids or not set(finding.subject_ids) & {item.id for item in evidence})
    )
    causal_unsupported = hypothesis.permitted_claim_strength == "causal" and any(item.study_design not in _CAUSAL_DESIGNS for item in supporting)

    if blocking:
        new_status = "inconclusive"
        rationale = "Blocking scientific quality findings prevent hypothesis interpretation until remediation or explicit scope revision."
    elif refuting:
        new_status = "refuted"
        rationale = "At least one usable evidence record matches a prespecified disconfirming relation, so concurrent support cannot preserve the hypothesis."
    elif weakening:
        new_status = "weakened"
        rationale = "Usable weakening evidence conflicts with the active hypothesis and requires alternative explanations or revised scope."
    elif causal_unsupported:
        new_status = "inconclusive"
        rationale = "The available evidence design is not sufficient for the hypothesis's permitted causal claim strength."
    elif not missing and len(support_groups) >= hypothesis.minimum_independent_evidence_groups:
        new_status = "supported"
        rationale = "All required evidence types and the minimum number of independent evidence groups support the prespecified observations."
    else:
        new_status = "inconclusive"
        rationale = "Available evidence does not refute the hypothesis, but required types or independent evidence groups remain insufficient."

    alternatives = () if new_status == "supported" else hypothesis.alternative_explanations
    return HypothesisAssessment(
        hypothesis_id=hypothesis.id,
        previous_status=hypothesis.status,
        new_status=new_status,
        supporting_ids=tuple(item.id for item in supporting),
        conflicting_ids=tuple(item.id for item in (*weakening, *refuting)),
        independent_support_groups=support_groups,
        missing_evidence_types=missing,
        alternative_explanations_to_test=alternatives,
        rationale=rationale,
    )
