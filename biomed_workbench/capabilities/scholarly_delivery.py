"""Deterministic scholarly-delivery records and package audits."""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from typing import Any
from xml.etree import ElementTree as ET


_ACCESS_ROUTES = {
    "public-repository",
    "controlled-access-repository",
    "within-paper-or-supplement",
    "reused-public-source",
    "third-party-restricted",
    "justified-request",
    "not-applicable",
}
_LITERATURE_STATUSES = {
    "downloaded",
    "downloaded_with_si",
    "open_access_downloaded",
    "full_text_html_available",
    "available_not_downloaded",
    "institutional_login_waiting_user",
    "publisher_verification_waiting_user",
    "retry_after_user_verification",
    "do_not_auto_retry",
    "url_needs_repair",
    "library_no_permission",
    "no_full_text_link",
    "publisher_blocked_waiting_user",
    "no_authorized_pdf_found",
    "failed_after_retry",
}
_SOURCE_LEVELS = {"full-text", "abstract-only", "metadata-only"}
_LANDSCAPE_SCORE_FIELDS = (
    "topic_relevance",
    "claim_directness",
    "methodological_fit",
    "evidence_depth",
    "novelty_value",
    "recency_value",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STABLE_IDENTIFIER_RE = re.compile(
    r"^(?:10\.\d{4,9}/\S+|(?:GSE|GSM|SRP|SRR|SRS|PRJNA|PRJEB|E-MTAB-|PXD|MTBLS|phs|EGAS|SCP|HRA)\S+|https://doi\.org/10\.\d{4,9}/\S+)$",
    re.IGNORECASE,
)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def audit_data_availability(
    target_journal: str,
    datasets: list[dict[str, Any]],
    statement: str,
    code_availability: dict[str, Any] | None = None,
    materials_availability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit claim-supporting data routes, identifiers, restrictions, and statement coverage."""
    if not isinstance(target_journal, str) or not isinstance(statement, str) or not isinstance(datasets, list):
        raise ValueError("target_journal, datasets, and statement have invalid types")
    code_availability = dict(code_availability or {})
    materials_availability = dict(materials_availability or {})
    findings: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for index, item in enumerate(datasets, start=1):
        if not isinstance(item, dict):
            raise ValueError("datasets must contain objects")
        identifier = str(item.get("id", "")).strip()
        title = str(item.get("title", "")).strip()
        route = str(item.get("access_route", "")).strip()
        role = str(item.get("claim_support_role", "")).strip()
        repository = str(item.get("repository", "")).strip()
        stable_identifier = str(item.get("stable_identifier", "")).strip()
        restriction = str(item.get("restriction_reason", "")).strip()
        access_process = str(item.get("access_process", "")).strip()
        if not identifier or identifier in identifiers or not title or not role or route not in _ACCESS_ROUTES:
            raise ValueError(f"dataset row {index} requires a unique id, title, claim-support role, and valid access route")
        if route in {"public-repository", "controlled-access-repository", "reused-public-source"}:
            if not repository:
                findings.append({"code": "repository-missing", "severity": "major", "dataset_id": identifier})
            if not stable_identifier or not _STABLE_IDENTIFIER_RE.match(stable_identifier):
                findings.append({"code": "stable-identifier-missing-or-invalid", "severity": "major", "dataset_id": identifier})
        if route in {"controlled-access-repository", "third-party-restricted", "justified-request"}:
            if not restriction:
                findings.append({"code": "restriction-reason-missing", "severity": "major", "dataset_id": identifier})
            if not access_process:
                findings.append({"code": "access-process-missing", "severity": "major", "dataset_id": identifier})
        if route == "justified-request" and re.search(r"available (?:from|upon request to) the corresponding author", statement, re.IGNORECASE) and not restriction:
            findings.append({"code": "unsupported-available-upon-request", "severity": "major", "dataset_id": identifier})
        if identifier not in statement and stable_identifier and stable_identifier not in statement:
            findings.append({"code": "dataset-statement-mapping-missing", "severity": "major", "dataset_id": identifier})
        normalized.append(
            {
                "id": identifier,
                "title": title,
                "claim_support_role": role,
                "access_route": route,
                "repository": repository or None,
                "stable_identifier": stable_identifier or None,
                "restriction_reason": restriction or None,
                "access_process": access_process or None,
            }
        )
        identifiers.add(identifier)
    if not datasets:
        findings.append({"code": "dataset-inventory-empty", "severity": "major", "dataset_id": None})
    if not statement.strip():
        findings.append({"code": "data-availability-statement-empty", "severity": "major", "dataset_id": None})
    for label, record in (("code", code_availability), ("materials", materials_availability)):
        if record and not str(record.get("status", "")).strip():
            findings.append({"code": f"{label}-availability-status-missing", "severity": "major", "dataset_id": None})
    major_count = sum(item["severity"] == "major" for item in findings)
    return {
        "target_journal": target_journal.strip() or "unspecified",
        "dataset_inventory": normalized,
        "dataset_count": len(normalized),
        "statement": statement.strip(),
        "code_availability": code_availability,
        "materials_availability": materials_availability,
        "findings": findings,
        "major_finding_count": major_count,
        "ready_for_manuscript": major_count == 0,
        "inventory_digest": _digest(normalized),
        "limitations": [
            "Repository suitability, embargo, consent, governance, and journal policy must be verified against the current authoritative instructions before submission.",
            "This audit does not invent or register repository identifiers and does not upload data.",
        ],
    }


def audit_paper_reader_package(
    paper_markdown: str,
    source_map: list[dict[str, Any]],
    translation_notes: str,
    assets: list[dict[str, Any]] | None = None,
    source_complete: bool = True,
) -> dict[str, Any]:
    """Validate a bilingual, source-anchored paper reader package."""
    if not isinstance(paper_markdown, str) or not isinstance(source_map, list) or not isinstance(translation_notes, str):
        raise ValueError("paper_markdown, source_map, and translation_notes have invalid types")
    assets = list(assets or [])
    findings: list[dict[str, Any]] = []
    source_ids: list[str] = []
    source_types = {"text", "caption", "figure", "table"}
    prefixes = {"text": "S", "caption": "C", "figure": "F", "table": "T"}
    for index, item in enumerate(source_map, start=1):
        if not isinstance(item, dict):
            raise ValueError("source_map must contain objects")
        identifier = str(item.get("id", "")).strip()
        kind = str(item.get("type", "")).strip()
        if kind not in source_types or not re.fullmatch(rf"{prefixes.get(kind, 'X')}\d{{3,}}", identifier):
            raise ValueError(f"source map row {index} has an invalid type or stable id")
        if identifier in source_ids:
            raise ValueError("source_map contains duplicate ids")
        original = str(item.get("original", ""))
        translation = str(item.get("translation", ""))
        page = item.get("page")
        if not isinstance(page, int) or page < 1:
            findings.append({"code": "source-page-missing", "severity": "major", "source_id": identifier})
        if kind in {"text", "caption"} and (not original.strip() or not translation.strip()):
            findings.append({"code": "bilingual-block-incomplete", "severity": "major", "source_id": identifier})
        if identifier not in paper_markdown:
            findings.append({"code": "source-anchor-not-rendered", "severity": "major", "source_id": identifier})
        source_ids.append(identifier)
    text_count = sum(item.get("type") == "text" for item in source_map if isinstance(item, dict))
    if paper_markdown.count("**Original:**") < text_count or paper_markdown.count("**中文:**") < text_count:
        findings.append({"code": "visible-bilingual-pairs-incomplete", "severity": "major", "source_id": None})
    if not source_complete and not re.search(r"draft|incomplete|pending|缺失|未完成|待处理", translation_notes, re.IGNORECASE):
        findings.append({"code": "incomplete-source-not-disclosed", "severity": "major", "source_id": None})
    asset_ids: set[str] = set()
    for index, item in enumerate(assets, start=1):
        if not isinstance(item, dict):
            raise ValueError("assets must contain objects")
        identifier = str(item.get("id", "")).strip()
        source_id = str(item.get("source_id", "")).strip()
        path = str(item.get("path", "")).strip()
        digest = str(item.get("sha256", "")).strip()
        if not identifier or identifier in asset_ids or source_id not in source_ids or not path or not _SHA256_RE.fullmatch(digest):
            raise ValueError(f"asset row {index} is invalid")
        if path not in paper_markdown:
            findings.append({"code": "asset-not-linked", "severity": "major", "source_id": source_id})
        asset_ids.add(identifier)
    figure_table_ids = {item["id"] for item in source_map if isinstance(item, dict) and item.get("type") in {"figure", "table"}}
    asset_source_ids = {str(item.get("source_id", "")) for item in assets if isinstance(item, dict)}
    for missing in sorted(figure_table_ids - asset_source_ids):
        findings.append({"code": "figure-or-table-asset-missing", "severity": "major", "source_id": missing})
    major_count = sum(item["severity"] == "major" for item in findings)
    return {
        "source_block_count": len(source_map),
        "text_block_count": text_count,
        "asset_count": len(assets),
        "source_complete": source_complete,
        "findings": findings,
        "major_finding_count": major_count,
        "ready_for_reading": major_count == 0,
        "source_map_digest": _digest(source_map),
        "package_digest": _digest({"paper": paper_markdown, "map": source_map, "notes": translation_notes, "assets": assets}),
        "limitations": [
            "This gate validates the supplied reader package structure and traceability; it does not prove translation accuracy or figure-crop fidelity without expert visual review.",
        ],
    }


def standardize_experiment_log(
    experiment_date: str,
    system_code: str,
    device_code: str,
    daily_sequence: int,
    experiment_type: str,
    objective: str,
    sample_batches: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    raw_materials: list[dict[str, Any]],
    anomalies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a deterministic Markdown experiment record and archive plan."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", experiment_date):
        raise ValueError("experiment_date must use YYYY-MM-DD")
    system = str(system_code).strip().upper()
    device = str(device_code).strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]{0,5}", system) or not re.fullmatch(r"[A-Z][A-Z0-9]{0,3}", device):
        raise ValueError("system_code or device_code is invalid")
    if not isinstance(daily_sequence, int) or not 1 <= daily_sequence <= 999:
        raise ValueError("daily_sequence must be 1..999")
    if not experiment_type.strip() or not objective.strip():
        raise ValueError("experiment_type and objective are required")
    for value, name in ((sample_batches, "sample_batches"), (steps, "steps"), (observations, "observations"), (raw_materials, "raw_materials")):
        if not isinstance(value, list):
            raise ValueError(f"{name} must be an array")
    anomalies = list(anomalies or [])
    experiment_id = f"{system}-{device}-{experiment_date[2:4]}{experiment_date[5:7]}{experiment_date[8:10]}-{daily_sequence:03d}"
    issues: list[dict[str, Any]] = []
    sample_ids: set[str] = set()
    for index, sample in enumerate(sample_batches, start=1):
        if not isinstance(sample, dict):
            raise ValueError("sample_batches must contain objects")
        identifier = str(sample.get("sample_batch", "")).strip()
        if not identifier or identifier in sample_ids:
            raise ValueError(f"sample row {index} requires a unique sample_batch")
        if not str(sample.get("description", "")).strip():
            issues.append({"code": "sample-description-missing", "severity": "major", "location": identifier})
        sample_ids.add(identifier)
    normalized_steps: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValueError("steps must contain objects")
        action = str(step.get("action", "")).strip()
        if not action:
            issues.append({"code": "step-action-missing", "severity": "major", "location": f"step-{index}"})
        normalized_steps.append({"index": index, "action": action, "conditions": dict(step.get("conditions", {})), "sample_batches": list(step.get("sample_batches", []))})
        unknown = sorted(set(normalized_steps[-1]["sample_batches"]) - sample_ids)
        if unknown:
            issues.append({"code": "step-unknown-sample", "severity": "major", "location": f"step-{index}", "sample_batches": unknown})
    for index, item in enumerate(raw_materials, start=1):
        if not isinstance(item, dict):
            raise ValueError("raw_materials must contain objects")
        path = str(item.get("path", "")).strip()
        digest = str(item.get("sha256", "")).strip()
        if not path or not _SHA256_RE.fullmatch(digest):
            issues.append({"code": "raw-material-identity-incomplete", "severity": "major", "location": f"raw-{index}"})
    uncertain_markers = re.compile(r"(?:unknown|unclear|not sure|approximately\?|不清楚|不确定|记不清|待确认)", re.IGNORECASE)
    for group, rows in (("observation", observations), ("anomaly", anomalies)):
        for index, item in enumerate(rows, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"{group} rows must be objects")
            text = str(item.get("text", "")).strip()
            if not text:
                issues.append({"code": f"{group}-empty", "severity": "major", "location": f"{group}-{index}"})
            elif uncertain_markers.search(text):
                issues.append({"code": "author-input-needed", "severity": "major", "location": f"{group}-{index}", "question": text})

    frontmatter = {
        "experiment_id": experiment_id,
        "date": experiment_date,
        "system": system,
        "device": device,
        "experiment_type": experiment_type.strip(),
        "sample_batches": sorted(sample_ids),
        "status": "needs-clarification" if any(item["severity"] == "major" for item in issues) else "recorded",
    }
    yaml_lines = ["---"] + [f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in frontmatter.items()] + ["---", ""]
    body = [
        f"# {experiment_type.strip()} ({experiment_id})",
        "",
        "## Objective",
        objective.strip(),
        "",
        "## Samples",
        *[f"- {item['sample_batch']}: {str(item.get('description', '')).strip()}" for item in sample_batches],
        "",
        "## Procedure",
        *[f"{item['index']}. {item['action']}" for item in normalized_steps],
        "",
        "## Observations",
        *[f"- {str(item.get('text', '')).strip()}" for item in observations],
        "",
        "## Anomalies",
        *([f"- {str(item.get('text', '')).strip()}" for item in anomalies] or ["- None recorded"]),
        "",
        "## Raw materials",
        *[f"- {item.get('path', '')} ({item.get('sha256', '')})" for item in raw_materials],
        "",
    ]
    log_markdown = "\n".join(yaml_lines + body)
    folder = f"raw/experiments/{experiment_date.replace('-', '.')}_{experiment_type.strip().replace(' ', '-')}_{experiment_id}"
    major_count = sum(item["severity"] == "major" for item in issues)
    return {
        "experiment_id": experiment_id,
        "record": {"frontmatter": frontmatter, "steps": normalized_steps, "observations": observations, "anomalies": anomalies},
        "log_markdown": log_markdown,
        "archive_plan": {
            "raw_folder": folder,
            "log_path": f"wiki/实验日志/{system}/{experiment_type.strip()}/{experiment_id}.md",
            "update_index": True,
            "update_anomaly_register": bool(anomalies),
        },
        "issues": issues,
        "major_issue_count": major_count,
        "ready_to_write": major_count == 0,
        "record_digest": _digest({"frontmatter": frontmatter, "samples": sample_batches, "steps": normalized_steps, "observations": observations, "raw": raw_materials, "anomalies": anomalies}),
        "limitations": ["The caller must obtain permission for the destination vault and archive source files without altering their bytes."],
    }


def audit_literature_acquisition_manifest(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Audit lawful literature-acquisition outcomes without attempting authentication or downloads."""
    if not isinstance(items, list):
        raise ValueError("items must be an array")
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    identities: set[str] = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError("items must contain objects")
        identity = str(item.get("id", "")).strip()
        title = str(item.get("title", "")).strip()
        status = str(item.get("status", "")).strip()
        source_level = str(item.get("source_level", "")).strip()
        access_route = str(item.get("access_route", "")).strip()
        if not identity or identity in identities or not title or status not in _LITERATURE_STATUSES or source_level not in _SOURCE_LEVELS or not access_route:
            raise ValueError(f"literature row {index} is invalid")
        file_name = str(item.get("file_name", "")).strip()
        digest = str(item.get("sha256", "")).strip()
        signature = bool(item.get("pdf_signature_verified", False))
        page_count = item.get("page_count")
        if status in {"downloaded", "downloaded_with_si", "open_access_downloaded"}:
            if not file_name or not _SHA256_RE.fullmatch(digest) or not signature or not isinstance(page_count, int) or page_count < 1:
                findings.append({"code": "download-verification-incomplete", "severity": "major", "item_id": identity})
            if source_level != "full-text":
                findings.append({"code": "download-source-level-inconsistent", "severity": "major", "item_id": identity})
        if status == "full_text_html_available" and file_name.lower().endswith(".pdf"):
            findings.append({"code": "html-mislabelled-as-pdf", "severity": "major", "item_id": identity})
        if status in {"institutional_login_waiting_user", "publisher_verification_waiting_user", "publisher_blocked_waiting_user"} and not str(item.get("next_action", "")).strip():
            findings.append({"code": "user-handoff-action-missing", "severity": "major", "item_id": identity})
        if bool(item.get("access_boundary_violation", False)):
            findings.append({"code": "credential-or-session-export", "severity": "fatal", "item_id": identity})
        safe_row = {key: value for key, value in item.items() if key != "access_boundary_violation"}
        safe_row["access_boundary_passed"] = not bool(item.get("access_boundary_violation", False))
        rows.append(safe_row)
        identities.add(identity)
    counts = dict(sorted(Counter(row["status"] for row in rows).items()))
    blocking = sum(item["severity"] in {"major", "fatal"} for item in findings)
    return {
        "item_count": len(rows),
        "status_counts": counts,
        "items": rows,
        "findings": findings,
        "blocking_finding_count": blocking,
        "manifest_valid": blocking == 0,
        "manifest_digest": _digest(rows),
        "safety_boundary": [
            "Use only open-access or user-authorized institutional routes.",
            "Never request, read, store, export, or type passwords, one-time codes, cookies, tokens, or browser-session data.",
            "Stop for CAPTCHA, bot checks, security warnings, or other verification challenges.",
        ],
    }


def audit_literature_landscape(
    query_plan: dict[str, Any],
    records: list[dict[str, Any]],
    scoring_weights: dict[str, float] | None = None,
    strict_journal_scope: list[str] | None = None,
    focal_authors: list[str] | None = None,
    focal_affiliations: list[str] | None = None,
) -> dict[str, Any]:
    """Audit multi-source literature selection, scoring, scope, and citation independence."""
    if not isinstance(query_plan, dict) or not isinstance(records, list):
        raise ValueError("query_plan and records have invalid types")
    objective = str(query_plan.get("objective", "")).strip()
    queries = query_plan.get("queries", [])
    declared_sources = query_plan.get("sources", [])
    coverage_mode = str(query_plan.get("coverage_mode", "bounded")).strip()
    if not objective or not isinstance(queries, list) or not queries or not all(isinstance(value, str) and value.strip() for value in queries):
        raise ValueError("query_plan requires an objective and nonempty queries")
    if not isinstance(declared_sources, list) or not all(isinstance(value, str) and value.strip() for value in declared_sources):
        raise ValueError("query_plan.sources must be a string array")
    if coverage_mode not in {"bounded", "comprehensive", "recurring-monitor"}:
        raise ValueError("coverage_mode is unsupported")

    weights = dict(scoring_weights or {field: 1.0 for field in _LANDSCAPE_SCORE_FIELDS})
    if set(weights) != set(_LANDSCAPE_SCORE_FIELDS):
        raise ValueError("scoring_weights must define the six declared dimensions exactly")
    if any(not isinstance(value, (int, float)) or value < 0 for value in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError("scoring weights must be nonnegative and have a positive sum")

    strict_scope = {value.casefold().strip(): value.strip() for value in (strict_journal_scope or []) if value.strip()}
    declared_source_map = {value.casefold().strip(): value.strip() for value in declared_sources}
    focal_author_keys = {value.casefold().strip() for value in (focal_authors or []) if value.strip()}
    focal_affiliation_keys = {value.casefold().strip() for value in (focal_affiliations or []) if value.strip()}
    findings: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    seen_keys: dict[str, str] = {}
    duplicates: list[dict[str, str]] = []
    observed_source_map: dict[str, str] = {}

    for index, item in enumerate(records, start=1):
        if not isinstance(item, dict):
            raise ValueError("records must contain objects")
        identifier = str(item.get("id", "")).strip()
        title = str(item.get("title", "")).strip()
        source = str(item.get("source", "")).strip()
        source_level = str(item.get("source_level", "")).strip()
        doi = str(item.get("doi", "")).strip().lower()
        journal = str(item.get("journal", "")).strip()
        retraction_status = str(item.get("retraction_status", "unknown")).strip()
        if not identifier or not title or not source or source_level not in _SOURCE_LEVELS:
            raise ValueError(f"literature record {index} lacks identity, title, source, or valid source_level")
        scores = item.get("scores", {})
        if not isinstance(scores, dict) or set(scores) != set(_LANDSCAPE_SCORE_FIELDS):
            raise ValueError(f"literature record {identifier} must define all six scores")
        if any(not isinstance(scores[field], (int, float)) or not 0 <= float(scores[field]) <= 5 for field in _LANDSCAPE_SCORE_FIELDS):
            raise ValueError(f"literature record {identifier} scores must be within 0..5")

        title_key = re.sub(r"\W+", "", title.casefold())
        identity_key = f"doi:{doi}" if doi else f"title:{title_key}"
        if identity_key in seen_keys:
            duplicates.append({"record_id": identifier, "duplicate_of": seen_keys[identity_key]})
            findings.append({"code": "duplicate-literature-record", "severity": "major", "record_id": identifier, "duplicate_of": seen_keys[identity_key]})
        else:
            seen_keys[identity_key] = identifier
        observed_source_map.setdefault(source.casefold(), source)

        if strict_scope and journal.casefold() not in strict_scope:
            findings.append({"code": "journal-outside-strict-scope", "severity": "major", "record_id": identifier})
        if retraction_status.casefold() in {"retracted", "withdrawn"}:
            findings.append({"code": "retracted-or-withdrawn-record", "severity": "major", "record_id": identifier})

        authors = [str(value).strip() for value in item.get("authors", []) if str(value).strip()]
        affiliations = [str(value).strip() for value in item.get("affiliations", []) if str(value).strip()]
        author_overlap = sorted({value for value in authors if value.casefold() in focal_author_keys})
        affiliation_overlap = sorted({value for value in affiliations if value.casefold() in focal_affiliation_keys})
        citation_contexts = item.get("citation_contexts", [])
        if not isinstance(citation_contexts, list) or not all(isinstance(value, str) for value in citation_contexts):
            raise ValueError(f"literature record {identifier}.citation_contexts must be a string array")
        record_role = str(item.get("record_role", "candidate")).strip()
        if record_role not in {"candidate", "citing-work", "background"}:
            raise ValueError(f"literature record {identifier}.record_role is unsupported")
        independent_citing_work = record_role == "citing-work" and not author_overlap and not affiliation_overlap
        if record_role == "citing-work" and not citation_contexts:
            findings.append({"code": "citation-context-missing", "severity": "major", "record_id": identifier})

        weighted_score = sum(float(scores[field]) * float(weights[field]) for field in _LANDSCAPE_SCORE_FIELDS) / sum(float(value) for value in weights.values())
        normalized.append(
            {
                "id": identifier,
                "title": title,
                "doi": doi or None,
                "journal": journal or None,
                "source": source,
                "source_level": source_level,
                "record_role": record_role,
                "scores": {field: float(scores[field]) for field in _LANDSCAPE_SCORE_FIELDS},
                "weighted_score": round(weighted_score, 6),
                "retraction_status": retraction_status,
                "author_overlap": author_overlap,
                "affiliation_overlap": affiliation_overlap,
                "independent_citing_work": independent_citing_work,
                "citation_contexts": citation_contexts,
            }
        )

    missing_source_keys = sorted(set(declared_source_map) - set(observed_source_map))
    missing_declared_sources = [declared_source_map[key] for key in missing_source_keys]
    if missing_declared_sources:
        findings.append({"code": "declared-source-without-record", "severity": "major", "sources": missing_declared_sources})
    if coverage_mode in {"comprehensive", "recurring-monitor"} and len(declared_source_map) < 2:
        findings.append({"code": "multi-source-coverage-not-declared", "severity": "major", "record_id": None})
    if not records:
        findings.append({"code": "literature-records-empty", "severity": "major", "record_id": None})

    ranked = sorted(normalized, key=lambda row: (-row["weighted_score"], row["id"]))
    blocking = sum(item["severity"] in {"major", "fatal"} for item in findings)
    return {
        "query_plan": {
            "objective": objective,
            "queries": [value.strip() for value in queries],
            "sources": [value.strip() for value in declared_sources],
            "coverage_mode": coverage_mode,
        },
        "scoring_weights": {field: float(weights[field]) for field in _LANDSCAPE_SCORE_FIELDS},
        "record_count": len(ranked),
        "source_coverage": {"declared": sorted(declared_source_map.values()), "observed": sorted(observed_source_map.values()), "missing": missing_declared_sources},
        "strict_journal_scope": sorted(strict_scope.values()),
        "ranked_records": ranked,
        "duplicates": duplicates,
        "independent_citing_work_ids": [row["id"] for row in ranked if row["independent_citing_work"]],
        "findings": findings,
        "blocking_finding_count": blocking,
        "ready_for_synthesis": blocking == 0,
        "landscape_digest": _digest({"query_plan": query_plan, "weights": weights, "records": ranked, "scope": sorted(strict_scope)}),
        "limitations": [
            "Scores prioritize review and do not measure scientific truth, citation support, or journal quality.",
            "Independence is bounded to the supplied author and affiliation identities; scientific independence still requires expert review.",
            "Retrieval, retraction status, citation contexts, and journal scope must come from current authoritative or declared sources.",
        ],
    }


def audit_presentation_package(
    pptx_base64: str,
    expected_slide_count: int,
    asset_manifest: list[dict[str, Any]],
    qa_findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Reload a PPTX package and apply bounded structural and traceability checks."""
    if not isinstance(pptx_base64, str) or not isinstance(expected_slide_count, int) or expected_slide_count < 1:
        raise ValueError("pptx_base64 and expected_slide_count are invalid")
    if not isinstance(asset_manifest, list):
        raise ValueError("asset_manifest must be an array")
    qa_findings = list(qa_findings or [])
    try:
        payload = base64.b64decode(pptx_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("pptx_base64 is invalid") from exc
    findings: list[dict[str, Any]] = []
    slide_names: list[str] = []
    media_names: list[str] = []
    notes_names: list[str] = []
    visible_text: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "ppt/presentation.xml" not in names:
                findings.append({"code": "pptx-core-part-missing", "severity": "fatal", "location": "package"})
            slide_names = sorted(name for name in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", name))
            media_names = sorted(name for name in names if name.startswith("ppt/media/") and not name.endswith("/"))
            notes_names = sorted(name for name in names if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", name))
            for name in slide_names:
                try:
                    root = ET.fromstring(archive.read(name))
                except ET.ParseError:
                    findings.append({"code": "slide-xml-invalid", "severity": "fatal", "location": name})
                    continue
                texts = [node.text or "" for node in root.iter() if node.tag.endswith("}t")]
                slide_text = " ".join(texts).strip()
                visible_text.append(slide_text)
                if len(slide_text) > 900:
                    findings.append({"code": "slide-text-overload", "severity": "major", "location": name})
    except zipfile.BadZipFile as exc:
        raise ValueError("payload is not a valid PPTX ZIP package") from exc
    if len(slide_names) != expected_slide_count:
        findings.append({"code": "slide-count-mismatch", "severity": "major", "location": "package", "expected": expected_slide_count, "observed": len(slide_names)})
    asset_ids: set[str] = set()
    for index, item in enumerate(asset_manifest, start=1):
        if not isinstance(item, dict):
            raise ValueError("asset_manifest must contain objects")
        identifier = str(item.get("id", "")).strip()
        digest = str(item.get("sha256", "")).strip()
        source = str(item.get("source", "")).strip()
        slide = item.get("slide")
        if not identifier or identifier in asset_ids or not _SHA256_RE.fullmatch(digest) or not source or not isinstance(slide, int) or not 1 <= slide <= len(slide_names):
            findings.append({"code": "asset-manifest-row-invalid", "severity": "major", "location": f"asset-{index}"})
        asset_ids.add(identifier)
    for index, item in enumerate(qa_findings, start=1):
        if not isinstance(item, dict) or item.get("severity") not in {"high", "medium", "low"} or not str(item.get("issue", "")).strip():
            raise ValueError(f"qa finding {index} is invalid")
        if item["severity"] == "high" and not bool(item.get("resolved", False)):
            findings.append({"code": "unresolved-high-severity-qa", "severity": "major", "location": str(item.get("slide", "package"))})
    blocking = sum(item["severity"] in {"major", "fatal"} for item in findings)
    return {
        "package": {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "byte_count": len(payload),
            "slide_count": len(slide_names),
            "media_count": len(media_names),
            "notes_slide_count": len(notes_names),
        },
        "visible_text_character_count": sum(len(value) for value in visible_text),
        "asset_count": len(asset_manifest),
        "findings": findings,
        "blocking_finding_count": blocking,
        "ready_for_visual_review": blocking == 0,
        "limitations": [
            "Package reload and XML checks do not prove that crops, alignment, typography, color, or scientific legibility are acceptable; rendered visual review remains required.",
            "A valid presentation package does not validate the scientific claims presented on its slides.",
        ],
    }
