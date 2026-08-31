"""Whitelisted, typed discovery operations for public life-science resources."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from .public_databases import PublicDatabaseError, PublicJSONClient, _clean_text


PUBLIC_RESEARCH_EVIDENCE_CONTRACT_VERSION = "typed-public-evidence-v1-observed-2026-08-31"


def probe_public_research_evidence_contract() -> str:
    return PUBLIC_RESEARCH_EVIDENCE_CONTRACT_VERSION


@dataclass(frozen=True)
class SourceOperation:
    source: str
    operation: str
    base_url: str
    path: str
    record_path: tuple[str, ...]
    query_parameter: str
    fixed_parameters: dict[str, Any]
    documentation: str
    evidence_role: str
    limitations: tuple[str, ...]


_OPERATIONS = {
    ("gwas-catalog", "studies-by-trait"): SourceOperation(
        "gwas-catalog", "studies-by-trait", "https://www.ebi.ac.uk", "/gwas/rest/api/v2/studies",
        ("_embedded", "studies"), "efo_trait", {"size": 20},
        "https://www.ebi.ac.uk/gwas/rest/api/v2/docs", "human genetic association discovery",
        ("Curated top associations and study metadata are not complete summary statistics or causal evidence.",),
    ),
    ("gwas-catalog", "associations-by-gene"): SourceOperation(
        "gwas-catalog", "associations-by-gene", "https://www.ebi.ac.uk", "/gwas/rest/api/v2/associations",
        ("_embedded", "associations"), "mapped_gene", {"size": 20},
        "https://www.ebi.ac.uk/gwas/rest/api/v2/docs", "human genetic association discovery",
        ("Mapped or nearby genes are hypotheses, not established effector genes or mechanisms.",),
    ),
    ("chembl", "molecule-search"): SourceOperation(
        "chembl", "molecule-search", "https://www.ebi.ac.uk", "/chembl/api/data/molecule/search.json",
        ("molecules",), "q", {"limit": 20},
        "https://chembl.gitbook.io/chembl-interface-documentation/web-services/chembl-data-web-services", "compound identity discovery",
        ("Name search does not establish a unique active chemical form, target engagement, efficacy, or safety.",),
    ),
    ("chembl", "activities-by-molecule"): SourceOperation(
        "chembl", "activities-by-molecule", "https://www.ebi.ac.uk", "/chembl/api/data/activity.json",
        ("activities",), "molecule_chembl_id", {"limit": 20},
        "https://chembl.gitbook.io/chembl-interface-documentation/web-services/chembl-data-web-services", "bioactivity discovery",
        ("Activity records differ in assay, endpoint, units and confidence and cannot be pooled without harmonization.",),
    ),
    ("pride", "projects"): SourceOperation(
        "pride", "projects", "https://www.ebi.ac.uk", "/pride/ws/archive/v2/projects",
        ("_embedded", "projects"), "keyword", {"pageSize": 20},
        "https://www.ebi.ac.uk/pride/ws/archive/v2/docs/api-guide.html", "proteomics dataset discovery",
        ("Project metadata does not establish that raw files, design, organism, or processing are suitable for reuse.",),
    ),
    ("biostudies", "studies"): SourceOperation(
        "biostudies", "studies", "https://www.ebi.ac.uk", "/biostudies/api/v1/search",
        ("hits",), "query", {"page": 1, "pageSize": 20},
        "https://www.ebi.ac.uk/biostudies/help", "multi-omics dataset discovery",
        ("Search hits require accession-level review of files, design, consent, species and processing.",),
    ),
    ("encode", "experiments"): SourceOperation(
        "encode", "experiments", "https://www.encodeproject.org", "/search/",
        ("@graph",), "searchTerm", {"type": "Experiment", "limit": 20, "format": "json"},
        "https://www.encodeproject.org/help/rest-api/", "functional genomics dataset discovery",
        ("Portal experiment metadata must be reviewed for assay, biosample, control, audit status, assembly and file processing level.",),
    ),
    ("human-protein-atlas", "gene"): SourceOperation(
        "human-protein-atlas", "gene", "https://www.proteinatlas.org", "/api/search_download.php",
        (), "search", {"format": "json", "columns": "g,gs,tissue", "compress": "no"},
        "https://www.proteinatlas.org/about/download", "human expression context",
        ("Atlas expression and antibody evidence are contextual observations, not proof of function, mechanism or disease causality.",),
    ),
    ("mgnify", "studies"): SourceOperation(
        "mgnify", "studies", "https://www.ebi.ac.uk", "/metagenomics/api/v1/studies",
        ("data",), "search", {"page_size": 20},
        "https://www.ebi.ac.uk/metagenomics/api/v1/docs/", "microbiome dataset discovery",
        ("Study discovery does not establish comparable extraction, marker, sequencing, host depletion, taxonomy or biome definitions.",),
    ),
}


def _records_at(payload: dict[str, Any], path: tuple[str, ...]) -> list[Any]:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise PublicDatabaseError("public evidence response lacks the registered record container")
        value = value[key]
    if path == () and isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        raise PublicDatabaseError("public evidence record container is not a list")
    return value


def _compact_record(value: Any, *, depth: int = 0) -> Any:
    if depth >= 3:
        return None
    if isinstance(value, dict):
        result = {}
        for key in sorted(value)[:40]:
            compact = _compact_record(value[key], depth=depth + 1)
            if compact not in (None, "", [], {}):
                result[str(key)[:120]] = compact
        return result
    if isinstance(value, list):
        return [_compact_record(item, depth=depth + 1) for item in value[:20]]
    if isinstance(value, str):
        return _clean_text(value, limit=2000)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _clean_text(value, limit=500)


def query_public_research_evidence(
    source: str,
    operation: str,
    query: str,
    max_records: int = 20,
    *,
    client: PublicJSONClient | None = None,
) -> dict[str, Any]:
    """Run one source-specific public query with no caller-controlled URL."""
    spec = _OPERATIONS.get((source, operation))
    if spec is None:
        raise ValueError("source and operation are not a registered public-evidence query")
    normalized = query.strip()
    if not 1 <= len(normalized) <= 300 or any(ord(char) < 32 for char in normalized):
        raise ValueError("query must contain 1..300 printable characters")
    if not 1 <= max_records <= 100:
        raise ValueError("max_records must be within 1..100")
    params = {**spec.fixed_parameters, spec.query_parameter: normalized}
    for key in ("size", "limit", "pageSize", "page_size"):
        if key in params:
            params[key] = min(max_records, 100)
    # Scientific discovery requests fail visibly instead of silently multiplying
    # network calls. The host can decide whether one explicit retry is warranted.
    active = client or PublicJSONClient(retries=0)
    if source in {"human-protein-atlas", "pride"}:
        raw, transport = active.get_array_with_metadata(spec.base_url, spec.path, params)
    else:
        payload, transport = active.get_with_metadata(spec.base_url, spec.path, params)
        raw = _records_at(payload, spec.record_path)
    records = [_compact_record(item) for item in raw[:max_records]]
    return {
        "source": source,
        "operation": operation,
        "query": normalized,
        "evidence_role": spec.evidence_role,
        "returned_count": len(records),
        "records_truncated": len(raw) > max_records,
        "records": records,
        "provenance": {
            "contract_version": PUBLIC_RESEARCH_EVIDENCE_CONTRACT_VERSION,
            "documentation": spec.documentation,
            "transport": transport,
        },
        "limitations": list(spec.limitations),
    }


def synthesize_public_evidence(
    question: str,
    evidence_records: list[dict[str, Any]],
    expected_entity: str | None = None,
) -> dict[str, Any]:
    """Normalize outputs from public-database clients into a scientific evidence table."""
    normalized_question = question.strip()
    if not 5 <= len(normalized_question) <= 2000 or not isinstance(evidence_records, list) or not evidence_records:
        raise ValueError("question and nonempty evidence_records are required")
    if len(evidence_records) > 500:
        raise ValueError("evidence_records may contain at most 500 records")
    entity = expected_entity.strip() if isinstance(expected_entity, str) and expected_entity.strip() else None
    rows, concerns = [], []
    for index, record in enumerate(evidence_records, start=1):
        required = {"source", "record_id", "evidence_type", "observation", "source_url"}
        if not isinstance(record, dict) or not required <= set(record):
            raise ValueError("every evidence record requires source, record_id, evidence_type, observation, and source_url")
        source = str(record["source"]).strip()
        identifier = str(record["record_id"]).strip()
        evidence_type = str(record["evidence_type"]).strip().lower()
        observation = str(record["observation"]).strip()
        url = str(record["source_url"]).strip()
        record_entity = str(record.get("entity", "")).strip() or None
        if not source or not identifier or not observation or not re.fullmatch(r"https://[^\s]+", url):
            raise ValueError("evidence identifiers, observation, and HTTPS source URL must be valid")
        if entity and record_entity and record_entity.casefold() != entity.casefold():
            concerns.append({"record_id": identifier, "code": "ENTITY_MISMATCH", "detail": f"record entity {record_entity} differs from {entity}"})
        rows.append({
            "index": index, "source": source, "record_id": identifier,
            "evidence_type": evidence_type, "entity": record_entity,
            "observation": observation, "source_url": url,
            "supports": str(record.get("supports", "context")).strip().lower(),
        })
    source_count = len({row["source"] for row in rows})
    return {
        "question": normalized_question,
        "expected_entity": entity,
        "record_count": len(rows),
        "source_count": source_count,
        "evidence_table": rows,
        "concerns": concerns,
        "usable_for_interpretation": not concerns,
        "scientific_summary": (
            f"{len(rows)} records from {source_count} public sources were normalized; interpretation must follow evidence type and study design."
        ),
        "next_review": [
            "Confirm entity, species, assembly or chemical identity before combining records.",
            "Separate direct project observations, public association, expression context, perturbation evidence and mechanistic evidence.",
            "Resolve contradictions and assess whether missing records reflect absence of evidence or an incomplete query.",
        ],
    }
