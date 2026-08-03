"""Deterministic cross-module scientific quality and inference gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..kernel.artifacts import ScientificArtifact
from ..kernel.identity import digest_value, validate_identifier
from ..kernel.plans import PlanNode
from ..kernel.state import ProjectState
from ..modules.contract import ModuleManifest


SEVERITIES = frozenset({"info", "warning", "major", "fatal"})
_DIRECT_IDENTIFIER_KEYS = frozenset({"name", "participant_name", "email", "phone", "address", "mrn", "medical_record_number"})
_CAUSAL_DESIGNS = frozenset({"randomized", "randomized-controlled", "interventional", "controlled-perturbation"})


@dataclass(frozen=True)
class QualityFinding:
    id: str
    code: str
    severity: str
    subject_ids: tuple[str, ...]
    message: str
    blocks_execution: bool
    blocks_interpretation: bool
    remediation_artifact_types: tuple[str, ...]

    def __post_init__(self) -> None:
        validate_identifier(self.id, "quality_finding.id")
        if not isinstance(self.code, str) or not self.code or self.severity not in SEVERITIES:
            raise ValueError("quality finding code or severity is invalid")
        if not self.subject_ids or any(not isinstance(value, str) or not value for value in self.subject_ids):
            raise ValueError("quality finding requires subjects")
        if not isinstance(self.message, str) or len(self.message.strip()) < 12:
            raise ValueError("quality finding requires a meaningful message")
        if not isinstance(self.blocks_execution, bool) or not isinstance(self.blocks_interpretation, bool):
            raise ValueError("quality finding block flags must be boolean")
        if self.severity in {"major", "fatal"} and not self.remediation_artifact_types:
            raise ValueError("blocking quality findings require remediation artifact types")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "code": self.code,
            "severity": self.severity,
            "subject_ids": list(self.subject_ids),
            "message": self.message,
            "blocks_execution": self.blocks_execution,
            "blocks_interpretation": self.blocks_interpretation,
            "remediation_artifact_types": list(self.remediation_artifact_types),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "QualityFinding":
        values = dict(payload)
        values["subject_ids"] = tuple(values["subject_ids"])
        values["remediation_artifact_types"] = tuple(values["remediation_artifact_types"])
        return cls(**values)


def _finding(code: str, severity: str, subjects: tuple[str, ...], message: str, remediation: tuple[str, ...] = ("quality_report",), *, blocks_execution: bool | None = None) -> QualityFinding:
    ordered_subjects = tuple(sorted(set(subjects)))
    identity = digest_value({"code": code, "subjects": ordered_subjects, "message": message})[:16]
    return QualityFinding(
        id=f"finding-{code.lower().replace('_', '-')}-{identity}",
        code=code,
        severity=severity,
        subject_ids=ordered_subjects,
        message=message,
        blocks_execution=(severity == "fatal") if blocks_execution is None else blocks_execution,
        blocks_interpretation=severity in {"major", "fatal"},
        remediation_artifact_types=remediation if severity in {"major", "fatal"} else (),
    )


def _values(artifacts: tuple[ScientificArtifact, ...], attribute: str) -> dict[object, tuple[str, ...]]:
    grouped = {}
    for artifact in artifacts:
        value = getattr(artifact, attribute)
        if value is not None:
            grouped.setdefault(value, []).append(artifact.id)
    return {key: tuple(value) for key, value in grouped.items()}


def _mismatch(findings: list[QualityFinding], artifacts: tuple[ScientificArtifact, ...], attribute: str, code: str, severity: str, label: str) -> None:
    grouped = _values(artifacts, attribute)
    if len(grouped) > 1:
        findings.append(_finding(code, severity, tuple(item.id for item in artifacts), f"Input artifacts declare incompatible {label} values."))


def evaluate_project_quality(state: ProjectState, node: PlanNode, manifest: ModuleManifest) -> tuple[QualityFinding, ...]:
    """Evaluate explicit project metadata without inferring missing scientific facts."""
    by_id = {artifact.id: artifact for artifact in state.artifacts}
    artifacts = tuple(by_id[artifact_id] for artifact_id in node.input_bindings.values() if artifact_id in by_id)
    findings: list[QualityFinding] = []
    for artifact in artifacts:
        if artifact.quality_status in {"major", "fatal"}:
            findings.append(
                _finding(
                    "UPSTREAM_QUALITY_BLOCK",
                    artifact.quality_status,
                    (artifact.id,),
                    "An upstream artifact has unresolved blocking quality status.",
                    blocks_execution=True,
                )
            )
        elif artifact.quality_status == "warning":
            findings.append(_finding("UPSTREAM_QUALITY_WARNING", "warning", (artifact.id,), "An upstream artifact carries a quality warning that must remain in interpretation."))
        if artifact.experimental_unit != state.context.experimental_unit:
            findings.append(_finding("PSEUDOREPLICATION_RISK", "major", (artifact.id, state.context.project_id), "Artifact and project experimental units differ, creating a pseudoreplication risk."))
        content_keys = set(artifact.content)
        if state.context.privacy_level in {"sensitive", "restricted"} and content_keys & _DIRECT_IDENTIFIER_KEYS:
            findings.append(_finding("PRIVACY_VIOLATION", "fatal", (artifact.id,), "Sensitive project state contains fields associated with direct identifiers.", ("deidentified_record",)))
        if artifact.content.get("training_cohort_id") and artifact.content.get("training_cohort_id") == artifact.content.get("validation_cohort_id"):
            findings.append(_finding("CIRCULAR_VALIDATION", "major", (artifact.id,), "Training and validation cohort identifiers are identical."))
        if artifact.content.get("completely_confounded") is True:
            findings.append(_finding("COMPLETE_CONFOUNDING", "fatal", (artifact.id,), "The declared study design is completely confounded for the requested comparison.", ("experimental_design",)))
        if artifact.content.get("threshold_selected_on_outcome") is True:
            findings.append(_finding("OUTCOME_INFORMED_THRESHOLD", "major", (artifact.id,), "The analysis threshold was selected using the outcome being evaluated."))
        claimed_evidence = artifact.content.get("evidence_ids")
        if isinstance(claimed_evidence, tuple) and not set(claimed_evidence) <= {item.id for item in state.evidence}:
            findings.append(_finding("CLAIM_EVIDENCE_DRIFT", "major", (artifact.id,), "A claim artifact references evidence records that are absent from project state.", ("claim_set", "evidence_table")))

    _mismatch(findings, artifacts, "identifier_namespace", "IDENTIFIER_NAMESPACE_MISMATCH", "fatal", "identifier namespaces")
    _mismatch(findings, artifacts, "genome_build", "GENOME_BUILD_MISMATCH", "fatal", "genome builds")
    _mismatch(findings, artifacts, "coordinate_system", "COORDINATE_SYSTEM_MISMATCH", "fatal", "coordinate systems")
    _mismatch(findings, artifacts, "denominator", "DENOMINATOR_MISMATCH", "major", "inference denominators")
    _mismatch(findings, artifacts, "processing_level", "PROCESSING_LEVEL_MISMATCH", "major", "processing levels")
    units = {artifact.scientific_scope.get("unit") for artifact in artifacts if artifact.scientific_scope.get("unit") is not None}
    if len(units) > 1:
        findings.append(_finding("UNIT_MISMATCH", "major", tuple(item.id for item in artifacts), "Input artifacts declare incompatible measurement units."))
    digests = {}
    for artifact in artifacts:
        digests.setdefault(artifact.content_digest, []).append(artifact.id)
    for duplicate_ids in digests.values():
        if len(duplicate_ids) > 1:
            findings.append(_finding("DUPLICATED_EVIDENCE", "major", tuple(duplicate_ids), "Multiple inputs have identical content and cannot count as independent evidence."))
    targeted = {item.id: item for item in state.hypotheses if item.id in node.target_hypothesis_ids}
    for hypothesis in targeted.values():
        if hypothesis.permitted_claim_strength == "causal" and state.context.study_design not in _CAUSAL_DESIGNS:
            findings.append(_finding("UNSUPPORTED_CAUSAL_SCOPE", "major", (hypothesis.id,), "The project design does not support the hypothesis's permitted causal claim strength.", ("experimental_design", "orthogonal_validation")))
    unique = {finding.id: finding for finding in findings}
    return tuple(sorted(unique.values(), key=lambda item: (item.severity, item.code, item.id)))


def interpretation_allowed(findings: tuple[QualityFinding, ...]) -> bool:
    return not any(finding.blocks_interpretation for finding in findings)
