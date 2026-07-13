"""Citation-coverage auditing for empirical and quantitative assertions."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import date
from typing import Any


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ORIGINS = {"external_evidence", "current_study", "author_interpretation", "definition", "method_description"}
_CLAIM_KINDS = {"empirical", "quantitative", "causal", "comparative", "definitional", "procedural", "interpretive"}
_EVIDENCE_REQUIRED_KINDS = {"empirical", "quantitative", "causal", "comparative"}
_EMPIRICAL_WORDS = {
    "show", "shows", "showed", "shown", "demonstrate", "demonstrates", "demonstrated", "observe", "observes",
    "observed", "confirm", "confirms", "confirmed", "reveal", "reveals", "revealed", "indicate", "indicates",
    "indicated", "associate", "associates", "associated", "predict", "predicts", "predicted", "increase", "increased",
    "decrease", "decreased", "reduce", "reduced", "improve", "improved", "worsen", "worsened",
}
_FUZZY_QUANTIFIERS = {"most", "several", "majority", "minority", "two-thirds", "half"}
_DEFINITION_PHRASES = ("refers to", "is defined as", "we define", "for the purposes of")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z-]*")
_NUMBER_RE = re.compile(
    r"\bp\s*[<=>]\s*0?\.\d+\b|\b(?:or|hr|rr)\s*[=:]?\s*\d+(?:\.\d+)?\b|\b\d+(?:\.\d+)?%|"
    r"\b\d+(?:\.\d+)?\s+of\s+\d+\b|\b\d+(?:\.\d+)*(?:\s*(?:fold|cells?|participants?|patients?|"
    r"samples?|genes?|reads?|mg|ug|ng|mm|um|nm|ml|ul|hours?|days?|weeks?|months?|years?))?\b",
    re.IGNORECASE,
)
_SECTION_CUE_RE = re.compile(r"(?:section|chapter|figure|table|fig\.|tbl\.|step|appendix|§)\s*$", re.IGNORECASE)
_VERSION_PREFIX_RE = re.compile(r"v\s*$", re.IGNORECASE)
_REF_INTENT_RE = re.compile(r"<!--\s*ref:[^>]*-->", re.IGNORECASE)


def _exact(value: Any, fields: set[str], location: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{location} must contain exactly {sorted(fields)}")
    return value


def _identifier(value: Any, location: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not _ID_RE.fullmatch(value):
        raise ValueError(f"{location} must be a normalized safe identifier")
    return value


def _text(value: Any, location: str, maximum: int = 10000) -> str:
    if not isinstance(value, str) or value != value.strip() or not 1 <= len(value) <= maximum:
        raise ValueError(f"{location} must be normalized meaningful text")
    return value


def _ids(value: Any, location: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{location} must be a list")
    values = [_identifier(item, f"{location} item") for item in value]
    if len(set(values)) != len(values):
        raise ValueError(f"{location} contains duplicates")
    return values


def _numeric_triggers(text: str) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []
    for match in _NUMBER_RE.finditer(text):
        token = match.group(0)
        lowered = token.lower().replace(" ", "")
        qualified = any(character.isalpha() for character in token) or "%" in token or " of " in token or lowered.startswith("p")
        if not qualified:
            if re.fullmatch(r"(?:19|20)\d{2}", token):
                continue
            if re.fullmatch(r"\d+(?:\.\d+){2,}", token):
                continue
            left = text[max(0, match.start() - 24):match.start()]
            if _SECTION_CUE_RE.search(left) or ("." in token and _VERSION_PREFIX_RE.search(left)):
                continue
            if match.start() > 0 and text[match.start() - 1] == "." and re.search(r"\d+\.$", left):
                continue
        matches.append((match.start(), token))
    return matches


def _trigger_tokens(text: str) -> list[str]:
    lowered = text.lower()
    if any(phrase in lowered for phrase in _DEFINITION_PHRASES):
        return []
    matches = _numeric_triggers(text)
    for match in _WORD_RE.finditer(text):
        token = match.group(0).lower()
        if token in _EMPIRICAL_WORDS or token in _FUZZY_QUANTIFIERS:
            matches.append((match.start(), token))
    matches.sort(key=lambda item: item[0])
    return list(dict.fromkeys(token for _, token in matches))


def _issue(code: str, severity: str, subject_ids: list[str], message: str, action: str) -> dict[str, Any]:
    return {"code": code, "severity": severity, "subject_ids": sorted(set(subject_ids)), "message": message, "action": action}


def audit_assertion_citation_coverage(
    sentences: list[dict[str, Any]],
    citation_inventory: list[str],
    artifact_inventory: list[str],
    terminal_policy: str,
    audit_provenance: dict[str, Any],
) -> dict[str, Any]:
    """Find evidence-bearing assertions lacking citations or current-study artifacts."""
    if not isinstance(sentences, list) or not 1 <= len(sentences) <= 100000:
        raise ValueError("sentences must contain 1 to 100000 records")
    citations = set(_ids(citation_inventory, "citation_inventory"))
    artifacts = set(_ids(artifact_inventory, "artifact_inventory"))
    if terminal_policy not in {"advisory", "strict"}:
        raise ValueError("terminal_policy must be advisory or strict")

    sentence_fields = {
        "id", "text", "section_path", "adjacent_text", "origin", "claim_kind", "citation_ids",
        "adjacent_citation_ids", "artifact_ids", "manifest_claim_id",
    }
    results: list[dict[str, Any]] = []
    global_issues: list[dict[str, Any]] = []
    seen: set[str] = set()
    candidate_count = 0
    for index, raw in enumerate(sentences, start=1):
        sentence = _exact(raw, sentence_fields, f"sentence {index}")
        sentence_id = _identifier(sentence["id"], f"sentence {index}.id")
        if sentence_id in seen:
            raise ValueError("sentence IDs must be unique")
        seen.add(sentence_id)
        text = _text(sentence["text"], f"sentence {sentence_id}.text")
        _text(sentence["section_path"], f"sentence {sentence_id}.section_path", 1000)
        adjacent_text = sentence["adjacent_text"]
        if adjacent_text is not None and (not isinstance(adjacent_text, str) or len(adjacent_text) > 20000):
            raise ValueError(f"sentence {sentence_id}.adjacent_text must be null or bounded text")
        origin, claim_kind = sentence["origin"], sentence["claim_kind"]
        if origin not in _ORIGINS or claim_kind not in _CLAIM_KINDS:
            raise ValueError(f"sentence {sentence_id} origin or claim_kind is unsupported")
        if (origin == "definition") != (claim_kind == "definitional"):
            raise ValueError(f"sentence {sentence_id} definition origin and definitional claim_kind must agree")
        citation_ids = _ids(sentence["citation_ids"], f"sentence {sentence_id}.citation_ids")
        adjacent_ids = _ids(sentence["adjacent_citation_ids"], f"sentence {sentence_id}.adjacent_citation_ids")
        artifact_ids = _ids(sentence["artifact_ids"], f"sentence {sentence_id}.artifact_ids")
        manifest_claim_id = sentence["manifest_claim_id"]
        if manifest_claim_id is not None:
            _identifier(manifest_claim_id, f"sentence {sentence_id}.manifest_claim_id")
        unknown_citations = sorted((set(citation_ids) | set(adjacent_ids)) - citations)
        unknown_artifacts = sorted(set(artifact_ids) - artifacts)
        tokens = _trigger_tokens(text)
        explicit_kind = claim_kind in _EVIDENCE_REQUIRED_KINDS
        candidate = explicit_kind or bool(tokens)
        if origin == "definition" or claim_kind == "definitional":
            candidate = False
        if candidate:
            candidate_count += 1
        issues: list[dict[str, Any]] = []
        if unknown_citations:
            issues.append(_issue("CITATION_BINDING_UNRESOLVED", "major", [sentence_id, *unknown_citations], "One or more citation bindings do not resolve in the supplied inventory.", "Repair citation extraction or add the missing citation records."))
        if unknown_artifacts:
            issues.append(_issue("ARTIFACT_BINDING_UNRESOLVED", "major", [sentence_id, *unknown_artifacts], "One or more current-study artifact bindings do not resolve in the supplied inventory.", "Repair result-to-sentence provenance before release."))
        marker_intent = bool(_REF_INTENT_RE.search(text) or (isinstance(adjacent_text, str) and _REF_INTENT_RE.search(adjacent_text)))
        resolved_sentence_citations = sorted(set(citation_ids) & citations)
        resolved_adjacent_citations = sorted(set(adjacent_ids) & citations)
        resolved_artifacts = sorted(set(artifact_ids) & artifacts)
        if marker_intent and not (citation_ids or adjacent_ids):
            issues.append(_issue("CITATION_INTENT_NOT_STRUCTURED", "warning", [sentence_id], "Text contains citation-marker intent but no structured citation binding; malformed or unparsed markers do not prove coverage.", "Parse and validate the marker into an inventory-backed citation binding."))

        coverage_kind = "not_required"
        covered = not candidate
        if candidate:
            if origin == "external_evidence":
                covered = bool(resolved_sentence_citations or resolved_adjacent_citations)
                coverage_kind = "sentence_citation" if resolved_sentence_citations else "adjacent_citation" if resolved_adjacent_citations else "none"
                if not covered:
                    issues.append(_issue("UNCITED_EXTERNAL_ASSERTION", "major", [sentence_id], "An external empirical, quantitative, comparative, or causal assertion lacks a resolvable sentence or adjacent-clause citation.", "Add a claim-level citation binding or remove/qualify the assertion."))
            elif origin == "current_study":
                covered = bool(resolved_artifacts)
                coverage_kind = "current_study_artifact" if covered else "none"
                if not covered:
                    issues.append(_issue("CURRENT_STUDY_ASSERTION_UNBOUND", "major", [sentence_id], "A current-study result claim lacks a provenance link to a registered analysis or experiment artifact.", "Bind the assertion to the result artifact that supports it."))
            elif origin == "author_interpretation":
                covered = bool(resolved_sentence_citations or resolved_adjacent_citations or resolved_artifacts)
                coverage_kind = "mixed_evidence" if covered else "none"
                if not covered:
                    issues.append(_issue("INTERPRETATION_EVIDENCE_UNBOUND", "warning", [sentence_id], "An evidence-bearing interpretation is not linked to literature or current-study artifacts.", "Bind the interpretation to its evidence or label it explicitly as speculation."))
            elif origin == "method_description":
                covered = True
                coverage_kind = "method_description"
                if claim_kind in {"comparative", "causal"} and not (resolved_sentence_citations or resolved_adjacent_citations or resolved_artifacts):
                    covered = False
                    coverage_kind = "none"
                    issues.append(_issue("METHOD_CLAIM_EVIDENCE_UNBOUND", "warning", [sentence_id], "A comparative or causal method statement exceeds neutral procedure description but has no evidence binding.", "Cite the external method or bind the current-study validation artifact."))

        major = any(item["severity"] == "major" for item in issues)
        gate = "blocked" if major and terminal_policy == "strict" else "review_required" if issues else "passed"
        results.append({
            "sentence_id": sentence_id,
            "manifest_claim_id": manifest_claim_id,
            "candidate": candidate,
            "trigger_terms": tokens,
            "coverage_kind": coverage_kind,
            "covered": covered and not unknown_citations and not unknown_artifacts,
            "resolved_citation_ids": sorted(set(resolved_sentence_citations + resolved_adjacent_citations)),
            "resolved_artifact_ids": resolved_artifacts,
            "issues": sorted(issues, key=lambda item: (item["severity"], item["code"], item["subject_ids"])),
            "gate": gate,
        })

    provenance = _exact(audit_provenance, {"audit_id", "audit_version", "reviewed_at", "segmentation_complete", "citation_extraction_complete", "rules_independent_from_writer"}, "audit_provenance")
    for field in ("audit_id", "audit_version"):
        _identifier(provenance[field], f"audit_provenance.{field}")
    try:
        reviewed_at = date.fromisoformat(provenance["reviewed_at"])
    except (TypeError, ValueError) as exc:
        raise ValueError("audit_provenance.reviewed_at must be a valid ISO calendar date") from exc
    if reviewed_at.isoformat() != provenance["reviewed_at"]:
        raise ValueError("audit_provenance.reviewed_at must use canonical YYYY-MM-DD form")
    for field in ("segmentation_complete", "citation_extraction_complete", "rules_independent_from_writer"):
        if not isinstance(provenance[field], bool):
            raise ValueError(f"audit_provenance.{field} must be boolean")
    provenance_gate_ids = []
    if not provenance["segmentation_complete"]:
        provenance_gate_ids.append("sentence_segmentation_incomplete")
    if not provenance["citation_extraction_complete"]:
        provenance_gate_ids.append("citation_extraction_incomplete")
    if not provenance["rules_independent_from_writer"]:
        provenance_gate_ids.append("audit_rules_not_independent")
    if provenance_gate_ids:
        global_issues.append(_issue("ASSERTION_COVERAGE_AUDIT_INCOMPLETE", "major", provenance_gate_ids, "Incomplete sentence segmentation, citation extraction, or rule independence invalidates a clean audit result.", "Complete the missing audit stage and rerun; do not interpret missing findings as evidence of coverage."))

    all_issues = global_issues + [issue for result in results for issue in result["issues"]]
    counts = Counter(issue["severity"] for issue in all_issues)
    uncovered = sum(1 for result in results if result["candidate"] and not result["covered"])
    release_safe = counts["major"] == 0 and not provenance_gate_ids
    if provenance_gate_ids or (terminal_policy == "strict" and counts["major"]):
        overall_status = "blocked"
    elif all_issues:
        overall_status = "review_required"
    else:
        overall_status = "passed"
    digest_payload = {
        "sentences": sentences, "citation_inventory": citation_inventory, "artifact_inventory": artifact_inventory,
        "terminal_policy": terminal_policy, "audit_provenance": audit_provenance,
    }
    audit_digest = hashlib.sha256(json.dumps(digest_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "audit_id": provenance["audit_id"],
        "audit_version": provenance["audit_version"],
        "audit_digest": audit_digest,
        "terminal_policy": terminal_policy,
        "sentence_count": len(results),
        "candidate_count": candidate_count,
        "uncovered_candidate_count": uncovered,
        "sentence_results": results,
        "global_issues": global_issues,
        "issue_counts": {severity: counts.get(severity, 0) for severity in ("major", "warning")},
        "provenance_gate_ids": provenance_gate_ids,
        "release_safe": release_safe,
        "overall_status": overall_status,
        "quality_gates": [
            "Manifest membership never exempts an evidence-bearing assertion from citation or artifact coverage.",
            "A citation marker is intent only; coverage requires a structured binding that resolves in the citation inventory.",
            "Current-study results bind to project artifacts rather than requiring an external citation by default.",
            "Audit extraction failures are surfaced and never converted into a false clean result.",
        ],
        "limitations": [
            "Lexical triggers are a recall aid, not semantic entailment; explicit claim_kind and origin classifications remain review inputs.",
            "The module checks evidence binding presence, while source-content support is adjudicated by claim-evidence-integrity-audit.",
        ],
    }
