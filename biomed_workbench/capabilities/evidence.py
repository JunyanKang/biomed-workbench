"""Composable NCBI evidence workflows driven by structured Codex inputs."""

from __future__ import annotations

from typing import Any

from biomed_workbench.services.eutils import EUtilitiesClient, EUtilitiesError
from biomed_workbench.services.public_databases import (
    clinical_trial_records,
    preprint_record,
    pubchem_compound,
    rcsb_structure_records,
    resolve_citation_record,
)


def citation_record_resolution(doi: str) -> dict[str, Any]:
    """Resolve a DOI across independent bibliographic services."""
    return resolve_citation_record(doi)


def preprint_evidence(doi: str, server: str = "biorxiv") -> dict[str, Any]:
    """Retrieve all known versions of one bioRxiv or medRxiv preprint."""
    return preprint_record(doi, server)


def chemical_evidence(identifier: str, namespace: str = "name") -> dict[str, Any]:
    """Retrieve identity-critical PubChem compound records."""
    return pubchem_compound(identifier, namespace)


def clinical_trial_evidence(
    query: str | None = None,
    page_size: int = 100,
    filters: dict[str, Any] | None = None,
    max_records: int = 1000,
    advanced_query: str | None = None,
    include_full_record: bool = False,
) -> dict[str, Any]:
    """Retrieve design-aware ClinicalTrials.gov study records."""
    return clinical_trial_records(query, page_size, filters, max_records, advanced_query, include_full_record)


def structure_evidence(pdb_ids: list[str]) -> dict[str, Any]:
    """Retrieve entry-level RCSB PDB evidence for explicit identifiers."""
    return rcsb_structure_records(pdb_ids)


def _bounded_links(client: EUtilitiesClient, source: str, target: str, ids: tuple[str, ...], limit: int) -> tuple[dict[str, Any], str | None]:
    try:
        result = client.link(source, target, ids)
    except EUtilitiesError as exc:
        return {"ids": [], "total": 0, "link_names": []}, str(exc)
    return {
        "ids": list(result.links[:limit]),
        "total": len(result.links),
        "link_names": list(result.link_names),
    }, None


def literature_evidence(query: str, max_records: int = 10, database: str = "pubmed") -> dict[str, Any]:
    if database not in {"pubmed", "pmc"}:
        raise ValueError("literature database must be pubmed or pmc")
    if not 1 <= max_records <= 100:
        raise ValueError("max_records must be 1..100")
    client = EUtilitiesClient()
    found = client.search(database, query, retmax=max_records)
    summarized = client.summary(database, found.ids) if found.ids else None
    return {
        "database": database,
        "query": query,
        "query_translation": found.query_translation,
        "count": found.count,
        "returned_ids": list(found.ids),
        "records": list(summarized.records) if summarized else [],
        "provenance": {"service": "NCBI Entrez E-utilities", "operations": ["esearch", "esummary"]},
    }


def gene_evidence(gene: str, organism: str = "human", max_links: int = 25) -> dict[str, Any]:
    if not gene.strip() or not organism.strip():
        raise ValueError("gene and organism must not be empty")
    if not 1 <= max_links <= 500:
        raise ValueError("max_links must be 1..500")
    client = EUtilitiesClient()
    query = f"{gene}[Gene Name] AND {organism}[Organism]"
    found = client.search("gene", query, retmax=5, sort="relevance")
    summarized = client.summary("gene", found.ids) if found.ids else None
    linked: dict[str, Any] = {}
    warnings = []
    for target in ("protein", "clinvar", "pubmed"):
        payload, warning = _bounded_links(client, "gene", target, found.ids, max_links) if found.ids else ({"ids": [], "total": 0, "link_names": []}, None)
        linked[target] = payload
        if warning:
            warnings.append(f"{target}: {warning}")
    return {
        "query": query,
        "match_count": found.count,
        "gene_records": list(summarized.records) if summarized else [],
        "linked": linked,
        "warnings": warnings,
        "provenance": {"service": "NCBI Entrez E-utilities", "operations": ["esearch", "esummary", "elink"]},
    }


def variant_evidence(query: str, max_records: int = 10, max_links: int = 25) -> dict[str, Any]:
    if not query.strip() or not 1 <= max_records <= 100 or not 1 <= max_links <= 500:
        raise ValueError("query must be nonempty and limits must be bounded")
    client = EUtilitiesClient()
    found = client.search("clinvar", query, retmax=max_records)
    summarized = client.summary("clinvar", found.ids) if found.ids else None
    linked: dict[str, Any] = {}
    warnings = []
    for target in ("gene", "pubmed"):
        payload, warning = _bounded_links(client, "clinvar", target, found.ids, max_links) if found.ids else ({"ids": [], "total": 0, "link_names": []}, None)
        linked[target] = payload
        if warning:
            warnings.append(f"{target}: {warning}")
    return {
        "query": query,
        "match_count": found.count,
        "variant_records": list(summarized.records) if summarized else [],
        "linked": linked,
        "warnings": warnings,
        "provenance": {"service": "NCBI Entrez E-utilities", "operations": ["esearch", "esummary", "elink"]},
        "limitations": ["Database classifications must be interpreted in the submitted condition, review status, and assertion context."],
    }
