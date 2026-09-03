"""Result-first scientific review self-correction for biomedical artifacts."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from biomed_workbench.biomedical_writing import build_biomedical_argument
from biomed_workbench.domain_context import validate_domain_context


_CAUSAL = re.compile(r"\b(caus(?:e|es|ed|al|ally)|drives?|determines?|mechanis(?:m|tic)|proves?)\b|导致|驱动|决定|机制|证明", re.IGNORECASE)
_AUDIT_LANGUAGE = re.compile(r"\b(registry|digest|hash|sha-?256|gate|renderer|state machine|artifact index|audit)\b|注册表|校验值|门禁|渲染器|状态机|审计", re.IGNORECASE)
_CAUSAL_DESIGNS = {"randomized", "interventional", "genetic-perturbation", "causal-inference"}
_ACTIONS = {"retain", "retain-with-limit", "rerun", "switch-method", "acquire-data", "revise-hypothesis", "exclude", "stop"}


def self_correct_scientific_review(
    question: str,
    hypothesis: str,
    study_design: str,
    statistical_unit: str,
    observations: list[dict[str, Any]],
    draft_review: dict[str, str],
    proposed_action: str,
    alternative_explanations: list[str] | None = None,
    domain_context: dict[str, Any] | None = None,
    literature_context: list[dict[str, Any]] | None = None,
    narrative_evidence: list[dict[str, Any]] | None = None,
    target_document: str = "research-article",
    target_section: str = "results",
) -> dict[str, Any]:
    """Find scientific-logic defects and return a corrected result-first review brief."""
    question, hypothesis = question.strip(), hypothesis.strip()
    design, unit = study_design.strip().lower(), statistical_unit.strip()
    if not question or not hypothesis or not design or not unit:
        raise ValueError("question, hypothesis, study_design, and statistical_unit are required")
    if proposed_action not in _ACTIONS:
        raise ValueError("proposed_action is unsupported")
    domain_profile = validate_domain_context(domain_context) if domain_context is not None else None
    alternatives = [] if alternative_explanations is None else alternative_explanations
    if not isinstance(alternatives, list) or len(alternatives) > 10:
        raise ValueError("alternative_explanations must be a list of at most 10 items")
    alternatives = [str(value).strip() for value in alternatives]
    if any(not value for value in alternatives):
        raise ValueError("alternative explanations must be nonempty")
    if not alternatives and domain_profile is not None:
        alternatives = list(domain_profile["competing_explanations"])
    if (literature_context is None) != (narrative_evidence is None):
        raise ValueError("literature_context and narrative_evidence must be supplied together")
    required_sections = {"methods", "results", "conclusion", "limitations", "next_step"}
    if not isinstance(draft_review, dict) or set(draft_review) != required_sections:
        raise ValueError("draft_review must contain exactly methods, results, conclusion, limitations, and next_step")
    if not isinstance(observations, list) or not observations or len(observations) > 200:
        raise ValueError("observations must contain 1..200 rows")

    findings, normalized = [], []
    for index, row in enumerate(observations, start=1):
        required = {"id", "observation", "direction", "effect_size", "uncertainty", "replicates", "status"}
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError("each observation must contain exactly the seven supported fields")
        identifier = str(row["id"]).strip()
        observation = str(row["observation"]).strip()
        direction = str(row["direction"]).strip().lower()
        effect = row["effect_size"]
        uncertainty = str(row["uncertainty"]).strip()
        replicates = row["replicates"]
        status = str(row["status"]).strip().lower()
        if not identifier or not observation or direction not in {"increase", "decrease", "mixed", "null", "not-applicable"}:
            raise ValueError("observation identity, text, or direction is invalid")
        if not isinstance(replicates, int) or isinstance(replicates, bool) or replicates < 0:
            raise ValueError("replicates must be a nonnegative integer")
        if status not in {"formal", "candidate", "sensitivity", "deprecated"}:
            raise ValueError("observation status is unsupported")
        if effect is None:
            findings.append({"severity": "major", "code": "EFFECT_SIZE_MISSING", "location": identifier, "revision": "Report the observed magnitude or explicitly state why it is not estimable."})
        if not uncertainty:
            findings.append({"severity": "major", "code": "UNCERTAINTY_MISSING", "location": identifier, "revision": "Report interval, dispersion, variability, or the applicable uncertainty limitation."})
        if replicates < 2:
            findings.append({"severity": "major", "code": "REPLICATION_WEAK", "location": identifier, "revision": "Treat the result as descriptive and state the number and unit of independent replicates."})
        normalized.append({**row, "id": identifier, "observation": observation, "direction": direction, "uncertainty": uncertainty, "status": status})

    methods, results = draft_review["methods"].strip(), draft_review["results"].strip()
    conclusion = draft_review["conclusion"].strip()
    limitations, next_step = draft_review["limitations"].strip(), draft_review["next_step"].strip()
    if len(methods) > max(len(results) * 1.5, 400):
        findings.append({"severity": "major", "code": "METHODS_DOMINATE_RESULTS", "location": "draft_review", "revision": "Move implementation detail to provenance and lead with observations, magnitude and uncertainty."})
    for section, text in draft_review.items():
        if _AUDIT_LANGUAGE.search(text):
            findings.append({"severity": "minor", "code": "INTERNAL_LANGUAGE_IN_SCIENTIFIC_NARRATIVE", "location": section, "revision": "Replace implementation vocabulary with biological question, method, result, limitation and decision language."})
    if _CAUSAL.search(conclusion) and design not in _CAUSAL_DESIGNS:
        findings.append({"severity": "major", "code": "CAUSALITY_EXCEEDS_DESIGN", "location": "conclusion", "revision": "Use association or consistency language and state the perturbation required to test causality."})
    if domain_profile is not None:
        conclusion_terms = set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", conclusion.lower()))
        for forbidden in domain_profile["forbidden_inferences"]:
            forbidden_terms = set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", str(forbidden).lower()))
            informative = {term for term in forbidden_terms if len(term) > 2}
            if informative and len(informative & conclusion_terms) / len(informative) >= 0.6:
                findings.append({
                    "severity": "major",
                    "code": "DOMAIN_INFERENCE_BOUNDARY_CROSSED",
                    "location": "conclusion",
                    "revision": f"Revise the conclusion against the project-specific boundary: {forbidden}",
                })
    if not alternatives:
        findings.append({"severity": "minor", "code": "ALTERNATIVES_NOT_EXPLICIT", "location": "alternative_explanations", "revision": "Name at least one biologically plausible alternative before selecting a discriminating next step."})
    if not limitations:
        findings.append({"severity": "major", "code": "LIMITATIONS_MISSING", "location": "limitations", "revision": "State design-specific uncertainty and the strongest unsupported inference."})
    if not next_step or not re.search(r"\b(if|would|test|distinguish|versus|vs\.?|alternative)\b|如果|检验|区分|替代|相反", next_step, re.IGNORECASE):
        findings.append({"severity": "major", "code": "NEXT_STEP_NOT_DISCRIMINATING", "location": "next_step", "revision": "Define an observation that would distinguish the leading interpretation from an alternative."})
    if not any(row["direction"] in {"null", "mixed"} for row in normalized) and "null" not in limitations.lower() and "阴性" not in limitations:
        findings.append({"severity": "minor", "code": "NEGATIVE_RESULT_BOUNDARY_ABSENT", "location": "limitations", "revision": "State whether null or discordant results were observed and how they affect interpretation."})

    discordant = [row["id"] for row in normalized if row["direction"] in {"null", "mixed"}]
    if discordant and not re.search(r"\b(null|mixed|discord|no (?:change|effect|increase|decrease))\b|阴性|不一致|未见|无显著", conclusion, re.IGNORECASE):
        findings.append({"severity": "major", "code": "DISCORDANT_EVIDENCE_UNRESOLVED", "location": "conclusion", "revision": "Integrate the named null or mixed observations into the conclusion instead of narrating only concordant results."})

    severity_counts = Counter(item["severity"] for item in findings)
    blocking = severity_counts["major"] > 0
    action = proposed_action
    if blocking and proposed_action == "retain":
        action = "retain-with-limit" if all(item["code"] not in {"CAUSALITY_EXCEEDS_DESIGN", "EFFECT_SIZE_MISSING", "UNCERTAINTY_MISSING"} for item in findings) else "rerun"
    causal_overclaim = any(item["code"] == "CAUSALITY_EXCEEDS_DESIGN" for item in findings)
    if causal_overclaim:
        corrected_interpretation = (
            f"The reported observations are consistent with the stated hypothesis, but the declared {design} design "
            "does not establish causality or a molecular mechanism."
        )
    elif discordant and any(item["code"] == "DISCORDANT_EVIDENCE_UNRESOLVED" for item in findings):
        corrected_interpretation = (
            f"The observations provide mixed support for the stated hypothesis; null or discordant results "
            f"({', '.join(discordant)}) prevent an unqualified conclusion."
        )
    else:
        corrected_interpretation = conclusion

    corrected_limitations = limitations
    if not corrected_limitations:
        corrected_limitations = (
            f"The {design} design and the declared independent-replication structure limit causal and mechanistic inference; "
            "unobserved or incompletely measured null and discordant results remain possible."
        )
    corrected_next_step = next_step
    if any(item["code"] == "NEXT_STEP_NOT_DISCRIMINATING" for item in findings):
        if domain_profile is not None and domain_profile["discriminating_observations"]:
            corrected_next_step = str(domain_profile["discriminating_observations"][0])
        else:
            comparator = alternatives[0] if alternatives else "a biologically plausible alternative explanation"
            corrected_next_step = (
                "Use a hypothesis-directed perturbation with an appropriate negative control and the same prespecified endpoint. "
                f"A selective response would support the leading hypothesis, whereas a null or nonselective response would favor {comparator}."
            )

    support_assessment = "not promotable"
    if not any(item["severity"] == "major" for item in findings):
        support_assessment = "bounded support" if discordant else "supported within the declared design"
    corrected = {
        "question": question,
        "hypothesis": hypothesis,
        "study_design": design,
        "statistical_unit": unit,
        "observations": normalized,
        "result_first_summary": [
            f"{row['id']}: {row['observation']} (effect={row['effect_size']}; uncertainty={row['uncertainty'] or 'not reported'}; independent replicates={row['replicates']}; status={row['status']})."
            for row in normalized
        ],
        "interpretation": corrected_interpretation,
        "limitations": corrected_limitations,
        "alternative_explanations": alternatives,
        "discordant_observation_ids": discordant,
        "support_assessment": support_assessment,
        "discriminating_next_step": corrected_next_step,
        "recommended_action": action,
        "unresolved_major_codes": [item["code"] for item in findings if item["severity"] == "major"],
    }
    if domain_profile is not None:
        corrected["domain_context"] = {
            "profile_id": domain_profile["profile_id"],
            "version": domain_profile["version"],
            "profile_digest": domain_profile["profile_digest"],
            "organism": domain_profile["organism"],
            "tissue_or_system": domain_profile["tissue_or_system"],
            "scientific_review_required": True,
        }
    scientific_argument = {}
    if narrative_evidence is not None and literature_context is not None:
        scientific_argument = build_biomedical_argument(
            central_question=question,
            central_claim=corrected_interpretation,
            study_design=design,
            evidence_items=narrative_evidence,
            literature_context=literature_context,
            target_document=target_document,
            target_section=target_section,
            competing_explanations=alternatives,
        )
        for item in scientific_argument["findings"]:
            findings.append({
                "severity": item["severity"],
                "code": f"ARGUMENT_{item['code']}",
                "location": item.get("evidence_id") or item.get("literature_id") or target_section,
                "revision": "Resolve this scientific-argument finding before drafting or delivery.",
            })
        severity_counts = Counter(item["severity"] for item in findings)
        corrected["unresolved_major_codes"] = [item["code"] for item in findings if item["severity"] == "major"]
        if severity_counts["major"] and corrected["recommended_action"] == "retain":
            corrected["recommended_action"] = "retain-with-limit"
    return {
        "passed": not findings,
        "requires_revision": bool(findings),
        "finding_counts": dict(sorted(severity_counts.items())),
        "findings": findings,
        "corrected_review_brief": corrected,
        "review_display_order": ["result_first_summary", "interpretation", "limitations", "discriminating_next_step", "recommended_action"],
        "background_provenance_fields": ["methods", "environment", "parameters", "input_digests", "artifact_lineage"],
        "scientific_argument": scientific_argument,
        "ready_for_writing": bool(scientific_argument) and scientific_argument.get("ready_for_drafting", False) and severity_counts["major"] == 0,
        "claim_boundary": "Automated self-correction detects explicit logic and reporting defects; it does not replace full-data review, field expertise, or independent scientific judgment.",
    }
