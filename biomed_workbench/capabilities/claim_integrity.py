"""Claim-to-evidence integrity auditing for research deliverables."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from typing import Any


_CLAIM_STRENGTHS = {"descriptive", "association", "prediction", "causal"}
_EVIDENCE_TYPES = {"literature", "experiment", "clinical", "omics", "imaging", "statistical"}
_PARTIAL_POLICIES = {"forbidden", "allowed_with_qualification"}
_IDENTITY_STATUSES = {"verified_match", "identifier_not_found", "unresolved"}
_RETRIEVAL_STATUSES = {"completed", "not_found", "unreachable", "not_attempted"}
_CITATION_METHODS = {"original_source_review", "manual_source_review", "resolver_only", "none"}
_STUDY_DESIGNS = {
    "descriptive",
    "cross-sectional",
    "case-control",
    "observational-cohort",
    "systematic-review",
    "meta-analysis",
    "randomized",
    "interventional",
    "controlled-perturbation",
}
_CAUSAL_DESIGNS = {"randomized", "interventional", "controlled-perturbation"}
_RELATIONS = {"supports", "weakens", "refutes", "ambiguous", "not_assessed"}
_ADJUDICATION_STATUSES = {"completed", "inconclusive", "tool_failure"}
_REVIEW_METHODS = {"original_source_review", "manual_review", "deterministic_result_check", "not_reviewed"}
_CONSTRAINT_VERDICTS = {"violated", "not_violated", "unresolved"}
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _exact(record: Any, fields: set[str], location: str) -> dict[str, Any]:
    if not isinstance(record, dict) or set(record) != fields:
        raise ValueError(f"{location} must contain exactly {sorted(fields)}")
    return record


def _identifier(value: Any, location: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not _ID_RE.fullmatch(value):
        raise ValueError(f"{location} must be a normalized safe identifier")
    return value


def _text(value: Any, location: str, maximum: int = 4000) -> str:
    if not isinstance(value, str) or value != value.strip() or not 1 <= len(value) <= maximum:
        raise ValueError(f"{location} must be normalized meaningful text")
    return value


def _ids(value: Any, location: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValueError(f"{location} must be a {'possibly empty' if allow_empty else 'nonempty'} list")
    result = [_identifier(item, f"{location} item") for item in value]
    if len(set(result)) != len(result):
        raise ValueError(f"{location} contains duplicate identifiers")
    return result


def _enum(value: Any, allowed: set[str], location: str) -> str:
    if value not in allowed:
        raise ValueError(f"{location} has an unsupported value")
    return value


def _boolean(value: Any, location: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{location} must be boolean")
    return value


def _add_issue(issues: list[dict[str, Any]], code: str, severity: str, subjects: list[str], message: str) -> None:
    issues.append({"code": code, "severity": severity, "subject_ids": sorted(set(subjects)), "message": message})


def audit_claim_evidence_integrity(
    declared_claims: list[dict[str, Any]],
    emitted_claims: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    experiments: list[dict[str, Any]],
    analysis_artifacts: list[dict[str, Any]],
    evidence_assessments: list[dict[str, Any]],
    constraint_assessments: list[dict[str, Any]],
    audit_provenance: dict[str, Any],
) -> dict[str, Any]:
    """Audit claim emission, source review, experiment execution, and evidence direction."""
    if not isinstance(declared_claims, list) or not 1 <= len(declared_claims) <= 10000:
        raise ValueError("declared_claims must contain 1 to 10000 records")
    declared: dict[str, dict[str, Any]] = {}
    constraint_owner: dict[str, str] = {}
    for index, raw in enumerate(declared_claims, start=1):
        claim = _exact(raw, {"id", "text", "claim_strength", "intended_evidence_types", "citation_ids", "experiment_ids", "analysis_artifact_ids", "minimum_independent_supports", "negative_constraints", "partial_support_policy"}, f"declared claim {index}")
        identifier = _identifier(claim["id"], f"declared claim {index} id")
        if identifier in declared:
            raise ValueError("declared claim IDs must be unique")
        _text(claim["text"], f"declared claim {identifier} text")
        _enum(claim["claim_strength"], _CLAIM_STRENGTHS, f"declared claim {identifier} strength")
        evidence_types = claim["intended_evidence_types"]
        if not isinstance(evidence_types, list) or not evidence_types or any(value not in _EVIDENCE_TYPES for value in evidence_types) or len(set(evidence_types)) != len(evidence_types):
            raise ValueError(f"declared claim {identifier} intended evidence types are invalid")
        _ids(claim["citation_ids"], f"declared claim {identifier} citation_ids")
        _ids(claim["experiment_ids"], f"declared claim {identifier} experiment_ids")
        _ids(claim["analysis_artifact_ids"], f"declared claim {identifier} analysis_artifact_ids")
        minimum = claim["minimum_independent_supports"]
        if not isinstance(minimum, int) or isinstance(minimum, bool) or not 1 <= minimum <= 100:
            raise ValueError(f"declared claim {identifier} minimum support count is invalid")
        _enum(claim["partial_support_policy"], _PARTIAL_POLICIES, f"declared claim {identifier} partial policy")
        constraints = claim["negative_constraints"]
        if not isinstance(constraints, list):
            raise ValueError(f"declared claim {identifier} negative_constraints must be a list")
        normalized_constraints = []
        for cindex, constraint in enumerate(constraints, start=1):
            _exact(constraint, {"id", "description"}, f"constraint {cindex} on {identifier}")
            constraint_id = _identifier(constraint["id"], f"constraint {cindex} id")
            if constraint_id in constraint_owner:
                raise ValueError("negative constraint IDs must be globally unique")
            constraint_owner[constraint_id] = identifier
            _text(constraint["description"], f"constraint {constraint_id} description")
            normalized_constraints.append(dict(constraint))
        declared[identifier] = {**claim, "negative_constraints": normalized_constraints}

    citation_fields = {"id", "identity_status", "source_acquired", "metadata_verified_against_original", "claim_content_reviewed", "retrieval_status", "verification_method", "study_design", "independent_group"}
    citation_index: dict[str, dict[str, Any]] = {}
    global_issues: list[dict[str, Any]] = []
    for index, raw in enumerate(citations, start=1):
        citation = _exact(raw, citation_fields, f"citation {index}")
        identifier = _identifier(citation["id"], f"citation {index} id")
        if identifier in citation_index:
            raise ValueError("citation IDs must be unique")
        _enum(citation["identity_status"], _IDENTITY_STATUSES, f"citation {identifier} identity status")
        _boolean(citation["source_acquired"], f"citation {identifier} source_acquired")
        _boolean(citation["metadata_verified_against_original"], f"citation {identifier} metadata verification")
        _boolean(citation["claim_content_reviewed"], f"citation {identifier} content review")
        _enum(citation["retrieval_status"], _RETRIEVAL_STATUSES, f"citation {identifier} retrieval status")
        _enum(citation["verification_method"], _CITATION_METHODS, f"citation {identifier} verification method")
        _enum(citation["study_design"], _STUDY_DESIGNS, f"citation {identifier} study design")
        _identifier(citation["independent_group"], f"citation {identifier} independent group")
        if citation["metadata_verified_against_original"] and (
            not citation["source_acquired"] or citation["verification_method"] not in {"original_source_review", "manual_source_review"}
        ):
            _add_issue(global_issues, "CITATION_METADATA_PROVENANCE_CONTRADICTION", "major", [identifier], "Metadata cannot be declared verified against the original without an acquired source and an original-source review method.")
        if citation["claim_content_reviewed"] and (
            not citation["source_acquired"]
            or citation["retrieval_status"] != "completed"
            or citation["verification_method"] not in {"original_source_review", "manual_source_review"}
        ):
            _add_issue(global_issues, "CITATION_CONTENT_REVIEW_CONTRADICTION", "major", [identifier], "Claim content cannot be declared reviewed unless the source was acquired and review completed against the original.")
        if citation["retrieval_status"] == "completed" and not citation["source_acquired"]:
            _add_issue(global_issues, "CITATION_RETRIEVAL_ACQUISITION_CONTRADICTION", "major", [identifier], "Completed source retrieval requires source_acquired=true.")
        citation_index[identifier] = dict(citation)

    experiment_fields = {"id", "study_design", "independent_group", "planned_units", "negative_results", "known_limitations", "results_reviewed", "reproducibility_record"}
    experiment_index: dict[str, dict[str, Any]] = {}
    experiment_eligibility: dict[str, bool] = {}
    for index, raw in enumerate(experiments, start=1):
        experiment = _exact(raw, experiment_fields, f"experiment {index}")
        identifier = _identifier(experiment["id"], f"experiment {index} id")
        if identifier in experiment_index:
            raise ValueError("experiment IDs must be unique")
        _enum(experiment["study_design"], _STUDY_DESIGNS, f"experiment {identifier} study design")
        _identifier(experiment["independent_group"], f"experiment {identifier} independent group")
        _boolean(experiment["results_reviewed"], f"experiment {identifier} results_reviewed")
        units = experiment["planned_units"]
        if not isinstance(units, list) or not units:
            raise ValueError(f"experiment {identifier} planned_units must be nonempty")
        unit_ids = set()
        executed_with_results = 0
        for uindex, unit in enumerate(units, start=1):
            _exact(unit, {"id", "planned", "executed", "skip_reason", "result_pointer"}, f"unit {uindex} on experiment {identifier}")
            unit_id = _identifier(unit["id"], f"unit {uindex} id")
            if unit_id in unit_ids:
                raise ValueError(f"experiment {identifier} unit IDs must be unique")
            unit_ids.add(unit_id)
            _text(unit["planned"], f"unit {unit_id} planned description")
            _boolean(unit["executed"], f"unit {unit_id} executed")
            if unit["executed"]:
                if unit["skip_reason"] is not None:
                    _add_issue(global_issues, "EXECUTED_UNIT_HAS_SKIP_REASON", "major", [identifier, unit_id], "An executed unit must not carry a skip reason.")
                if not isinstance(unit["result_pointer"], str) or not unit["result_pointer"].strip():
                    _add_issue(global_issues, "EXECUTED_UNIT_MISSING_RESULT", "major", [identifier, unit_id], "An executed unit requires a nonempty result pointer.")
                else:
                    executed_with_results += 1
            else:
                if not isinstance(unit["skip_reason"], str) or not unit["skip_reason"].strip():
                    _add_issue(global_issues, "UNEXECUTED_UNIT_MISSING_REASON", "major", [identifier, unit_id], "Every planned but unexecuted unit requires a skip reason.")
                if unit["result_pointer"] is not None:
                    _add_issue(global_issues, "UNEXECUTED_UNIT_HAS_RESULT", "major", [identifier, unit_id], "An unexecuted unit must not carry a result pointer.")
        for field in ("negative_results", "known_limitations"):
            records = experiment[field]
            if not isinstance(records, list):
                raise ValueError(f"experiment {identifier} {field} must be a list, including an explicit empty list")
            seen = set()
            for rindex, record in enumerate(records, start=1):
                _exact(record, {"id", "description"}, f"{field} record {rindex} on {identifier}")
                record_id = _identifier(record["id"], f"{field} record id")
                if record_id in seen:
                    raise ValueError(f"experiment {identifier} {field} IDs must be unique")
                seen.add(record_id)
                _text(record["description"], f"{field} record description", 2000)
        reproducibility = _exact(experiment["reproducibility_record"], {"input_digest", "parameter_digest", "software_recorded", "randomization_recorded"}, f"experiment {identifier} reproducibility_record")
        for field in ("input_digest", "parameter_digest"):
            if not isinstance(reproducibility[field], str) or not re.fullmatch(r"[0-9a-f]{64}", reproducibility[field]):
                raise ValueError(f"experiment {identifier} {field} must be a SHA-256 digest")
        _boolean(reproducibility["software_recorded"], f"experiment {identifier} software_recorded")
        _boolean(reproducibility["randomization_recorded"], f"experiment {identifier} randomization_recorded")
        if not reproducibility["software_recorded"]:
            _add_issue(global_issues, "EXPERIMENT_SOFTWARE_NOT_RECORDED", "warning", [identifier], "Experiment software and versions were not recorded, limiting reproducibility.")
        if experiment["study_design"] in _CAUSAL_DESIGNS and not reproducibility["randomization_recorded"]:
            _add_issue(global_issues, "EXPERIMENT_RANDOMIZATION_NOT_RECORDED", "warning", [identifier], "A causal-design experiment lacks a recorded randomization or allocation procedure.")
        experiment_eligibility[identifier] = experiment["results_reviewed"] and executed_with_results > 0
        experiment_index[identifier] = dict(experiment)

    artifact_fields = {"id", "evidence_type", "study_design", "independent_group", "result_reviewed", "provenance_complete", "quality_status"}
    artifact_index: dict[str, dict[str, Any]] = {}
    if not isinstance(analysis_artifacts, list) or len(analysis_artifacts) > 100000:
        raise ValueError("analysis_artifacts must be a list with at most 100000 records")
    for index, raw in enumerate(analysis_artifacts, start=1):
        artifact = _exact(raw, artifact_fields, f"analysis artifact {index}")
        identifier = _identifier(artifact["id"], f"analysis artifact {index} id")
        if identifier in artifact_index:
            raise ValueError("analysis artifact IDs must be unique")
        _enum(artifact["evidence_type"], {"clinical", "omics", "imaging", "statistical"}, f"analysis artifact {identifier} evidence type")
        _enum(artifact["study_design"], _STUDY_DESIGNS, f"analysis artifact {identifier} study design")
        _identifier(artifact["independent_group"], f"analysis artifact {identifier} independent group")
        _boolean(artifact["result_reviewed"], f"analysis artifact {identifier} result_reviewed")
        _boolean(artifact["provenance_complete"], f"analysis artifact {identifier} provenance_complete")
        _enum(artifact["quality_status"], {"passed", "warning", "major", "fatal"}, f"analysis artifact {identifier} quality status")
        artifact_index[identifier] = dict(artifact)

    emitted_fields = {"id", "declared_claim_id", "text", "claim_strength", "citation_ids", "experiment_ids", "analysis_artifact_ids"}
    emitted: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(emitted_claims, start=1):
        claim = _exact(raw, emitted_fields, f"emitted claim {index}")
        identifier = _identifier(claim["id"], f"emitted claim {index} id")
        if identifier in emitted:
            raise ValueError("emitted claim IDs must be unique")
        if claim["declared_claim_id"] is not None:
            _identifier(claim["declared_claim_id"], f"emitted claim {identifier} declared_claim_id")
        _text(claim["text"], f"emitted claim {identifier} text")
        _enum(claim["claim_strength"], _CLAIM_STRENGTHS, f"emitted claim {identifier} strength")
        _ids(claim["citation_ids"], f"emitted claim {identifier} citation_ids")
        _ids(claim["experiment_ids"], f"emitted claim {identifier} experiment_ids")
        _ids(claim["analysis_artifact_ids"], f"emitted claim {identifier} analysis_artifact_ids")
        emitted[identifier] = dict(claim)

    assessment_fields = {"emitted_claim_id", "evidence_kind", "evidence_id", "relation", "adjudication_status", "review_method", "independent_from_writer", "rationale"}
    assessments_by_claim: dict[str, list[dict[str, Any]]] = defaultdict(list)
    assessment_keys = set()
    for index, raw in enumerate(evidence_assessments, start=1):
        assessment = _exact(raw, assessment_fields, f"evidence assessment {index}")
        claim_id = _identifier(assessment["emitted_claim_id"], f"assessment {index} emitted_claim_id")
        kind = _enum(assessment["evidence_kind"], {"citation", "experiment", "artifact"}, f"assessment {index} evidence_kind")
        evidence_id = _identifier(assessment["evidence_id"], f"assessment {index} evidence_id")
        key = (claim_id, kind, evidence_id)
        if key in assessment_keys:
            raise ValueError("evidence assessment claim-kind-evidence keys must be unique")
        assessment_keys.add(key)
        _enum(assessment["relation"], _RELATIONS, f"assessment {index} relation")
        _enum(assessment["adjudication_status"], _ADJUDICATION_STATUSES, f"assessment {index} adjudication_status")
        _enum(assessment["review_method"], _REVIEW_METHODS, f"assessment {index} review_method")
        _boolean(assessment["independent_from_writer"], f"assessment {index} independent_from_writer")
        _text(assessment["rationale"], f"assessment {index} rationale")
        if assessment["adjudication_status"] == "tool_failure" and assessment["relation"] != "not_assessed":
            raise ValueError("tool-failure assessments must use relation=not_assessed")
        if assessment["adjudication_status"] == "inconclusive" and assessment["relation"] not in {"ambiguous", "not_assessed"}:
            raise ValueError("inconclusive assessments cannot assert directional support")
        if assessment["review_method"] == "not_reviewed" and assessment["relation"] != "not_assessed":
            raise ValueError("not-reviewed evidence cannot assert a directional relation")
        assessments_by_claim[claim_id].append(dict(assessment))

    constraint_fields = {"emitted_claim_id", "constraint_id", "verdict", "review_method", "independent_from_writer", "rationale"}
    constraints_by_claim: dict[str, list[dict[str, Any]]] = defaultdict(list)
    constraint_keys = set()
    for index, raw in enumerate(constraint_assessments, start=1):
        assessment = _exact(raw, constraint_fields, f"constraint assessment {index}")
        claim_id = _identifier(assessment["emitted_claim_id"], f"constraint assessment {index} emitted_claim_id")
        constraint_id = _identifier(assessment["constraint_id"], f"constraint assessment {index} constraint_id")
        if (claim_id, constraint_id) in constraint_keys:
            raise ValueError("constraint assessment keys must be unique")
        constraint_keys.add((claim_id, constraint_id))
        _enum(assessment["verdict"], _CONSTRAINT_VERDICTS, f"constraint assessment {index} verdict")
        _enum(assessment["review_method"], _REVIEW_METHODS, f"constraint assessment {index} review method")
        _boolean(assessment["independent_from_writer"], f"constraint assessment {index} independent_from_writer")
        _text(assessment["rationale"], f"constraint assessment {index} rationale")
        if assessment["review_method"] == "not_reviewed" and assessment["verdict"] != "unresolved":
            raise ValueError("not-reviewed constraints must use verdict=unresolved")
        constraints_by_claim[claim_id].append(dict(assessment))

    provenance = _exact(audit_provenance, {"audit_id", "audit_version", "review_owner", "reviewed_at", "rules_independent_from_writer", "leakage_reviewed"}, "audit_provenance")
    for field in ("audit_id", "audit_version", "review_owner", "reviewed_at"):
        _text(provenance[field], f"audit_provenance.{field}", 500)
    _boolean(provenance["rules_independent_from_writer"], "audit_provenance.rules_independent_from_writer")
    _boolean(provenance["leakage_reviewed"], "audit_provenance.leakage_reviewed")
    provenance_gate_ids = []
    if not provenance["rules_independent_from_writer"]:
        provenance_gate_ids.append("audit_rules_not_independent")
    if not provenance["leakage_reviewed"]:
        provenance_gate_ids.append("audit_leakage_not_reviewed")

    claim_results = []
    mapped_declared = set()
    for claim_id, emitted_claim in emitted.items():
        issues: list[dict[str, Any]] = []
        declared_id = emitted_claim["declared_claim_id"]
        declaration = declared.get(declared_id) if declared_id is not None else None
        if declaration is None:
            _add_issue(issues, "EMITTED_CLAIM_UNDECLARED", "major", [claim_id], "The emitted claim does not resolve to a declared claim.")
        else:
            mapped_declared.add(declared_id)
            if emitted_claim["claim_strength"] == "causal" and declaration["claim_strength"] != "causal":
                _add_issue(issues, "CLAIM_STRENGTH_ESCALATION", "major", [claim_id, declared_id], "The emitted claim escalates a noncausal declaration to causal language.")
            elif emitted_claim["claim_strength"] != declaration["claim_strength"]:
                _add_issue(issues, "CLAIM_SCOPE_DRIFT", "warning", [claim_id, declared_id], "The emitted claim strength differs from the declared scope and requires explicit review.")
            if set(emitted_claim["citation_ids"]) - set(declaration["citation_ids"]):
                _add_issue(issues, "UNDECLARED_CITATION_BINDING", "major", [claim_id], "The emitted claim binds citations outside its declaration.")
            if set(emitted_claim["experiment_ids"]) - set(declaration["experiment_ids"]):
                _add_issue(issues, "UNDECLARED_EXPERIMENT_BINDING", "major", [claim_id], "The emitted claim binds experiments outside its declaration.")
            if set(emitted_claim["analysis_artifact_ids"]) - set(declaration["analysis_artifact_ids"]):
                _add_issue(issues, "UNDECLARED_ANALYSIS_BINDING", "major", [claim_id], "The emitted claim binds analysis artifacts outside its declaration.")
            if set(declaration["citation_ids"]) - set(emitted_claim["citation_ids"]):
                _add_issue(issues, "DECLARED_CITATION_NOT_BOUND", "warning", [claim_id], "One or more declared citations are absent from the emitted claim.")
            if set(declaration["experiment_ids"]) - set(emitted_claim["experiment_ids"]):
                _add_issue(issues, "DECLARED_EXPERIMENT_NOT_BOUND", "warning", [claim_id], "One or more declared experiments are absent from the emitted claim.")
            if set(declaration["analysis_artifact_ids"]) - set(emitted_claim["analysis_artifact_ids"]):
                _add_issue(issues, "DECLARED_ANALYSIS_NOT_BOUND", "warning", [claim_id], "One or more declared analysis artifacts are absent from the emitted claim.")

        referenced = {("citation", value) for value in emitted_claim["citation_ids"]} | {("experiment", value) for value in emitted_claim["experiment_ids"]}
        referenced.update(("artifact", value) for value in emitted_claim["analysis_artifact_ids"])
        supplied = {(item["evidence_kind"], item["evidence_id"]) for item in assessments_by_claim.get(claim_id, [])}
        for kind, evidence_id in sorted(referenced - supplied):
            _add_issue(issues, "EVIDENCE_ASSESSMENT_MISSING", "major", [claim_id, evidence_id], f"Referenced {kind} evidence lacks an assessment.")
        for kind, evidence_id in sorted(supplied - referenced):
            _add_issue(issues, "ASSESSMENT_NOT_BOUND_TO_CLAIM", "major", [claim_id, evidence_id], f"A {kind} assessment is not bound by the emitted claim.")

        usable_supports = []
        weakening = []
        refuting = []
        unresolved = []
        observed_types = set()
        causal_support = False
        for assessment in assessments_by_claim.get(claim_id, []):
            kind, evidence_id = assessment["evidence_kind"], assessment["evidence_id"]
            evidence = citation_index.get(evidence_id) if kind == "citation" else experiment_index.get(evidence_id) if kind == "experiment" else artifact_index.get(evidence_id)
            if evidence is None:
                _add_issue(issues, "EVIDENCE_REFERENCE_UNRESOLVED", "major", [claim_id, evidence_id], "An assessment references an unknown evidence record.")
                continue
            independently_reviewed = assessment["independent_from_writer"] and assessment["review_method"] != "not_reviewed" and assessment["adjudication_status"] == "completed"
            eligible = independently_reviewed
            if kind == "citation":
                eligible = eligible and evidence["identity_status"] == "verified_match" and evidence["claim_content_reviewed"] and evidence["retrieval_status"] == "completed"
                group = evidence["independent_group"]
                design = evidence["study_design"]
                observed_type = "literature"
                if assessment["relation"] == "supports" and evidence["identity_status"] != "verified_match":
                    _add_issue(issues, "UNRESOLVED_CITATION_CANNOT_SUPPORT", "major", [claim_id, evidence_id], "An unresolved or identifier-not-found citation cannot support a scientific claim.")
                if assessment["relation"] == "supports" and not evidence["claim_content_reviewed"]:
                    _add_issue(issues, "UNREAD_SOURCE_CANNOT_SUPPORT", "major", [claim_id, evidence_id], "Citation identity or metadata alone cannot establish claim support without original content review.")
            elif kind == "experiment":
                eligible = eligible and experiment_eligibility[evidence_id]
                group = evidence["independent_group"]
                design = evidence["study_design"]
                observed_type = "experiment"
                if assessment["relation"] == "supports" and not experiment_eligibility[evidence_id]:
                    _add_issue(issues, "UNEXECUTED_EXPERIMENT_CANNOT_SUPPORT", "major", [claim_id, evidence_id], "An unreviewed or fully skipped experiment cannot support a scientific claim.")
            else:
                eligible = eligible and evidence["result_reviewed"] and evidence["provenance_complete"] and evidence["quality_status"] in {"passed", "warning"}
                group = evidence["independent_group"]
                design = evidence["study_design"]
                observed_type = evidence["evidence_type"]
                if assessment["relation"] == "supports" and not evidence["result_reviewed"]:
                    _add_issue(issues, "UNREVIEWED_ANALYSIS_CANNOT_SUPPORT", "major", [claim_id, evidence_id], "An analysis artifact cannot support a claim before its result is reviewed.")
                if assessment["relation"] == "supports" and not evidence["provenance_complete"]:
                    _add_issue(issues, "INCOMPLETE_ANALYSIS_PROVENANCE", "major", [claim_id, evidence_id], "An analysis artifact with incomplete provenance cannot support a claim.")
                if assessment["relation"] == "supports" and evidence["quality_status"] in {"major", "fatal"}:
                    _add_issue(issues, "BLOCKED_ANALYSIS_CANNOT_SUPPORT", "major", [claim_id, evidence_id], "An analysis artifact with blocking quality status cannot support a claim.")
            if assessment["adjudication_status"] == "tool_failure":
                _add_issue(issues, "EVIDENCE_AUDIT_TOOL_FAILURE", "warning", [claim_id, evidence_id], "Evidence assessment failed operationally and remains unresolved; it is not a negative scientific result.")
            if assessment["relation"] == "supports" and eligible:
                usable_supports.append((evidence_id, group, observed_type, design))
                observed_types.add(observed_type)
                causal_support = causal_support or design in _CAUSAL_DESIGNS
            elif assessment["relation"] == "weakens" and eligible:
                weakening.append(evidence_id)
            elif assessment["relation"] == "refutes" and eligible:
                refuting.append(evidence_id)
            elif assessment["relation"] in {"ambiguous", "not_assessed"} or not eligible:
                unresolved.append(evidence_id)

        violated_constraints = []
        unresolved_constraints = []
        expected_constraints = {item["id"] for item in declaration["negative_constraints"]} if declaration else set()
        observed_constraints = {item["constraint_id"] for item in constraints_by_claim.get(claim_id, [])}
        for missing in sorted(expected_constraints - observed_constraints):
            _add_issue(issues, "NEGATIVE_CONSTRAINT_NOT_ASSESSED", "major", [claim_id, missing], "A declared negative constraint lacks an assessment.")
        for assessment in constraints_by_claim.get(claim_id, []):
            constraint_id = assessment["constraint_id"]
            if constraint_id not in expected_constraints or constraint_owner.get(constraint_id) != declared_id:
                _add_issue(issues, "CONSTRAINT_SCOPE_UNRESOLVED", "major", [claim_id, constraint_id], "Constraint assessment does not resolve within the declared claim scope.")
                continue
            if assessment["verdict"] == "violated":
                violated_constraints.append(constraint_id)
            elif assessment["verdict"] == "unresolved" or not assessment["independent_from_writer"]:
                unresolved_constraints.append(constraint_id)
        if violated_constraints:
            _add_issue(issues, "NEGATIVE_CONSTRAINT_VIOLATED", "major", [claim_id, *violated_constraints], "The emitted claim violates one or more prespecified negative constraints.")

        independent_groups = sorted({group for _, group, _, _ in usable_supports})
        missing_types = sorted(set(declaration["intended_evidence_types"]) - observed_types) if declaration else []
        minimum_supports = declaration["minimum_independent_supports"] if declaration else 1
        causal_unsupported = emitted_claim["claim_strength"] == "causal" and not causal_support
        if causal_unsupported:
            _add_issue(issues, "CAUSAL_CLAIM_DESIGN_INSUFFICIENT", "major", [claim_id], "The emitted causal claim lacks eligible support from a causal study design.")

        if refuting:
            claim_state = "refuted"
        elif weakening or (usable_supports and (missing_types or len(independent_groups) < minimum_supports)):
            claim_state = "weakened"
        elif usable_supports and not missing_types and len(independent_groups) >= minimum_supports and not unresolved_constraints:
            claim_state = "supported"
        else:
            claim_state = "inconclusive"
        major_codes = [item["code"] for item in issues if item["severity"] == "major"]
        warning_codes = [item["code"] for item in issues if item["severity"] == "warning"]
        partial_forbidden = claim_state == "weakened" and declaration is not None and declaration["partial_support_policy"] == "forbidden"
        if claim_state == "refuted" or major_codes or partial_forbidden:
            emission_gate = "blocked"
        elif claim_state != "supported" or warning_codes or unresolved or unresolved_constraints:
            emission_gate = "review_required"
        else:
            emission_gate = "passed"
        claim_results.append({
            "emitted_claim_id": claim_id,
            "declared_claim_id": declared_id,
            "claim_state": claim_state,
            "emission_gate": emission_gate,
            "eligible_support_ids": sorted(item[0] for item in usable_supports),
            "weakening_ids": sorted(weakening),
            "refuting_ids": sorted(refuting),
            "unresolved_evidence_ids": sorted(set(unresolved)),
            "independent_support_groups": independent_groups,
            "missing_evidence_types": missing_types,
            "violated_constraint_ids": sorted(violated_constraints),
            "unresolved_constraint_ids": sorted(unresolved_constraints),
            "issues": sorted(issues, key=lambda item: (item["severity"], item["code"], item["subject_ids"])),
        })

    declared_not_emitted = sorted(set(declared) - mapped_declared)
    for identifier in declared_not_emitted:
        _add_issue(global_issues, "DECLARED_CLAIM_NOT_EMITTED", "warning", [identifier], "A declared claim was not emitted; omission should be intentional and recorded.")
    for claim_id in sorted(set(assessments_by_claim) - set(emitted)):
        _add_issue(global_issues, "ASSESSMENT_CLAIM_UNRESOLVED", "major", [claim_id], "Evidence assessments reference an unknown emitted claim.")
    for claim_id in sorted(set(constraints_by_claim) - set(emitted)):
        _add_issue(global_issues, "CONSTRAINT_CLAIM_UNRESOLVED", "major", [claim_id], "Constraint assessments reference an unknown emitted claim.")

    claim_results.sort(key=lambda item: item["emitted_claim_id"])
    all_issues = global_issues + [issue for result in claim_results for issue in result["issues"]]
    issue_counts = Counter(item["severity"] for item in all_issues)
    if provenance_gate_ids or issue_counts["major"] or any(item["emission_gate"] == "blocked" for item in claim_results):
        overall_status = "blocked"
    elif issue_counts["warning"] or declared_not_emitted or any(item["emission_gate"] == "review_required" for item in claim_results):
        overall_status = "review_required"
    else:
        overall_status = "passed"
    digest_payload = {
        "declared_claims": declared_claims,
        "emitted_claims": emitted_claims,
        "citations": citations,
        "experiments": experiments,
        "analysis_artifacts": analysis_artifacts,
        "evidence_assessments": evidence_assessments,
        "constraint_assessments": constraint_assessments,
        "audit_provenance": audit_provenance,
    }
    audit_digest = hashlib.sha256(json.dumps(digest_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "audit_id": provenance["audit_id"],
        "audit_version": provenance["audit_version"],
        "audit_digest": audit_digest,
        "declared_claim_count": len(declared),
        "emitted_claim_count": len(emitted),
        "citation_count": len(citation_index),
        "experiment_count": len(experiment_index),
        "analysis_artifact_count": len(artifact_index),
        "claim_results": claim_results,
        "declared_not_emitted_ids": declared_not_emitted,
        "global_issues": sorted(global_issues, key=lambda item: (item["severity"], item["code"], item["subject_ids"])),
        "issue_counts": {severity: issue_counts.get(severity, 0) for severity in ("major", "warning")},
        "provenance_gate_ids": provenance_gate_ids,
        "overall_status": overall_status,
        "quality_gates": [
            "Citation identity or metadata resolution alone never establishes claim support; original content must be reviewed.",
            "Retrieval failure, resolver outage, and audit-tool failure remain unresolved and are never converted into negative scientific evidence.",
            "Planned but unexecuted experiment units require reasons, and fully skipped or unreviewed experiments cannot support claims.",
            "Refuting evidence and prespecified negative-constraint violations take precedence over concurrent support.",
            "Causal claims require eligible support from causal study designs; observational support cannot silently escalate claim strength.",
        ],
        "limitations": [
            "The module audits supplied adjudications and provenance records; it does not itself read papers, inspect raw experiment files, or infer semantic entailment.",
            "Independence and leakage fields are declarations that require governance outside this deterministic reducer.",
        ],
    }
