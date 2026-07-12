"""Falsifiable hypotheses, revision lineage, and directional evidence links."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from .evidence import EvidenceRecord
from .identity import freeze_mapping, thaw, validate_identifier


HYPOTHESIS_STATUSES = frozenset({"proposed", "active", "supported", "weakened", "refuted", "inconclusive"})
CLAIM_STRENGTHS = frozenset({"descriptive", "associational", "predictive", "causal"})
EXPECTED_DIRECTIONS = frozenset({"increase", "decrease", "change", "no-change", "bidirectional"})


def _meaningful(value: str, location: str, minimum: int = 12) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise ValueError(f"{location} must be meaningful text")
    freeze_mapping({location: value.strip()})
    return value.strip()


def _statements(values: tuple[str, ...], location: str) -> tuple[str, ...]:
    result = tuple(_meaningful(value, location) for value in values)
    if not result or len(set(result)) != len(result):
        raise ValueError(f"{location} must be nonempty and unique")
    return result


def _ids(values: tuple[str, ...], location: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    result = tuple(validate_identifier(value, location) for value in values)
    if not allow_empty and not result:
        raise ValueError(f"{location} must not be empty")
    if len(set(result)) != len(result):
        raise ValueError(f"{location} contains duplicates")
    return result


@dataclass(frozen=True)
class Hypothesis:
    id: str
    statement: str
    biological_scope: Mapping[str, Any]
    experimental_unit: str
    comparison_id: str
    expected_direction: str
    expected_observations: tuple[str, ...]
    disconfirming_observations: tuple[str, ...]
    alternative_explanations: tuple[str, ...]
    required_evidence_types: tuple[str, ...]
    minimum_independent_evidence_groups: int
    permitted_claim_strength: str
    status: str
    supporting_evidence_ids: tuple[str, ...]
    conflicting_evidence_ids: tuple[str, ...]
    missing_evidence_types: tuple[str, ...]
    parent_hypothesis_id: str | None
    revision: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "hypothesis.id"))
        object.__setattr__(self, "statement", _meaningful(self.statement, "hypothesis.statement", 24))
        scope = freeze_mapping(self.biological_scope)
        if not scope:
            raise ValueError("hypothesis.biological_scope must not be empty")
        object.__setattr__(self, "biological_scope", scope)
        object.__setattr__(self, "experimental_unit", validate_identifier(self.experimental_unit, "hypothesis.experimental_unit"))
        object.__setattr__(self, "comparison_id", validate_identifier(self.comparison_id, "hypothesis.comparison_id"))
        if self.expected_direction not in EXPECTED_DIRECTIONS:
            raise ValueError("hypothesis.expected_direction is unsupported")
        object.__setattr__(self, "expected_observations", _statements(tuple(self.expected_observations), "hypothesis.expected_observations"))
        object.__setattr__(self, "disconfirming_observations", _statements(tuple(self.disconfirming_observations), "hypothesis.disconfirming_observations"))
        object.__setattr__(self, "alternative_explanations", _statements(tuple(self.alternative_explanations), "hypothesis.alternative_explanations"))
        required = _ids(tuple(self.required_evidence_types), "hypothesis.required_evidence_types", allow_empty=False)
        object.__setattr__(self, "required_evidence_types", required)
        if not isinstance(self.minimum_independent_evidence_groups, int) or isinstance(self.minimum_independent_evidence_groups, bool) or self.minimum_independent_evidence_groups < 1:
            raise ValueError("hypothesis.minimum_independent_evidence_groups must be positive")
        if self.permitted_claim_strength not in CLAIM_STRENGTHS:
            raise ValueError("hypothesis.permitted_claim_strength is unsupported")
        if self.status not in HYPOTHESIS_STATUSES:
            raise ValueError("hypothesis.status is unsupported")
        supporting = _ids(tuple(self.supporting_evidence_ids), "hypothesis.supporting_evidence_ids")
        conflicting = _ids(tuple(self.conflicting_evidence_ids), "hypothesis.conflicting_evidence_ids")
        if set(supporting) & set(conflicting):
            raise ValueError("supporting and conflicting evidence must remain disjoint")
        object.__setattr__(self, "supporting_evidence_ids", supporting)
        object.__setattr__(self, "conflicting_evidence_ids", conflicting)
        missing = _ids(tuple(self.missing_evidence_types), "hypothesis.missing_evidence_types")
        if not set(missing) <= set(required):
            raise ValueError("missing evidence types must be a subset of required evidence")
        object.__setattr__(self, "missing_evidence_types", missing)
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("hypothesis.revision must be positive")
        if self.parent_hypothesis_id is None:
            if self.revision != 1:
                raise ValueError("initial hypotheses must use revision 1")
        else:
            object.__setattr__(self, "parent_hypothesis_id", validate_identifier(self.parent_hypothesis_id, "hypothesis.parent_hypothesis_id"))
            if self.parent_hypothesis_id == self.id or self.revision == 1:
                raise ValueError("revised hypotheses require a distinct parent and revision greater than 1")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "statement": self.statement,
            "biological_scope": thaw(self.biological_scope),
            "experimental_unit": self.experimental_unit,
            "comparison_id": self.comparison_id,
            "expected_direction": self.expected_direction,
            "expected_observations": list(self.expected_observations),
            "disconfirming_observations": list(self.disconfirming_observations),
            "alternative_explanations": list(self.alternative_explanations),
            "required_evidence_types": list(self.required_evidence_types),
            "minimum_independent_evidence_groups": self.minimum_independent_evidence_groups,
            "permitted_claim_strength": self.permitted_claim_strength,
            "status": self.status,
            "supporting_evidence_ids": list(self.supporting_evidence_ids),
            "conflicting_evidence_ids": list(self.conflicting_evidence_ids),
            "missing_evidence_types": list(self.missing_evidence_types),
            "parent_hypothesis_id": self.parent_hypothesis_id,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Hypothesis":
        values = dict(payload)
        for field in (
            "expected_observations",
            "disconfirming_observations",
            "alternative_explanations",
            "required_evidence_types",
            "supporting_evidence_ids",
            "conflicting_evidence_ids",
            "missing_evidence_types",
        ):
            values[field] = tuple(values[field])
        return cls(**values)


def add_hypothesis(ledger: tuple[Hypothesis, ...], hypothesis: Hypothesis) -> tuple[Hypothesis, ...]:
    if not isinstance(hypothesis, Hypothesis):
        raise ValueError("hypothesis ledger accepts Hypothesis values")
    if hypothesis.id in {item.id for item in ledger}:
        raise ValueError(f"duplicate hypothesis id: {hypothesis.id}")
    if hypothesis.parent_hypothesis_id is not None and hypothesis.parent_hypothesis_id not in {item.id for item in ledger}:
        raise ValueError("hypothesis revision references an unknown parent")
    return (*tuple(ledger), hypothesis)


def revise_hypothesis(hypothesis: Hypothesis, *, new_id: str, **changes: Any) -> Hypothesis:
    if "id" in changes or "parent_hypothesis_id" in changes or "revision" in changes:
        raise ValueError("revision identity and lineage are controlled by revise_hypothesis")
    return replace(
        hypothesis,
        id=new_id,
        parent_hypothesis_id=hypothesis.id,
        revision=hypothesis.revision + 1,
        **changes,
    )


def attach_evidence(hypothesis: Hypothesis, evidence: EvidenceRecord) -> Hypothesis:
    if evidence.hypothesis_id != hypothesis.id:
        raise ValueError("evidence targets a different hypothesis")
    if evidence.id in set(hypothesis.supporting_evidence_ids) | set(hypothesis.conflicting_evidence_ids):
        raise ValueError("evidence is already linked to the hypothesis")
    supporting = hypothesis.supporting_evidence_ids
    conflicting = hypothesis.conflicting_evidence_ids
    missing = hypothesis.missing_evidence_types
    if evidence.relation == "supports":
        supporting = (*supporting, evidence.id)
        if evidence.quality_status in {"passed", "warning"}:
            missing = tuple(item for item in missing if item != evidence.evidence_type)
    elif evidence.relation in {"weakens", "refutes"}:
        conflicting = (*conflicting, evidence.id)
    return replace(
        hypothesis,
        supporting_evidence_ids=supporting,
        conflicting_evidence_ids=conflicting,
        missing_evidence_types=missing,
    )
