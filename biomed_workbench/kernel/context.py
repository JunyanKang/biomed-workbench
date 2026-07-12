"""Immutable scientific project framing and study-design contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .identity import FrozenMapping, freeze_mapping, thaw, validate_identifier


PRIVACY_LEVELS = frozenset({"public", "controlled", "sensitive", "restricted"})
CONSTRAINT_KINDS = frozenset({"scientific", "ethical", "privacy", "time", "resource", "credential", "delivery"})


def _meaningful(value: str, location: str, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise ValueError(f"{location} must be meaningful text")
    freeze_mapping({location: value.strip()})
    return value.strip()


def _identifiers(values: tuple[str, ...], location: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    result = tuple(validate_identifier(value, location) for value in values)
    if not allow_empty and not result:
        raise ValueError(f"{location} must not be empty")
    if len(set(result)) != len(result):
        raise ValueError(f"{location} contains duplicates")
    return result


@dataclass(frozen=True)
class Comparison:
    id: str
    numerator_group: str
    denominator_group: str
    covariates: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "comparison.id"))
        object.__setattr__(self, "numerator_group", validate_identifier(self.numerator_group, "comparison.numerator_group"))
        object.__setattr__(self, "denominator_group", validate_identifier(self.denominator_group, "comparison.denominator_group"))
        object.__setattr__(self, "covariates", _identifiers(tuple(self.covariates), "comparison.covariates", allow_empty=True))
        if self.numerator_group == self.denominator_group:
            raise ValueError("comparison groups must differ")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "numerator_group": self.numerator_group,
            "denominator_group": self.denominator_group,
            "covariates": list(self.covariates),
        }


@dataclass(frozen=True)
class Constraint:
    id: str
    kind: str
    description: str
    required: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "constraint.id"))
        if self.kind not in CONSTRAINT_KINDS:
            raise ValueError("constraint.kind is unsupported")
        object.__setattr__(self, "description", _meaningful(self.description, "constraint.description", 12))
        if not isinstance(self.required, bool):
            raise ValueError("constraint.required must be boolean")

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "kind": self.kind, "description": self.description, "required": self.required}


@dataclass(frozen=True)
class ProjectContext:
    project_id: str
    objective: str
    scientific_question: str
    species: tuple[str, ...]
    biological_scope: Mapping[str, Any]
    study_design: str
    experimental_unit: str
    comparisons: tuple[Comparison, ...]
    constraints: tuple[Constraint, ...]
    required_deliverables: tuple[str, ...]
    required_evidence_types: tuple[str, ...]
    privacy_level: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", validate_identifier(self.project_id, "project_id"))
        object.__setattr__(self, "objective", _meaningful(self.objective, "objective", 12))
        object.__setattr__(self, "scientific_question", _meaningful(self.scientific_question, "scientific_question", 12))
        object.__setattr__(self, "species", _identifiers(tuple(self.species), "species"))
        object.__setattr__(self, "biological_scope", freeze_mapping(self.biological_scope))
        object.__setattr__(self, "study_design", validate_identifier(self.study_design, "study_design"))
        object.__setattr__(self, "experimental_unit", validate_identifier(self.experimental_unit, "experimental_unit"))
        comparisons = tuple(self.comparisons)
        if not comparisons or any(not isinstance(item, Comparison) for item in comparisons):
            raise ValueError("at least one valid comparison is required")
        if len({item.id for item in comparisons}) != len(comparisons):
            raise ValueError("comparison IDs must be unique")
        object.__setattr__(self, "comparisons", comparisons)
        constraints = tuple(self.constraints)
        if any(not isinstance(item, Constraint) for item in constraints) or len({item.id for item in constraints}) != len(constraints):
            raise ValueError("constraints must be valid and uniquely identified")
        object.__setattr__(self, "constraints", constraints)
        object.__setattr__(self, "required_deliverables", _identifiers(tuple(self.required_deliverables), "required_deliverables"))
        object.__setattr__(self, "required_evidence_types", _identifiers(tuple(self.required_evidence_types), "required_evidence_types"))
        if self.privacy_level not in PRIVACY_LEVELS:
            raise ValueError("privacy_level is unsupported")

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "objective": self.objective,
            "scientific_question": self.scientific_question,
            "species": list(self.species),
            "biological_scope": thaw(self.biological_scope),
            "study_design": self.study_design,
            "experimental_unit": self.experimental_unit,
            "comparisons": [item.to_dict() for item in self.comparisons],
            "constraints": [item.to_dict() for item in self.constraints],
            "required_deliverables": list(self.required_deliverables),
            "required_evidence_types": list(self.required_evidence_types),
            "privacy_level": self.privacy_level,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProjectContext":
        values = dict(payload)
        values["species"] = tuple(values["species"])
        values["comparisons"] = tuple(Comparison(**{**item, "covariates": tuple(item["covariates"])}) for item in values["comparisons"])
        values["constraints"] = tuple(Constraint(**item) for item in values["constraints"])
        values["required_deliverables"] = tuple(values["required_deliverables"])
        values["required_evidence_types"] = tuple(values["required_evidence_types"])
        return cls(**values)
