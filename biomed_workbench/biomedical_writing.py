"""Evidence-ordered biomedical argument planning and venue-specific prose guidance."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


PROFILE_PATH = Path(__file__).parent / "knowledge" / "biomedical_writing" / "v2026.09.03.json"
ROLE_ORDER = {
    "field-premise": 0,
    "knowledge-gap": 1,
    "discovery": 2,
    "source-context": 3,
    "mechanistic-consistency": 4,
    "orthogonal-validation": 5,
    "boundary-null": 6,
    "integration": 7,
}
LITERATURE_RELATIONS = {"supports", "contradicts", "limits", "contextualises"}
STATUS_ORDER = {"FORMAL": 0, "CANDIDATE": 1, "SENSITIVITY": 2, "DEPRECATED": 3}
_DOI = re.compile(r"^10\.\d{4,9}/\S+$", re.I)


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_biomedical_writing_profiles() -> dict[str, Any]:
    payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not payload.get("profiles"):
        raise ValueError("biomedical writing profile registry is invalid")
    return payload


def resolve_biomedical_writing_profile(target_venue: str) -> dict[str, Any]:
    registry = load_biomedical_writing_profiles()
    target = re.sub(r"[^a-z0-9]+", " ", target_venue.lower()).strip()
    for profile_id, profile in registry["profiles"].items():
        for alias in profile["aliases"]:
            normalized = re.sub(r"[^a-z0-9]+", " ", alias.lower()).strip()
            if normalized and (target == normalized or normalized in target):
                return {"profile_id": profile_id, "profile_version": registry["profile_version"], **profile}
    return {
        "profile_id": "general-biomedical",
        "profile_version": registry["profile_version"],
        "research_domain": "biomedical",
        "reader": "the declared biomedical readership",
        "abstract_moves": ["context", "gap", "approach", "principal finding", "implication"],
        "results_moves": ["question", "observation", "magnitude and uncertainty", "bounded interpretation"],
        "discussion_moves": ["principal finding", "prior evidence", "biological meaning", "limitations"],
        "language": ["use direct biological subjects", "separate observations from inferences", "preserve uncertainty"],
        "official_sources": [],
        "research_examples": [],
    }


def build_biomedical_argument(
    central_question: str,
    central_claim: str,
    study_design: str,
    evidence_items: Sequence[Mapping[str, Any]],
    literature_context: Sequence[Mapping[str, Any]],
    *,
    target_document: str = "research-article",
    target_section: str = "results",
    competing_explanations: Sequence[str] = (),
) -> dict[str, Any]:
    """Place evidence by scientific job rather than source order or significance."""
    if not all(str(value).strip() for value in (central_question, central_claim, study_design, target_document, target_section)):
        raise ValueError("question, claim, design, document, and section are required")
    findings: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    ids: set[str] = set()
    for source_index, raw in enumerate(evidence_items, start=1):
        row = dict(raw)
        identifier = str(row.get("id", "")).strip()
        role = str(row.get("evidence_role", "")).strip()
        status = str(row.get("status", "CANDIDATE")).upper()
        finding = str(row.get("finding", "")).strip()
        if not identifier or identifier in ids or role not in ROLE_ORDER or status not in STATUS_ORDER or not finding:
            raise ValueError(f"evidence item {source_index} has invalid identity, role, status, or finding")
        ids.add(identifier)
        upstream = row.get("upstream_ids", [])
        if not isinstance(upstream, list) or any(not isinstance(value, str) or not value.strip() for value in upstream):
            raise ValueError(f"evidence item {identifier} has invalid upstream_ids")
        if role not in {"field-premise", "knowledge-gap", "boundary-null"} and not str(row.get("experimental_unit", "")).strip():
            findings.append({"code": "EXPERIMENTAL_UNIT_MISSING", "severity": "major", "evidence_id": identifier})
        if status == "DEPRECATED":
            disposition = "exclude"
        elif role == "boundary-null":
            disposition = "retain-as-boundary"
        else:
            disposition = "retain"
        normalized.append({
            "id": identifier,
            "source_index": source_index,
            "evidence_role": role,
            "finding": finding,
            "evidence_type": str(row.get("evidence_type", "unspecified")).strip(),
            "status": status,
            "experimental_unit": str(row.get("experimental_unit", "")).strip(),
            "effect": row.get("effect"),
            "uncertainty": str(row.get("uncertainty", "")).strip(),
            "independent_replicates": row.get("independent_replicates"),
            "supports_claim": bool(row.get("supports_claim", False)),
            "upstream_ids": list(upstream),
            "artifact_path": str(row.get("artifact_path", "")).strip(),
            "figure_or_table": str(row.get("figure_or_table", "")).strip(),
            "disposition": disposition,
        })
    if not normalized:
        raise ValueError("at least one evidence item is required")
    unknown_upstream = sorted({value for row in normalized for value in row["upstream_ids"] if value not in ids})
    if unknown_upstream:
        raise ValueError("evidence dependencies reference unknown ids: " + ", ".join(unknown_upstream))

    literature: list[dict[str, Any]] = []
    literature_ids: set[str] = set()
    for index, raw in enumerate(literature_context, start=1):
        row = dict(raw)
        identifier = str(row.get("id", "")).strip()
        doi = str(row.get("doi", "")).strip()
        relation = str(row.get("relation", "")).strip()
        if not identifier or identifier in literature_ids or not _DOI.fullmatch(doi) or relation not in LITERATURE_RELATIONS:
            raise ValueError(f"literature row {index} requires a unique id, DOI, and supported relation")
        statement, scope = str(row.get("statement", "")).strip(), str(row.get("scope", "")).strip()
        if not statement or not scope or not bool(row.get("verified", False)):
            findings.append({"code": "LITERATURE_CONTEXT_UNVERIFIED", "severity": "major", "literature_id": identifier})
        literature_ids.add(identifier)
        literature.append({
            "id": identifier, "doi": doi, "url": str(row.get("url", f"https://doi.org/{doi}")).strip(),
            "statement": statement, "scope": scope, "relation": relation, "verified": bool(row.get("verified", False)),
        })

    section = target_section.lower().replace("_", "-")
    needs_literature = section in {"abstract", "introduction", "discussion", "rationale", "significance"} or target_document == "grant-proposal"
    if needs_literature and not literature:
        findings.append({"code": "LITERATURE_CONTEXT_MISSING", "severity": "major", "section": target_section})
    if not competing_explanations:
        findings.append({"code": "COMPETING_EXPLANATION_MISSING", "severity": "minor", "section": target_section})
    if "mechan" in central_claim.lower() and study_design.lower() not in {"genetic-perturbation", "interventional", "randomized", "causal-inference"}:
        findings.append({"code": "MECHANISTIC_CLAIM_EXCEEDS_DESIGN", "severity": "major", "claim": central_claim})

    retained = [row for row in normalized if row["disposition"] != "exclude"]
    retained_ids = {row["id"] for row in retained}
    for row in retained:
        excluded_dependencies = sorted(set(row["upstream_ids"]) - retained_ids)
        if excluded_dependencies:
            findings.append({
                "code": "DEPENDENCY_EXCLUDED",
                "severity": "major",
                "evidence_id": row["id"],
                "upstream_ids": excluded_dependencies,
            })

    # Stable topological ordering keeps every declared prerequisite upstream.
    # Among simultaneously available items, biological narrative role and
    # project status decide priority; source order is only the final tie-breaker.
    by_id = {row["id"]: row for row in retained}
    pending = set(by_id)
    emitted: set[str] = set()
    ordered: list[dict[str, Any]] = []
    while pending:
        ready = [
            by_id[identifier]
            for identifier in pending
            if set(by_id[identifier]["upstream_ids"]) <= emitted
        ]
        if not ready:
            findings.append({
                "code": "EVIDENCE_DEPENDENCY_CYCLE",
                "severity": "major",
                "evidence_ids": sorted(pending),
            })
            ready = [by_id[identifier] for identifier in pending]
        ready.sort(key=lambda row: (ROLE_ORDER[row["evidence_role"]], STATUS_ORDER[row["status"]], row["source_index"]))
        chosen = ready[0]
        ordered.append(chosen)
        emitted.add(chosen["id"])
        pending.remove(chosen["id"])
    paragraph_plan = []
    for index, row in enumerate(ordered, start=1):
        paragraph_plan.append({
            "paragraph": index,
            "job": row["evidence_role"],
            "topic_sentence_content": row["finding"],
            "evidence_ids": [row["id"]],
            "must_report": [value for value in (row["effect"], row["uncertainty"], row["experimental_unit"]) if value not in (None, "")],
            "allowed_move": "observation" if row["evidence_role"] != "integration" else "bounded synthesis",
            "transition": "advance the biological question; do not introduce the next method by name",
        })
    source_order = [row["id"] for row in normalized if row["disposition"] != "exclude"]
    scientific_order = [row["id"] for row in ordered]
    major = sum(item["severity"] == "major" for item in findings)
    result = {
        "central_question": central_question.strip(),
        "central_claim": central_claim.strip(),
        "study_design": study_design.strip(),
        "target_document": target_document,
        "target_section": target_section,
        "evidence_sequence": ordered,
        "excluded_evidence": [row for row in normalized if row["disposition"] == "exclude"],
        "literature_context": literature,
        "competing_explanations": [str(value).strip() for value in competing_explanations if str(value).strip()],
        "paragraph_plan": paragraph_plan,
        "source_order_preserved": source_order == scientific_order,
        "ordering_basis": "declared evidence dependencies, biological argument role, project status, then source order; never p value alone",
        "findings": findings,
        "major_finding_count": major,
        "ready_for_drafting": major == 0,
    }
    result["argument_digest"] = _digest(result)
    return result
