"""Structured publication and translation audits for Codex synthesis."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any


def manuscript_audit(
    sections: dict[str, str],
    claims: list[dict[str, Any]],
    figure_count: int = 0,
    data_availability: bool = False,
    code_availability: bool = False,
) -> dict[str, Any]:
    if not isinstance(sections, dict) or not isinstance(claims, list) or figure_count < 0:
        raise ValueError("sections, claims, and figure_count are invalid")
    required = ["abstract", "introduction", "results", "discussion", "methods"]
    normalized = {str(key).strip().lower(): str(value).strip() for key, value in sections.items()}
    missing = [section for section in required if not normalized.get(section)]
    findings = []
    for section in missing:
        findings.append({"severity": "major", "code": "SECTION_MISSING", "location": section, "message": f"Required section {section} is absent or empty."})
    for index, claim in enumerate(claims, start=1):
        text = str(claim.get("claim", "")).strip()
        citations = int(claim.get("citation_count", 0))
        evidence = str(claim.get("evidence", "unspecified")).strip()
        if not text:
            findings.append({"severity": "major", "code": "CLAIM_EMPTY", "location": f"claim {index}", "message": "Claim text is empty."})
        elif citations <= 0:
            findings.append({"severity": "major", "code": "UNGROUNDED_CLAIM", "location": f"claim {index}", "message": "Claim has no linked citation or evidence record."})
        if evidence in {"", "unspecified"}:
            findings.append({"severity": "major", "code": "EVIDENCE_LEVEL_UNSPECIFIED", "location": f"claim {index}", "message": "Evidence type is not declared."})
    if figure_count == 0:
        findings.append({"severity": "minor", "code": "FIGURES_MISSING", "location": "figures", "message": "No figure is declared for the results narrative."})
    if not data_availability:
        findings.append({"severity": "major", "code": "DATA_AVAILABILITY_MISSING", "location": "availability", "message": "Data availability is not resolved."})
    if not code_availability:
        findings.append({"severity": "major", "code": "CODE_AVAILABILITY_MISSING", "location": "availability", "message": "Code availability is not resolved."})
    major_count = sum(finding["severity"] == "major" for finding in findings)
    return {
        "structure": {"required": required, "present": [section for section in required if section not in missing], "missing": missing},
        "claim_count": len(claims), "figure_count": figure_count, "findings": findings,
        "ready": major_count == 0, "major_finding_count": major_count,
        "next_gate": "scientific and editorial review" if major_count == 0 else "resolve major findings",
    }


def _canonical_doi(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    text = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", text)
    return text if re.fullmatch(r"10\.\d{4,9}/\S+", text) else None


def citation_audit(references: list[dict[str, Any]]) -> dict[str, Any]:
    required = ["authors", "title", "year", "journal"]
    rows = []
    dois = []
    for index, reference in enumerate(references, start=1):
        if not isinstance(reference, dict):
            raise ValueError("references must be objects")
        missing = [field for field in required if reference.get(field) in {None, ""}]
        doi = _canonical_doi(reference.get("doi"))
        if reference.get("doi") and doi is None:
            missing.append("valid_doi")
        if doi:
            dois.append(doi)
        rows.append({"index": index, "missing_fields": missing, "canonical_doi": doi, "complete": not missing})
    counts = Counter(dois)
    duplicates = sorted(doi for doi, count in counts.items() if count > 1)
    return {
        "reference_count": len(references), "references": rows, "duplicate_dois": duplicates,
        "complete_count": sum(row["complete"] for row in rows),
        "limitations": ["Metadata completeness does not prove that a reference exists, supports the claim, or is the intended version; external verification remains required."],
    }


def response_matrix(comments: list[dict[str, Any]]) -> dict[str, Any]:
    allowed = {"completed", "planned", "disputed", "blocked"}
    rows = []
    for index, item in enumerate(comments, start=1):
        if not isinstance(item, dict):
            raise ValueError("comments must be objects")
        status = str(item.get("status", "planned"))
        if status not in allowed:
            raise ValueError(f"unsupported response status: {status}")
        row = {
            "index": index, "reviewer": str(item.get("reviewer", "unspecified")),
            "comment": str(item.get("comment", "")).strip(), "response": str(item.get("response", "")).strip(),
            "action": str(item.get("action", "")).strip(), "status": status,
        }
        if not row["comment"] or not row["response"] or not row["action"]:
            raise ValueError("each response row requires comment, response, and action")
        rows.append(row)
    return {
        "comment_count": len(rows), "rows": rows, "status_counts": dict(sorted(Counter(row["status"] for row in rows).items())),
        "unresolved_indices": [row["index"] for row in rows if row["status"] != "completed"],
        "quality_gates": ["Every response must identify the manuscript or analysis change.", "Disagreement must be evidence-based and respectful.", "Line and figure references are added after pagination stabilizes."],
    }


def figure_specification(title: str, panels: list[dict[str, Any]]) -> dict[str, Any]:
    if not title.strip() or not panels:
        raise ValueError("figure title and at least one panel are required")
    labels = [str(panel.get("label", "")).strip() for panel in panels]
    if len(labels) != len(set(labels)) or any(not label for label in labels):
        raise ValueError("panel labels must be nonempty and unique")
    findings = []
    normalized = []
    for panel in panels:
        row = {key: str(panel.get(key, "")).strip() for key in ("label", "claim", "data_source", "plot")}
        missing = [key for key in ("claim", "data_source", "plot") if not row[key]]
        if missing:
            findings.append({"label": row["label"], "missing": missing})
        normalized.append(row)
    return {
        "title": title.strip(), "panels": normalized, "panel_findings": findings, "ready": not findings,
        "quality_gates": ["Panel claim is supported by the stated data source.", "Axes, units, n, statistical test, and uncertainty are explicit.", "Colors remain distinguishable and consistent across figures.", "Raster elements meet final-size resolution requirements."],
    }


def patent_disclosure_audit(
    problem: str,
    solution: str,
    essential_features: list[str],
    examples: list[str],
    alternatives: list[str],
    prior_art: list[str],
) -> dict[str, Any]:
    findings = []
    if not problem.strip() or not solution.strip():
        findings.append({"severity": "major", "code": "INVENTIVE_CONCEPT_INCOMPLETE", "message": "Problem and solution must both be explicit."})
    if not essential_features:
        findings.append({"severity": "major", "code": "ESSENTIAL_FEATURES_MISSING", "message": "Essential technical features are not identified."})
    if not examples:
        findings.append({"severity": "major", "code": "ENABLEMENT_EXAMPLES_MISSING", "message": "No enabling example is supplied."})
    if not alternatives:
        findings.append({"severity": "minor", "code": "ALTERNATIVES_MISSING", "message": "No alternative embodiment is supplied."})
    if not prior_art:
        findings.append({"severity": "major", "code": "PRIOR_ART_SEARCH_MISSING", "message": "No prior-art evidence is recorded."})
    return {
        "problem": problem.strip(), "solution": solution.strip(), "essential_features": essential_features,
        "example_count": len(examples), "alternative_count": len(alternatives), "prior_art_count": len(prior_art),
        "findings": findings, "ready_for_claim_drafting": not any(item["severity"] == "major" for item in findings),
        "limitations": ["This research disclosure audit is not legal advice, a patentability opinion, freedom-to-operate analysis, or jurisdiction-specific filing guidance."],
    }
