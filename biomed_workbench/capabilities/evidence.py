"""Composable public-database workflows driven by structured Codex inputs."""

from __future__ import annotations

import re
from typing import Any

from biomed_workbench.services.eutils import EUtilitiesClient, EUtilitiesError
from biomed_workbench.services.public_databases import (
    alphafold_structure_records,
    clinical_trial_records,
    preprint_record,
    pubchem_compound,
    rcsb_ligand_records,
    rcsb_polymer_entity_records,
    rcsb_structure_search,
    rcsb_structure_records,
    resolve_citation_record,
    ncbi_gene_orthologs,
    enrichr_library_catalog,
    enrichr_gene_set_library,
    ensembl_gene_lookup,
    archs4_expression_atlas,
    hpo_term_records,
    iupred2a_disorder_prediction,
    quickgo_term_records,
    reactome_pathway_record,
    reactome_gene_set_overrepresentation,
    opentargets_target_disease_evidence as fetch_opentargets_target_disease_evidence,
    gnomad_gene_constraint_evidence as fetch_gnomad_gene_constraint_evidence,
    uniprot_protein_record,
    uniprot_to_ensembl_gene_mapping,
    string_protein_interaction_evidence as fetch_string_protein_interaction_evidence,
)


def citation_record_resolution(doi: str) -> dict[str, Any]:
    """Resolve a DOI across independent bibliographic services."""
    return resolve_citation_record(doi)


def gene_set_library_membership(library_name: str, max_terms: int = 5000, max_members_per_term: int = 10000) -> dict[str, Any]:
    """Retrieve a bounded public gene-set snapshot for explicit downstream analysis."""
    return enrichr_gene_set_library(library_name, max_terms, max_members_per_term)


def archs4_expression_evidence(
    gene_symbol: str,
    species: str = "human",
    atlas: str = "tissue",
    max_records: int = 50,
) -> dict[str, Any]:
    """Retrieve bounded public tissue or cell-line expression context for one gene."""
    return archs4_expression_atlas(gene_symbol, species, atlas, max_records)


def hpo_term_evidence(hpo_ids: list[str]) -> dict[str, Any]:
    """Resolve declared HPO term identifiers through the public ontology service."""
    return hpo_term_records(hpo_ids)


def quickgo_term_evidence(go_ids: list[str]) -> dict[str, Any]:
    """Resolve declared Gene Ontology terms through the QuickGO ontology service."""
    return quickgo_term_records(go_ids)


def uniprot_protein_evidence(accession: str) -> dict[str, Any]:
    """Retrieve bounded identity-critical evidence for one UniProtKB protein."""
    return uniprot_protein_record(accession)


def uniprot_to_ensembl_evidence(accessions: list[str], max_polls: int = 12) -> dict[str, Any]:
    """Map bounded UniProt accessions to Ensembl gene IDs with explicit loss states."""
    return uniprot_to_ensembl_gene_mapping(accessions, max_polls)


def ensembl_gene_evidence(gene_symbol: str, species: str = "human") -> dict[str, Any]:
    """Resolve one explicit gene symbol through the bounded Ensembl REST lookup."""
    return ensembl_gene_lookup(gene_symbol, species)


def reactome_pathway_evidence(pathway_id: str) -> dict[str, Any]:
    """Retrieve one exact Reactome pathway identity record."""
    return reactome_pathway_record(pathway_id)


def reactome_overrepresentation_evidence(identifiers: list[str], max_pathways: int = 100) -> dict[str, Any]:
    """Retrieve bounded Reactome server-side overrepresentation context."""
    return reactome_gene_set_overrepresentation(identifiers, max_pathways)


def opentargets_target_disease_evidence(
    ensembl_gene_id: str, disease_id: str, data_types: list[str] | None = None, max_records: int = 100
) -> dict[str, Any]:
    """Retrieve bounded source-resolved Open Targets target-disease evidence."""
    return fetch_opentargets_target_disease_evidence(ensembl_gene_id, disease_id, data_types, max_records)


def gnomad_gene_constraint_evidence(gene_symbol: str) -> dict[str, Any]:
    """Retrieve fixed-field gnomAD GRCh38 gene-constraint context."""
    return fetch_gnomad_gene_constraint_evidence(gene_symbol)


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


def structure_search(
    text: str | None = None,
    organism: str | None = None,
    taxonomy_id: int | None = None,
    uniprot_accession: str | None = None,
    experimental_method: str | None = None,
    max_resolution: float | None = None,
    ligand_comp_id: str | None = None,
    include_computed_models: bool = False,
    max_records: int = 100,
) -> dict[str, Any]:
    """Search RCSB entries with count-verified scientific filters."""
    return rcsb_structure_search(
        text, organism, taxonomy_id, uniprot_accession, experimental_method,
        max_resolution, ligand_comp_id, include_computed_models, max_records,
    )


def structure_polymer_entities(
    pdb_id: str,
    entity_ids: list[str] | None = None,
    include_sequences: bool = False,
) -> dict[str, Any]:
    """Retrieve RCSB polymer entities and optional canonical sequences."""
    return rcsb_polymer_entity_records(pdb_id, entity_ids, include_sequences)


def structure_ligands(pdb_id: str, max_ligands: int = 25) -> dict[str, Any]:
    """Retrieve bound nonpolymer entities and chemical-component identity."""
    return rcsb_ligand_records(pdb_id, max_ligands)


def alphafold_structure_evidence(
    uniprot_accessions: list[str],
    include_sequence: bool = False,
) -> dict[str, Any]:
    """Retrieve versioned AlphaFold DB model and confidence metadata."""
    return alphafold_structure_records(uniprot_accessions, include_sequence)


def protein_interaction_network_evidence(
    identifiers: list[str],
    species: int,
    network_type: str = "functional",
    required_score: int = 700,
    add_nodes: int = 0,
) -> dict[str, Any]:
    """Retrieve a version-pinned STRING association or physical-evidence network."""
    return fetch_string_protein_interaction_evidence(
        identifiers, species, network_type, required_score, add_nodes
    )


def protein_disorder_evidence(
    uniprot_accessions: list[str],
    prediction_type: str = "long",
    score_threshold: float = 0.5,
    minimum_span_length: int = 20,
) -> dict[str, Any]:
    """Retrieve accession-bound IUPred2A score profiles and transparent threshold spans."""
    return iupred2a_disorder_prediction(
        uniprot_accessions, prediction_type, score_threshold, minimum_span_length
    )


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


def resolve_gene_identifier(
    gene: str,
    organism: str = "human",
    *,
    client: EUtilitiesClient | None = None,
) -> dict[str, Any]:
    """Resolve an exact, species-scoped gene symbol to one stable NCBI Gene ID.

    This is deliberately stricter than an evidence search.  It exposes all
    candidates and only yields a reusable identifier when the exact symbol and
    declared organism identify one current record.
    """
    symbol = gene.strip()
    declared_organism = organism.strip()
    if not symbol or not declared_organism:
        raise ValueError("gene and organism must not be empty")
    active_client = client or EUtilitiesClient()
    query = f"{symbol}[Gene Name] AND {declared_organism}[Organism]"
    found = active_client.search("gene", query, retmax=10, sort="relevance")
    summarized = active_client.summary("gene", found.ids) if found.ids else None
    records = list(summarized.records) if summarized else []
    exact_symbol = symbol.casefold()
    exact_organism = declared_organism.casefold()

    def organism_matches(record: dict[str, Any]) -> bool:
        organism_record = record.get("organism", {})
        if not isinstance(organism_record, dict):
            return False
        values = {
            str(organism_record.get("taxid", "")).casefold(),
            str(organism_record.get("commonname", "")).casefold(),
            str(organism_record.get("scientificname", "")).casefold(),
        }
        return exact_organism in values

    exact = [
        record
        for record in records
        if organism_matches(record)
        and (
            str(record.get("name", "")).casefold() == exact_symbol
            or str(record.get("nomenclaturesymbol", "")).casefold() == exact_symbol
        )
    ]
    candidates = [
        {
            "gene_id": str(record.get("uid", "")),
            "symbol": str(record.get("name") or record.get("nomenclaturesymbol") or ""),
            "description": str(record.get("description", "")),
            "taxon_id": str(record.get("organism", {}).get("taxid", "")),
            "scientific_name": str(record.get("organism", {}).get("scientificname", "")),
        }
        for record in records
        if str(record.get("uid", "")).isdigit()
    ]
    resolved = None
    if len(exact) == 1 and str(exact[0].get("uid", "")).isdigit():
        record = exact[0]
        resolved = {
            "gene_id": str(record["uid"]),
            "symbol": str(record.get("name") or record.get("nomenclaturesymbol") or symbol),
            "taxon_id": str(record.get("organism", {}).get("taxid", "")),
            "scientific_name": str(record.get("organism", {}).get("scientificname", "")),
            "description": str(record.get("description", "")),
        }
    status = "resolved" if resolved else ("ambiguous" if len(exact) > 1 else "not_found")
    return {
        "query": query,
        "match_count": found.count,
        "resolution_status": status,
        "resolved": resolved,
        "candidates": candidates,
        "provenance": {
            "service": "NCBI Entrez E-utilities",
            "operations": ["esearch", "esummary"],
            "selection_policy": "exact current gene or nomenclature symbol and exact declared organism; one candidate required",
        },
        "warnings": [] if resolved else ["No reusable Gene ID was emitted; review the returned candidates and declared organism before downstream analysis."],
    }


def gene_ortholog_evidence(gene_id: str, target_taxon_id: int, max_records: int = 100) -> dict[str, Any]:
    """Retrieve NCBI Gene ortholog records without converting them into functional claims."""
    return ncbi_gene_orthologs(gene_id, target_taxon_id, max_records)


def gene_set_library_catalog(category_id: int | None = None, max_libraries: int = 500) -> dict[str, Any]:
    """Discover bounded Enrichr gene-set library metadata before selecting a resource."""
    return enrichr_library_catalog(category_id, max_libraries)


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


def dbsnp_rsid_evidence(rsid: str) -> dict[str, Any]:
    """Retrieve one dbSNP reference-variant summary without clinical interpretation."""
    normalized = str(rsid).strip().lower()
    if not re.fullmatch(r"rs[1-9][0-9]*", normalized):
        raise ValueError("rsid must use canonical rs123 identifier form")
    client = EUtilitiesClient()
    found = client.search("snp", normalized, retmax=5)
    summarized = client.summary("snp", found.ids) if found.ids else None
    exact = [record for record in (summarized.records if summarized else ()) if str(record.get("snp_id") or record.get("uid") or "").lower() == normalized]
    return {
        "rsid": normalized,
        "match_count": found.count,
        "records": exact or list(summarized.records) if summarized else [],
        "resolution_status": "resolved" if len(exact) == 1 else ("not_found" if not found.ids else "review_required"),
        "provenance": {"service": "NCBI Entrez E-utilities", "database": "snp", "operations": ["esearch", "esummary"], "query_translation": found.query_translation},
        "limitations": ["A dbSNP reference record does not establish clinical significance, disease causality, allele frequency, genotype, genome-build harmonization, or sample-level variant validity."],
    }
