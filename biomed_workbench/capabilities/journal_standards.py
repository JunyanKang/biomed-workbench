"""Version-bound journal targeting and manuscript compliance checks."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


CATALOG_ROOT = Path(__file__).resolve().parents[1] / "knowledge" / "journal_standards"
TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*", re.IGNORECASE)
STOPWORDS = {
    "and",
    "are",
    "for",
    "from",
    "into",
    "our",
    "the",
    "their",
    "this",
    "through",
    "using",
    "with",
    "research",
    "researcher",
    "researchers",
    "seeking",
    "study",
    "studies",
}
TOKEN_ALIASES = {
    "biological": "biology",
    "biologist": "biology",
    "biologists": "biology",
    "cellular": "cell",
    "developmental": "development",
    "genomic": "genomics",
    "medical": "medicine",
    "regenerative": "regeneration",
}


def _load_catalog(version: str | None = None) -> tuple[dict[str, Any], str]:
    index = json.loads((CATALOG_ROOT / "index.json").read_text(encoding="utf-8"))
    selected = version or str(index["active_catalog_version"])
    path = CATALOG_ROOT / f"v{selected}.json"
    if not path.is_file():
        raise ValueError(f"journal standard catalog version is unavailable: {selected}")
    raw = path.read_bytes()
    catalog = json.loads(raw)
    if catalog.get("catalog_version") != selected:
        raise ValueError("journal standard catalog identity is inconsistent")
    digest = hashlib.sha256(raw).hexdigest()
    if selected == index["active_catalog_version"] and digest != index["active_catalog_sha256"]:
        raise ValueError("active journal standard catalog failed digest verification")
    if catalog.get("journal_count") != len(catalog.get("journals", [])) or len(catalog["journals"]) < 50:
        raise ValueError("journal standard catalog is incomplete")
    if selected == index["active_catalog_version"]:
        if len(catalog["journals"]) != 100:
            raise ValueError("active journal standard catalog must contain 100 journals")
        manifest = catalog.get("metric_source_manifest", {})
        source_file = CATALOG_ROOT.parents[2] / str(manifest.get("file", ""))
        if not source_file.is_file():
            raise ValueError("active journal metric source manifest is unavailable")
        source_digest = hashlib.sha256(source_file.read_bytes()).hexdigest()
        if source_digest != manifest.get("sha256") or source_digest != index.get("metric_source_sha256"):
            raise ValueError("active journal metric source manifest failed digest verification")
        previous_jif = float("inf")
        seen_unassigned = False
        for profile in catalog["journals"]:
            metric = profile.get("journal_metrics")
            if not isinstance(metric, dict) or not metric.get("categories") or not metric.get("source"):
                raise ValueError("active journal standard has incomplete metric provenance")
            jif = metric.get("jif")
            if jif is None:
                seen_unassigned = True
            elif seen_unassigned or not isinstance(jif, (int, float)) or isinstance(jif, bool) or jif > previous_jif:
                raise ValueError("active journal standards are not sorted by descending JIF")
            else:
                previous_jif = float(jif)
    return catalog, digest


def _tokens(values: list[str] | str) -> set[str]:
    text = " ".join(values) if isinstance(values, list) else values
    return {
        TOKEN_ALIASES.get(token.strip().lower(), token.strip().lower())
        for token in TOKEN_RE.findall(text.lower())
        if len(token.strip()) >= 3 and token.strip().lower() not in STOPWORDS
    }


def _matched_terms(profile_terms: list[str], project_tokens: set[str]) -> list[str]:
    """Return declared profile concepts whose meaningful tokens occur in the project."""
    matches = []
    for term in profile_terms:
        term_tokens = _tokens(term)
        if term_tokens and term_tokens.issubset(project_tokens):
            matches.append(term)
    return matches


def _fit_score(profile: dict[str, Any], project: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    project_concepts = _tokens(
        [
            str(project.get("summary", "")),
            *[str(value) for value in project.get("topics", [])],
            *[str(value) for value in project.get("methods", [])],
        ]
    )
    audience = _tokens(str(project.get("intended_audience", "")))
    study_type = str(project.get("study_type", "")).strip().lower()
    profile_audience = _tokens(profile["audience"])
    profile_types = {value.lower() for value in profile["favored_article_types"]}
    topic_hits = _matched_terms(profile["topic_fit_terms"], project_concepts)
    audience_hits = sorted(audience & profile_audience)
    type_hits = sorted(value for value in profile_types if study_type and (study_type in value or value in study_type))
    score = min(6.0, 2.0 * len(topic_hits)) + min(2.0, 0.5 * len(audience_hits)) + min(2.0, 2.0 * len(type_hits))
    reasons = []
    if topic_hits:
        reasons.append("topic overlap: " + ", ".join(topic_hits[:6]))
    if audience_hits:
        reasons.append("audience overlap: " + ", ".join(audience_hits[:4]))
    if type_hits:
        reasons.append("article-type overlap: " + ", ".join(type_hits[:2]))
    gaps = []
    if not topic_hits:
        gaps.append("No explicit topic match was found; scope requires editorial review.")
    if not type_hits:
        gaps.append("The requested study type was not an explicit article-type match.")
    if not audience_hits and project.get("intended_audience"):
        gaps.append("The intended audience did not explicitly overlap the journal audience statement.")
    return round(score, 2), reasons, gaps


def _metric_check(
    findings: list[dict[str, Any]],
    name: str,
    observed: Any,
    maximum: Any,
    *,
    label: str,
) -> None:
    if maximum is None:
        findings.append(
            {
                "field": name,
                "status": "manual-check",
                "observed": observed,
                "limit": None,
                "message": f"No verified public {label} limit is stored; bind the live article-type guide before submission.",
            }
        )
        return
    if observed is None:
        findings.append(
            {
                "field": name,
                "status": "missing",
                "observed": None,
                "limit": maximum,
                "message": f"{label} must be measured for compliance review.",
            }
        )
        return
    if not isinstance(observed, int) or isinstance(observed, bool) or observed < 0:
        raise ValueError(f"manuscript.{name} must be a nonnegative integer")
    findings.append(
        {
            "field": name,
            "status": "pass" if observed <= maximum else "fail",
            "observed": observed,
            "limit": maximum,
            "message": f"{label} is within the stored limit." if observed <= maximum else f"{label} exceeds the stored limit.",
        }
    )


def _compliance(profile: dict[str, Any], manuscript: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(manuscript, dict):
        raise ValueError("manuscript must be an object")
    findings: list[dict[str, Any]] = []
    constraints = profile["constraints"]
    _metric_check(findings, "main_text_words", manuscript.get("main_text_words"), constraints.get("main_text_words"), label="main-text word")
    _metric_check(findings, "abstract_words", manuscript.get("abstract_words"), constraints.get("abstract_words"), label="abstract word")
    _metric_check(findings, "display_items", manuscript.get("display_items"), constraints.get("display_items"), label="combined figure/table")
    _metric_check(findings, "references", manuscript.get("references"), constraints.get("references"), label="reference")
    if constraints.get("main_text_characters_with_spaces") is not None:
        _metric_check(
            findings,
            "main_text_characters_with_spaces",
            manuscript.get("main_text_characters_with_spaces"),
            constraints["main_text_characters_with_spaces"],
            label="main-text character-with-spaces",
        )
    sections = manuscript.get("sections", [])
    if not isinstance(sections, list) or any(not isinstance(value, str) for value in sections):
        raise ValueError("manuscript.sections must be a string list")
    present = {value.strip().casefold() for value in sections}
    for section in profile["required_sections"]:
        status = "pass" if section.casefold() in present else "missing"
        findings.append(
            {
                "field": f"section:{section}",
                "status": status,
                "observed": section if status == "pass" else None,
                "limit": "required",
                "message": f"{section} is present." if status == "pass" else f"Required section {section} was not declared.",
            }
        )
    declarations = manuscript.get("declarations", [])
    if not isinstance(declarations, list) or any(not isinstance(value, str) for value in declarations):
        raise ValueError("manuscript.declarations must be a string list")
    declared = {value.strip().casefold() for value in declarations}
    for requirement in profile["reporting_requirements"]:
        findings.append(
            {
                "field": f"reporting:{requirement}",
                "status": "pass" if requirement.casefold() in declared else "manual-check",
                "observed": requirement if requirement.casefold() in declared else None,
                "limit": "required-or-applicability-check",
                "message": (
                    f"{requirement} is declared."
                    if requirement.casefold() in declared
                    else f"Confirm applicability and completion of {requirement}."
                ),
            }
        )
    failed = sum(row["status"] in {"fail", "missing"} for row in findings)
    manual = sum(row["status"] == "manual-check" for row in findings)
    return {
        "findings": findings,
        "failed_count": failed,
        "manual_check_count": manual,
        "submission_ready": failed == 0 and manual == 0,
        "readiness_rule": "Submission-ready requires no failed, missing, or unresolved manual checks against the bound standard version.",
    }


def journal_targeting_and_compliance(
    project: dict[str, Any],
    target_journal_id: str | None = None,
    candidate_journal_ids: list[str] | None = None,
    manuscript: dict[str, Any] | None = None,
    top_k: int = 5,
    standard_version: str | None = None,
) -> dict[str, Any]:
    """Rank journal fit and audit a manuscript against one immutable standard version."""
    if not isinstance(project, dict) or not str(project.get("summary", "")).strip():
        raise ValueError("project.summary is required")
    if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 20:
        raise ValueError("top_k must be an integer from 1 to 20")
    catalog, digest = _load_catalog(standard_version)
    by_id = {row["id"]: row for row in catalog["journals"]}
    candidates = list(candidate_journal_ids or by_id)
    if len(candidates) != len(set(candidates)) or any(value not in by_id for value in candidates):
        raise ValueError("candidate_journal_ids contains an unknown or duplicate journal")
    ranked = []
    for journal_id in candidates:
        profile = by_id[journal_id]
        score, reasons, gaps = _fit_score(profile, project)
        ranked.append(
            {
                "journal_id": journal_id,
                "title": profile["title"],
                "fit_score_0_to_10": score,
                "fit_reasons": reasons,
                "fit_gaps": gaps,
                "audience": profile["audience"],
                "favored_article_types": profile["favored_article_types"],
                "standard_version": profile["standard_version"],
                "reviewed_on": profile["reviewed_on"],
                "official_sources": profile["official_sources"],
                "journal_metrics": profile.get("journal_metrics"),
            }
        )
    ranked.sort(key=lambda row: (-row["fit_score_0_to_10"], row["title"]))
    target = None
    compliance = None
    if target_journal_id is not None:
        if target_journal_id not in by_id:
            raise ValueError("target_journal_id is not present in the bound catalog")
        target = by_id[target_journal_id]
        if manuscript is not None:
            compliance = _compliance(target, manuscript)
    return {
        "catalog_version": catalog["catalog_version"],
        "catalog_sha256": digest,
        "reviewed_on": catalog["reviewed_on"],
        "journal_count": catalog["journal_count"],
        "recommendations": ranked[:top_k],
        "target_standard": target,
        "compliance": compliance,
        "policy": {
            "impact_factor_used": False,
            "acceptance_probability_claimed": False,
            "metric_source_levels_are_explicit": True,
            "secondary_metrics_require_primary_recheck_when_available": True,
            "target_standard_version_is_mandatory_for_drafting": True,
            "live_source_recheck_required_before_submission": True,
        },
    }
