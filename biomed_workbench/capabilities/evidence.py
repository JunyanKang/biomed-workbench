"""Composable NCBI evidence workflows driven by structured Codex inputs."""

from __future__ import annotations

from typing import Any

from biomed_workbench.services.eutils import EUtilitiesClient, EUtilitiesError


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
