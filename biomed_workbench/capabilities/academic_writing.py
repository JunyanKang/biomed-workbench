"""Deterministic gates for evidence-bound academic writing and proposals."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any


_DOCUMENT_TYPES = {
    "research-article",
    "review-article",
    "thesis",
    "rebuttal",
    "grant-proposal",
}
_STRUCTURE_POLICIES = {"preserve", "allow-declared-change"}
_CLAIM_LEVELS = {
    "descriptive": 0,
    "associational": 1,
    "functional": 2,
    "mechanistic": 3,
    "causal": 4,
}
_EVIDENCE_STATUSES = {
    "evidence-backed",
    "plausible-inference",
    "hypothesis",
    "unsupported",
}

_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?%?"
)
_CITATION_PATTERNS = (
    re.compile(r"\\cite(?:t|p|alp|author|year)?\*?(?:\[[^\]]*\])?\{[^{}]+\}"),
    re.compile(r"\[(?:\s*\d+[a-z]?(?:\s*[-–,;]\s*\d+[a-z]?)*\s*)\]"),
    re.compile(
        r"\((?:[A-Z][A-Za-z'’.-]+(?:\s+(?:and|&|et\s+al\.?)\s+[A-Z][A-Za-z'’.-]+)?"
        r",?\s+\d{4}[a-z]?(?:;\s*)?)+\)"
    ),
    re.compile(r"https?://doi\.org/10\.\d{4,9}/[^\s)\]]+", re.IGNORECASE),
)
_EQUATION_PATTERNS = (
    re.compile(r"\$\$.*?\$\$", re.DOTALL),
    re.compile(r"(?<!\$)\$(?!\$).*?(?<!\$)\$(?!\$)", re.DOTALL),
    re.compile(r"\\\[.*?\\\]", re.DOTALL),
    re.compile(r"\\\(.*?\\\)", re.DOTALL),
    re.compile(r"\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\}", re.DOTALL),
)
_HEADING_RE = re.compile(r"(?m)^\s{0,3}(?:#{1,6}\s+.+|(?:abstract|introduction|results|discussion|methods|conclusion|references|specific aims|significance|innovation|approach)\s*)$", re.IGNORECASE)
_SENTENCE_RE = re.compile(r"(?<=[.!?。！？])\s+")

_STYLE_PATTERNS: tuple[tuple[str, str, str, re.Pattern[str]], ...] = (
    (
        "inflated-significance",
        "major",
        "Replace promotional significance language with the concrete scientific consequence and its evidence.",
        re.compile(
            r"\b(?:pivotal moment|paves? the way|new paradigm|revolutioni[sz]e|paramount importance|opens? new avenues|sheds? light on|groundbreaking|unprecedented|transformative breakthrough)\b|"
            r"(?:开创性|革命性|颠覆性|前所未有|至关重要的里程碑|开启了新的范式)",
            re.IGNORECASE,
        ),
    ),
    (
        "ai-vocabulary",
        "minor",
        "Use the specific scientific operation or relationship instead of generic ornamental vocabulary.",
        re.compile(
            r"\b(?:delve|underscore|intricate|tapestry|testament|pivotal|showcase|realm|seamless|foster|rich landscape)\b|"
            r"(?:深入探讨|错综复杂的图景|生动展现|有力彰显)",
            re.IGNORECASE,
        ),
    ),
    (
        "formulaic-opener",
        "minor",
        "Open with the concrete problem, observation, or gap.",
        re.compile(
            r"(?:^|(?<=[.!?。！？])\s+)(?:in recent years|with the rapid development of|despite recent advances|it is worth noting that|needless to say)\b|"
            r"(?:近年来，?|随着.{0,18}的快速发展|值得注意的是|毋庸置疑)",
            re.IGNORECASE,
        ),
    ),
    (
        "empty-intensifier",
        "minor",
        "Quantify the scope or remove the intensifier.",
        re.compile(
            r"\b(?:very|extremely|remarkably|strikingly|highly|extensive|comprehensive|thorough|numerous|a wide range of)\b|"
            r"(?:非常|极其|十分|大量的|广泛的|全面而系统的)",
            re.IGNORECASE,
        ),
    ),
    (
        "novelty-padding",
        "major",
        "State the exact difference from prior work and cite the comparison instead of asserting priority.",
        re.compile(
            r"\b(?:to the best of our knowledge|for the first time|first ever|wholly novel)\b|"
            r"(?:据我们所知|首次实现|首次发现|完全创新)",
            re.IGNORECASE,
        ),
    ),
    (
        "boilerplate-emphasis",
        "minor",
        "Let the evidence carry the emphasis.",
        re.compile(
            r"\b(?:it should be emphasized that|it is important to note that|notably|importantly)\b|"
            r"(?:需要强调的是|尤其值得注意的是|尤为重要的是)",
            re.IGNORECASE,
        ),
    ),
    (
        "vague-hedging",
        "minor",
        "Quantify the uncertainty or use an evidence-calibrated hedge.",
        re.compile(
            r"\b(?:somewhat|relatively|fairly|to some extent|may possibly|could potentially)\b|"
            r"(?:在一定程度上|相对而言|可能或许|较为明显)",
            re.IGNORECASE,
        ),
    ),
    (
        "negative-parallelism",
        "minor",
        "State the positive scientific relationship directly.",
        re.compile(r"\bnot (?:just|only)\b.{0,80}\bbut (?:also\s+)?\b|不仅.{0,80}而且", re.IGNORECASE),
    ),
    (
        "copula-avoidance",
        "minor",
        "Prefer a direct copular construction when no functional distinction is intended.",
        re.compile(r"\bserves? as\b|\brepresents? a\b|充当|作为一种", re.IGNORECASE),
    ),
)

_OVERCLAIM_RE = re.compile(
    r"\b(?:prove[sd]?|guarantee[sd]?|establish(?:es|ed)? conclusively|confirm(?:s|ed)? definitively|universally superior)\b|"
    r"(?:证明了|彻底证实|完全确立|必然导致|普遍优于)",
    re.IGNORECASE,
)
_CONNECTOR_RE = re.compile(
    r"^(?:moreover|furthermore|additionally|in addition|in particular|however|therefore|thus|此外|进一步而言|另外|然而|因此)[,，]?\s*",
    re.IGNORECASE,
)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _paragraphs(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"\n\s*\n", text.strip()) if item.strip()]


def _markers(text: str, patterns: tuple[re.Pattern[str], ...]) -> list[str]:
    spans: list[tuple[int, int, str]] = []
    for pattern in patterns:
        spans.extend((match.start(), match.end(), match.group(0)) for match in pattern.finditer(text))
    spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    accepted: list[tuple[int, int, str]] = []
    for item in spans:
        if not any(item[0] >= row[0] and item[1] <= row[1] for row in accepted):
            accepted.append(item)
    return [item[2] for item in accepted]


def _counter_delta(original: list[str], revised: list[str]) -> dict[str, list[str]]:
    before, after = Counter(original), Counter(revised)
    removed = sorted((before - after).elements())
    added = sorted((after - before).elements())
    return {"removed": removed, "added": added}


def _location(text: str, start: int) -> dict[str, int]:
    return {"line": text.count("\n", 0, start) + 1, "character": start + 1}


def _style_findings(text: str, *, proposal_mode: bool) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for code, severity, action, pattern in _STYLE_PATTERNS:
        if proposal_mode and code in {"inflated-significance", "novelty-padding"}:
            continue
        for match in pattern.finditer(text):
            findings.append(
                {
                    "code": code,
                    "severity": severity,
                    "location": _location(text, match.start()),
                    "excerpt": match.group(0),
                    "action": action,
                }
            )
    for match in re.finditer("—", text):
        findings.append(
            {
                "code": "em-dash",
                "severity": "major",
                "location": _location(text, match.start()),
                "excerpt": "—",
                "action": "Recast with a comma, colon, parentheses, or a separate sentence.",
            }
        )
    for match in _OVERCLAIM_RE.finditer(text):
        findings.append(
            {
                "code": "overclaiming-verb",
                "severity": "major",
                "location": _location(text, match.start()),
                "excerpt": match.group(0),
                "action": "Match the verb to direct evidence and the bounded study design.",
            }
        )
    sentences = [item.strip() for item in _SENTENCE_RE.split(text) if item.strip()]
    consecutive_connectors = 0
    for index, sentence in enumerate(sentences, start=1):
        words = re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", sentence)
        clause_markers = len(re.findall(r"[,;，；]", sentence)) + len(re.findall(r"\b(?:which|that|while|whereas|although|because|with)\b", sentence, re.IGNORECASE))
        if len(words) > 30 and clause_markers >= 3:
            findings.append(
                {
                    "code": "clause-stacked-sentence",
                    "severity": "minor",
                    "location": {"sentence": index},
                    "excerpt": sentence[:180],
                    "action": "Split the sentence so each sentence carries one principal idea.",
                }
            )
        if _CONNECTOR_RE.match(sentence):
            consecutive_connectors += 1
            if consecutive_connectors >= 2:
                findings.append(
                    {
                        "code": "connector-overuse",
                        "severity": "minor",
                        "location": {"sentence": index},
                        "excerpt": sentence[:120],
                        "action": "Remove the sentence-initial connector and make the logical relation explicit.",
                    }
                )
        else:
            consecutive_connectors = 0
        citation_count = len(_markers(sentence, _CITATION_PATTERNS))
        lexical_words = re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", sentence)
        if citation_count >= 4 and len(lexical_words) < 25:
            findings.append(
                {
                    "code": "citation-dumping",
                    "severity": "minor",
                    "location": {"sentence": index},
                    "excerpt": sentence[:180],
                    "action": "Retain the most relevant sources and explain what each source contributes.",
                }
            )
    return findings


def _claim_findings(claim_bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(claim_bindings, start=1):
        if not isinstance(item, dict):
            raise ValueError("claim_bindings must contain objects")
        claim_id = str(item.get("claim_id", "")).strip()
        claim = str(item.get("claim", "")).strip()
        claim_level = str(item.get("claim_level", "")).strip()
        evidence_level = str(item.get("evidence_level", "")).strip()
        evidence_ids = item.get("evidence_ids", [])
        if not claim_id or claim_id in seen or not claim:
            raise ValueError(f"claim binding {index} requires a unique claim_id and nonempty claim")
        if claim_level not in _CLAIM_LEVELS or evidence_level not in _CLAIM_LEVELS:
            raise ValueError(f"claim binding {claim_id} uses an unsupported claim or evidence level")
        if not isinstance(evidence_ids, list) or not all(isinstance(value, str) and value.strip() for value in evidence_ids):
            raise ValueError(f"claim binding {claim_id}.evidence_ids must be a string list")
        if not evidence_ids:
            findings.append({"code": "claim-without-evidence", "severity": "major", "claim_id": claim_id, "message": "The claim has no bound evidence artifact or citation."})
        if _CLAIM_LEVELS[claim_level] > _CLAIM_LEVELS[evidence_level]:
            findings.append({"code": "claim-exceeds-evidence", "severity": "major", "claim_id": claim_id, "message": f"The {claim_level} claim exceeds the declared {evidence_level} evidence."})
        if bool(item.get("hedging_required", False)) and not bool(item.get("hedging_preserved", False)):
            findings.append({"code": "required-hedging-removed", "severity": "major", "claim_id": claim_id, "message": "Evidence-calibrated uncertainty was required but is not preserved."})
        seen.add(claim_id)
    return findings


def audit_academic_prose_revision(
    original_text: str,
    document_type: str,
    section_kind: str,
    target_venue: str,
    revised_text: str = "",
    author_voice_sample: str = "",
    structure_policy: str = "preserve",
    protected_spans: list[dict[str, str]] | None = None,
    claim_bindings: list[dict[str, Any]] | None = None,
    ai_disclosure_evasion: bool = False,
) -> dict[str, Any]:
    """Audit prose before editing and validate a supplied revision without rewriting it."""
    if not isinstance(original_text, str) or not original_text.strip():
        raise ValueError("original_text must be nonempty")
    if document_type not in _DOCUMENT_TYPES:
        raise ValueError("document_type is unsupported")
    if not isinstance(section_kind, str) or not section_kind.strip() or not isinstance(target_venue, str):
        raise ValueError("section_kind and target_venue must be strings")
    if structure_policy not in _STRUCTURE_POLICIES:
        raise ValueError("structure_policy is unsupported")
    if not isinstance(revised_text, str) or not isinstance(author_voice_sample, str) or not isinstance(ai_disclosure_evasion, bool):
        raise ValueError("revision, voice sample, and disclosure-evasion fields are invalid")
    protected_spans = list(protected_spans or [])
    claim_bindings = list(claim_bindings or [])
    normalized_spans: list[dict[str, str]] = []
    for index, item in enumerate(protected_spans, start=1):
        if not isinstance(item, dict) or set(item) != {"kind", "text"}:
            raise ValueError(f"protected span {index} must contain exactly kind and text")
        kind, text = str(item["kind"]).strip(), str(item["text"])
        if kind not in {"number", "equation", "citation", "technical-term", "result"} or not text:
            raise ValueError(f"protected span {index} is invalid")
        normalized_spans.append({"kind": kind, "text": text})

    proposal_mode = document_type == "grant-proposal"
    source_findings = _style_findings(original_text, proposal_mode=proposal_mode)
    phase = "post-revision" if revised_text.strip() else "preflight"
    findings = list(source_findings) if phase == "preflight" else _style_findings(revised_text, proposal_mode=proposal_mode)
    if ai_disclosure_evasion:
        findings.append(
            {
                "code": "ai-disclosure-evasion-requested",
                "severity": "fatal",
                "location": {"document": 1},
                "excerpt": "",
                "action": "Use the workflow for scholarly clarity and comply with applicable disclosure rules.",
            }
        )

    original_numbers = _NUMBER_RE.findall(original_text)
    original_citations = _markers(original_text, _CITATION_PATTERNS)
    original_equations = _markers(original_text, _EQUATION_PATTERNS)
    invariant_report: dict[str, Any] = {
        "evaluated": phase == "post-revision",
        "numbers": {"preserved": None, "delta": {"removed": [], "added": []}, "original_count": len(original_numbers)},
        "citations": {"preserved": None, "delta": {"removed": [], "added": []}, "original_count": len(original_citations)},
        "equations": {"preserved": None, "delta": {"removed": [], "added": []}, "original_count": len(original_equations)},
        "protected_spans": {"preserved": None, "missing": []},
        "structure": {
            "preserved": None,
            "policy": structure_policy,
            "original_paragraphs": len(_paragraphs(original_text)),
            "revised_paragraphs": None,
            "original_headings": _HEADING_RE.findall(original_text),
            "revised_headings": [],
        },
    }
    if phase == "post-revision":
        revised_numbers = _NUMBER_RE.findall(revised_text)
        revised_citations = _markers(revised_text, _CITATION_PATTERNS)
        revised_equations = _markers(revised_text, _EQUATION_PATTERNS)
        for key, before, after in (
            ("numbers", original_numbers, revised_numbers),
            ("citations", original_citations, revised_citations),
            ("equations", original_equations, revised_equations),
        ):
            delta = _counter_delta(before, after)
            invariant_report[key]["preserved"] = not delta["removed"] and not delta["added"]
            invariant_report[key]["delta"] = delta
            invariant_report[key]["revised_count"] = len(after)
            if not invariant_report[key]["preserved"]:
                findings.append(
                    {
                        "code": f"{key}-changed",
                        "severity": "fatal",
                        "location": {"document": 1},
                        "excerpt": "",
                        "action": f"Restore every original {key[:-1]} exactly before delivery.",
                    }
                )
        missing_spans = [item for item in normalized_spans if revised_text.count(item["text"]) < original_text.count(item["text"])]
        invariant_report["protected_spans"] = {"preserved": not missing_spans, "missing": missing_spans}
        if missing_spans:
            findings.append(
                {
                    "code": "protected-span-removed",
                    "severity": "fatal",
                    "location": {"document": 1},
                    "excerpt": "",
                    "action": "Restore every declared result, technical term, number, equation, and citation span.",
                }
            )
        revised_paragraphs = len(_paragraphs(revised_text))
        revised_headings = _HEADING_RE.findall(revised_text)
        structure_preserved = len(_paragraphs(original_text)) == revised_paragraphs and _HEADING_RE.findall(original_text) == revised_headings
        invariant_report["structure"].update(
            {"preserved": structure_preserved, "revised_paragraphs": revised_paragraphs, "revised_headings": revised_headings}
        )
        if structure_policy == "preserve" and not structure_preserved:
            findings.append(
                {
                    "code": "undeclared-structure-change",
                    "severity": "major",
                    "location": {"document": 1},
                    "excerpt": "",
                    "action": "Restore paragraph and heading structure or declare and review the structural change.",
                }
            )
        findings.extend(_claim_findings(claim_bindings))

    major_count = sum(item["severity"] in {"major", "fatal"} for item in findings)
    return {
        "phase": phase,
        "document": {
            "type": document_type,
            "section": section_kind.strip(),
            "target_venue": target_venue.strip() or "unspecified",
            "proposal_mode": proposal_mode,
            "author_voice_sample_provided": bool(author_voice_sample.strip()),
        },
        "source_digest": _digest(original_text),
        "revision_digest": _digest(revised_text) if phase == "post-revision" else None,
        "source_audit": {
            "finding_count": len(source_findings),
            "findings": source_findings,
        },
        "invariant_report": invariant_report,
        "claim_findings": [item for item in findings if "claim_id" in item],
        "findings": findings,
        "major_or_fatal_count": major_count,
        "ready_for_delivery": phase == "post-revision" and major_count == 0,
        "required_output": {
            "cleaned_text": phase == "post-revision",
            "change_report": True,
            "confirm_numbers_equations_citations_unchanged": phase == "post-revision",
            "voice_and_venue_notes": True,
        },
        "next_step": (
            "Revise the text with the same evidence, structure, numbers, equations, citations, and technical terms, then run post-revision validation."
            if phase == "preflight"
            else ("Resolve blocking findings and validate again." if major_count else "Deliver the revised text with its change report.")
        ),
    }


def audit_research_proposal(
    mode: str,
    agency: str,
    scope: dict[str, Any],
    research_canon: list[dict[str, Any]],
    evidence_table: list[dict[str, Any]],
    argument_map: dict[str, Any],
    section_contracts: list[dict[str, Any]],
    aims: list[dict[str, Any]],
    review_criteria: list[str],
    iteration_scores: list[float] | None = None,
) -> dict[str, Any]:
    """Validate proposal foundations, claim-feasibility links, aims, and stopping rules."""
    if mode not in {"compose", "revise", "hybrid", "qa"}:
        raise ValueError("mode is unsupported")
    agency_key = str(agency).strip().lower()
    if not agency_key:
        raise ValueError("agency is required")
    if not isinstance(scope, dict) or not isinstance(argument_map, dict):
        raise ValueError("scope and argument_map must be objects")
    if not all(isinstance(value, list) for value in (research_canon, evidence_table, section_contracts, aims, review_criteria)):
        raise ValueError("proposal tables, aims, and review criteria must be arrays")
    iteration_scores = list(iteration_scores or [])
    if any(not isinstance(value, (int, float)) or not 0 <= float(value) <= 10 for value in iteration_scores):
        raise ValueError("iteration_scores must contain values from 0 to 10")

    findings: list[dict[str, Any]] = []
    required_scope = {"deliverable", "target_reader", "language", "constraints", "version_target"}
    missing_scope = sorted(field for field in required_scope if not str(scope.get(field, "")).strip())
    if missing_scope:
        findings.append({"code": "proposal-scope-incomplete", "severity": "major", "location": "scope", "missing": missing_scope})

    canon_ids: set[str] = set()
    for index, item in enumerate(research_canon, start=1):
        if not isinstance(item, dict):
            raise ValueError("research_canon must contain objects")
        identifier = str(item.get("id", "")).strip()
        fact = str(item.get("fact", "")).strip()
        if not identifier or identifier in canon_ids or not fact:
            raise ValueError(f"research canon row {index} requires a unique id and fact")
        canon_ids.add(identifier)
    if not canon_ids:
        findings.append({"code": "research-canon-empty", "severity": "major", "location": "research_canon"})

    evidence_claim_ids: set[str] = set()
    for index, item in enumerate(evidence_table, start=1):
        if not isinstance(item, dict):
            raise ValueError("evidence_table must contain objects")
        claim_id = str(item.get("claim_id", "")).strip()
        claim = str(item.get("claim", "")).strip()
        status = str(item.get("status", "")).strip()
        source_ids = item.get("source_ids", [])
        if not claim_id or claim_id in evidence_claim_ids or not claim or status not in _EVIDENCE_STATUSES:
            raise ValueError(f"evidence row {index} is invalid")
        if not isinstance(source_ids, list) or any(value not in canon_ids for value in source_ids):
            raise ValueError(f"evidence row {claim_id} references an unknown canon source")
        if status == "evidence-backed" and not source_ids:
            findings.append({"code": "backed-claim-without-source", "severity": "major", "location": claim_id})
        if status == "unsupported":
            findings.append({"code": "unsupported-proposal-claim", "severity": "major", "location": claim_id})
        evidence_claim_ids.add(claim_id)
    if not evidence_claim_ids:
        findings.append({"code": "evidence-table-empty", "severity": "major", "location": "evidence_table"})

    for field in ("scientific_tension", "central_question", "central_thesis", "limitations"):
        if not argument_map.get(field):
            findings.append({"code": "argument-map-field-missing", "severity": "major", "location": f"argument_map.{field}"})

    contract_ids: set[str] = set()
    for index, item in enumerate(section_contracts, start=1):
        if not isinstance(item, dict):
            raise ValueError("section_contracts must contain objects")
        identifier = str(item.get("id", "")).strip()
        if not identifier or identifier in contract_ids:
            raise ValueError(f"section contract {index} requires a unique id")
        missing = [field for field in ("purpose", "inputs", "allowed_claims", "forbidden_claims", "required_evidence", "validation") if not item.get(field)]
        if missing:
            findings.append({"code": "section-contract-incomplete", "severity": "major", "location": identifier, "missing": missing})
        unknown_claims = sorted(set(item.get("allowed_claims", [])) - evidence_claim_ids)
        if unknown_claims:
            findings.append({"code": "section-contract-unknown-claim", "severity": "major", "location": identifier, "claim_ids": unknown_claims})
        contract_ids.add(identifier)
    if not contract_ids:
        findings.append({"code": "section-contracts-empty", "severity": "major", "location": "section_contracts"})

    aim_ids: set[str] = set()
    for index, item in enumerate(aims, start=1):
        if not isinstance(item, dict):
            raise ValueError("aims must contain objects")
        identifier = str(item.get("id", "")).strip()
        if not identifier or identifier in aim_ids:
            raise ValueError(f"aim {index} requires a unique id")
        missing = [field for field in ("objective", "rationale", "approach", "expected_outcome", "feasibility_evidence", "independence", "fallback") if not item.get(field)]
        if missing:
            findings.append({"code": "aim-incomplete", "severity": "major", "location": identifier, "missing": missing})
        objective = str(item.get("objective", "")).strip()
        if re.match(r"^(?:apply|use|perform|run|利用|采用|应用)\b", objective, re.IGNORECASE):
            findings.append({"code": "method-as-aim", "severity": "minor", "location": identifier})
        aim_ids.add(identifier)
    if not aims:
        findings.append({"code": "aims-empty", "severity": "major", "location": "aims"})

    criteria = {str(value).strip().lower().replace(" ", "_") for value in review_criteria if str(value).strip()}
    if "nsf" in agency_key:
        missing = sorted({"overview", "intellectual_merit", "broader_impacts"} - criteria)
        if missing:
            findings.append({"code": "nsf-review-criteria-missing", "severity": "major", "location": "review_criteria", "missing": missing})
    if "nih" in agency_key:
        if not 2 <= len(aims) <= 3:
            findings.append({"code": "nih-specific-aim-count", "severity": "minor", "location": "aims"})
        missing = sorted({"significance", "innovation", "approach"} - criteria)
        if missing:
            findings.append({"code": "nih-review-criteria-missing", "severity": "major", "location": "review_criteria", "missing": missing})
        if not argument_map.get("central_hypothesis"):
            findings.append({"code": "nih-central-hypothesis-missing", "severity": "major", "location": "argument_map.central_hypothesis"})

    stop_reasons: list[str] = []
    if len(iteration_scores) >= 4:
        stop_reasons.append("maximum-three-revision-rounds-reached")
    if len(iteration_scores) >= 3 and iteration_scores[-1] - iteration_scores[-2] < 0.5 and iteration_scores[-2] - iteration_scores[-3] < 0.5:
        stop_reasons.append("two-consecutive-score-improvements-below-0.5")
    if any(item["code"] in {"research-canon-empty", "unsupported-proposal-claim", "backed-claim-without-source"} for item in findings):
        stop_reasons.append("key-evidence-gap")

    major_count = sum(item["severity"] == "major" for item in findings)
    return {
        "mode": mode,
        "agency": agency,
        "foundation": {
            "scope_complete": not missing_scope,
            "canon_count": len(canon_ids),
            "evidence_claim_count": len(evidence_claim_ids),
            "section_contract_count": len(contract_ids),
            "aim_count": len(aim_ids),
            "digest": _digest({"scope": scope, "canon": research_canon, "evidence": evidence_table, "argument": argument_map, "contracts": section_contracts, "aims": aims}),
        },
        "findings": findings,
        "major_finding_count": major_count,
        "ready_for_scientific_drafting": major_count == 0,
        "stop_iteration": bool(stop_reasons),
        "stop_reasons": sorted(set(stop_reasons)),
        "next_step": (
            "Resolve proposal foundation and feasibility findings before drafting prose."
            if major_count
            else ("Stop the revision loop and request the missing decision or evidence." if stop_reasons else "Draft or revise under the frozen section contracts, then run academic prose validation.")
        ),
    }


def audit_statistical_reporting(
    design: dict[str, Any],
    analyses: list[dict[str, Any]],
    result_statements: list[dict[str, Any]],
    figure_statistics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Audit statistical reporting without inventing design or reanalysing absent data."""
    if not isinstance(design, dict) or not isinstance(analyses, list) or not isinstance(result_statements, list):
        raise ValueError("design, analyses, and result_statements have invalid types")
    figure_statistics = list(figure_statistics or [])
    findings: list[dict[str, Any]] = []
    for field in ("experimental_unit", "biological_replicates", "technical_replicates", "randomization", "blinding", "exclusion_rules", "missing_data"):
        if field not in design or design[field] in {None, ""}:
            findings.append({"code": "design-field-missing", "severity": "major", "location": f"design.{field}"})
    if str(design.get("experimental_unit", "")).strip().lower() in {"cell", "cells", "field", "fields", "image", "images", "measurement", "measurements"}:
        findings.append({"code": "possible-pseudoreplication", "severity": "major", "location": "design.experimental_unit"})

    analysis_ids: set[str] = set()
    for index, item in enumerate(analyses, start=1):
        if not isinstance(item, dict):
            raise ValueError("analyses must contain objects")
        identifier = str(item.get("id", "")).strip()
        if not identifier or identifier in analysis_ids:
            raise ValueError(f"analysis {index} requires a unique id")
        for field in ("comparison_or_model", "test_or_model", "unit_of_analysis", "assumptions", "multiple_comparison_policy", "effect_size", "uncertainty", "software_version"):
            if field not in item or item[field] is None or item[field] == "" or item[field] == []:
                findings.append({"code": "analysis-field-missing", "severity": "major", "location": f"analysis.{identifier}.{field}"})
        analysis_ids.add(identifier)
    if not analysis_ids:
        findings.append({"code": "analysis-register-empty", "severity": "major", "location": "analyses"})

    for index, item in enumerate(result_statements, start=1):
        if not isinstance(item, dict):
            raise ValueError("result_statements must contain objects")
        analysis_id = str(item.get("analysis_id", "")).strip()
        text = str(item.get("text", "")).strip()
        if analysis_id not in analysis_ids:
            findings.append({"code": "result-analysis-unresolved", "severity": "major", "location": f"result.{index}"})
        if not text:
            findings.append({"code": "result-text-empty", "severity": "major", "location": f"result.{index}"})
            continue
        if re.search(r"\bsignificant(?:ly)?\b|显著", text, re.IGNORECASE) and not re.search(r"(?:p\s*[<=>]|confidence interval|\bCI\b|置信区间|effect size|效应量)", text, re.IGNORECASE):
            findings.append({"code": "significance-without-statistic", "severity": "major", "location": f"result.{index}"})
        if re.search(r"\b(?:causes?|drives?|determines?)\b|导致|决定了", text, re.IGNORECASE) and not bool(item.get("causal_design", False)):
            findings.append({"code": "causal-language-without-causal-design", "severity": "major", "location": f"result.{index}"})

    for index, item in enumerate(figure_statistics, start=1):
        if not isinstance(item, dict):
            raise ValueError("figure_statistics must contain objects")
        for field in ("panel", "n_definition", "error_bar_definition", "test_or_model", "comparison", "exact_p_value_policy"):
            if not item.get(field):
                findings.append({"code": "figure-statistics-field-missing", "severity": "major", "location": f"figure_statistics.{index}.{field}"})

    major_count = sum(item["severity"] == "major" for item in findings)
    return {
        "design_readout": {
            "experimental_unit": design.get("experimental_unit"),
            "biological_replicates": design.get("biological_replicates"),
            "technical_replicates": design.get("technical_replicates"),
        },
        "analysis_count": len(analysis_ids),
        "result_statement_count": len(result_statements),
        "figure_panel_count": len(figure_statistics),
        "findings": findings,
        "major_finding_count": major_count,
        "ready_for_manuscript_reporting": major_count == 0,
        "author_input_needed": [item["location"] for item in findings if item["code"].endswith("missing") or "field-missing" in item["code"]],
        "limitations": [
            "This audit checks declared design and reporting records; it does not reanalyse raw data or establish that a selected model is scientifically correct.",
            "A domain statistician or study-design expert must review analyses whose design, dependence structure, missingness, or estimand remains ambiguous.",
        ],
    }
