"""Normalized, directional scientific evidence records and ledger operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .artifacts import QUALITY_STATUSES
from .identity import freeze_mapping, thaw, validate_identifier


EVIDENCE_RELATIONS = ("supports", "weakens", "refutes", "inconclusive")


def _meaningful(value: str, location: str, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise ValueError(f"{location} must be meaningful text")
    freeze_mapping({location: value.strip()})
    return value.strip()


def _limitations(values: tuple[str, ...]) -> tuple[str, ...]:
    result = tuple(_meaningful(value, "evidence.limitations", 12) for value in values)
    if len(set(result)) != len(result):
        raise ValueError("evidence limitations contain duplicates")
    return result


@dataclass(frozen=True)
class EvidenceRecord:
    id: str
    hypothesis_id: str
    artifact_id: str
    relation: str
    evidence_type: str
    independent_group: str
    study_design: str
    experimental_unit: str
    effect: Mapping[str, Any]
    uncertainty: Mapping[str, Any]
    quality_status: str
    limitations: tuple[str, ...]
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "evidence.id"))
        object.__setattr__(self, "hypothesis_id", validate_identifier(self.hypothesis_id, "evidence.hypothesis_id"))
        object.__setattr__(self, "artifact_id", validate_identifier(self.artifact_id, "evidence.artifact_id"))
        if self.relation not in EVIDENCE_RELATIONS:
            raise ValueError("evidence.relation is unsupported")
        object.__setattr__(self, "evidence_type", validate_identifier(self.evidence_type, "evidence.evidence_type"))
        object.__setattr__(self, "independent_group", validate_identifier(self.independent_group, "evidence.independent_group"))
        object.__setattr__(self, "study_design", validate_identifier(self.study_design, "evidence.study_design"))
        object.__setattr__(self, "experimental_unit", validate_identifier(self.experimental_unit, "evidence.experimental_unit"))
        if not isinstance(self.effect, Mapping) or not self.effect:
            raise ValueError("evidence.effect must be a nonempty object")
        if not isinstance(self.uncertainty, Mapping) or not self.uncertainty:
            raise ValueError("evidence.uncertainty must be a nonempty object")
        object.__setattr__(self, "effect", freeze_mapping(self.effect))
        object.__setattr__(self, "uncertainty", freeze_mapping(self.uncertainty))
        if self.quality_status not in QUALITY_STATUSES:
            raise ValueError("evidence.quality_status is unsupported")
        object.__setattr__(self, "limitations", _limitations(tuple(self.limitations)))
        object.__setattr__(self, "rationale", _meaningful(self.rationale, "evidence.rationale", 12))

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "hypothesis_id": self.hypothesis_id,
            "artifact_id": self.artifact_id,
            "relation": self.relation,
            "evidence_type": self.evidence_type,
            "independent_group": self.independent_group,
            "study_design": self.study_design,
            "experimental_unit": self.experimental_unit,
            "effect": thaw(self.effect),
            "uncertainty": thaw(self.uncertainty),
            "quality_status": self.quality_status,
            "limitations": list(self.limitations),
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceRecord":
        values = dict(payload)
        values["limitations"] = tuple(values["limitations"])
        return cls(**values)


def add_evidence(ledger: tuple[EvidenceRecord, ...], evidence: EvidenceRecord) -> tuple[EvidenceRecord, ...]:
    if not isinstance(evidence, EvidenceRecord):
        raise ValueError("evidence ledger accepts EvidenceRecord values")
    if evidence.id in {item.id for item in ledger}:
        raise ValueError(f"duplicate evidence id: {evidence.id}")
    same_source = [item for item in ledger if item.hypothesis_id == evidence.hypothesis_id and item.artifact_id == evidence.artifact_id]
    if same_source:
        raise ValueError("contradictory duplicate evidence for one hypothesis and artifact")
    return (*tuple(ledger), evidence)


def evidence_partition(records: tuple[EvidenceRecord, ...]) -> dict[str, tuple[EvidenceRecord, ...]]:
    return {relation: tuple(item for item in records if item.relation == relation) for relation in EVIDENCE_RELATIONS}


def independent_evidence_groups(records: tuple[EvidenceRecord, ...]) -> tuple[str, ...]:
    return tuple(sorted({item.independent_group for item in records}))
