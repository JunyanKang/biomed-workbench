"""Public immutable contracts for stateful scientific research projects."""

from .artifacts import QUALITY_STATUSES, ScientificArtifact
from .context import CONSTRAINT_KINDS, PRIVACY_LEVELS, Comparison, Constraint, ProjectContext
from .evidence import EVIDENCE_RELATIONS, EvidenceRecord, add_evidence, evidence_partition, independent_evidence_groups
from .hypotheses import CLAIM_STRENGTHS, EXPECTED_DIRECTIONS, HYPOTHESIS_STATUSES, Hypothesis, add_hypothesis, attach_evidence, revise_hypothesis
from .identity import FrozenMapping, canonical_json, digest_value, freeze_mapping, redact_sensitive, thaw, validate_identifier

__all__ = [
    "CONSTRAINT_KINDS",
    "CLAIM_STRENGTHS",
    "EVIDENCE_RELATIONS",
    "EXPECTED_DIRECTIONS",
    "HYPOTHESIS_STATUSES",
    "PRIVACY_LEVELS",
    "QUALITY_STATUSES",
    "Comparison",
    "Constraint",
    "EvidenceRecord",
    "FrozenMapping",
    "ProjectContext",
    "Hypothesis",
    "ScientificArtifact",
    "canonical_json",
    "add_evidence",
    "add_hypothesis",
    "attach_evidence",
    "digest_value",
    "freeze_mapping",
    "evidence_partition",
    "independent_evidence_groups",
    "redact_sensitive",
    "revise_hypothesis",
    "thaw",
    "validate_identifier",
]
