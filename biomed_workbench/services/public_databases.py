"""Bounded clients for public biomedical evidence databases.

The clients intentionally expose small, database-specific operations instead of
an arbitrary URL fetcher.  That keeps redirects, response size, identifiers,
pagination, and provenance inspectable at the module boundary.
"""

from __future__ import annotations

import csv
import json
import io
import math
import re
import time
from dataclasses import dataclass
from http.client import IncompleteRead
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

from .credentials import optional_credential

CROSSREF_CONTRACT_VERSION = "rest-v1-observed-2026-07-13"
EUROPE_PMC_CONTRACT_VERSION = "rest-observed-2026-07-13"
BIORXIV_CONTRACT_VERSION = "details-v1-observed-2026-07-13"
PUBCHEM_CONTRACT_VERSION = "pug-rest-observed-2026-07-13"
CLINICAL_TRIALS_CONTRACT_VERSION = "api-v2-observed-2026-07-13"
RCSB_CONTRACT_VERSION = "data-rest-v1-observed-2026-07-13"
RCSB_SEARCH_CONTRACT_VERSION = "search-v2-observed-2026-07-13"
ALPHAFOLD_CONTRACT_VERSION = "prediction-api-observed-2026-07-14"
ENRICHR_CONTRACT_VERSION = "dataset-statistics-observed-2026-07-23"
ENRICHR_LIBRARY_CONTRACT_VERSION = "gene-set-library-json-observed-2026-07-23"
ARCHS4_EXPRESSION_CONTRACT_VERSION = "expression-tissue-v1-observed-2026-07-23"
ENSEMBL_GENE_LOOKUP_CONTRACT_VERSION = "lookup-symbol-v1-observed-2026-07-23"
REACTOME_PATHWAY_CONTRACT_VERSION = "content-query-pathway-v1-observed-2026-07-23"
OPENTARGETS_EVIDENCE_CONTRACT_VERSION = "disease-evidences-v4-observed-2026-07-23"
GNOMAD_GENE_CONSTRAINT_CONTRACT_VERSION = "gene-constraint-grch38-observed-2026-07-24"
CBIOPORTAL_STUDY_CONTRACT_VERSION = "study-record-v1-observed-2026-07-24"
IUPRED2A_CONTRACT_VERSION = "rest-accession-json-v1-observed-2026-07-24"
STRING_CONTRACT_VERSION = "api-v12.0-observed-2026-08-02"
STRING_BASE_URL = "https://version-12-0.string-db.org"

_MAX_RESPONSE_BYTES = 20 * 1024 * 1024
_MAX_REQUEST_BYTES = 1024 * 1024
_DOI_RE = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)
_PDB_RE = re.compile(r"^[0-9][A-Za-z0-9]{3}$")
_UNIPROT_ACCESSION_RE = re.compile(
    r"^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})(?:-[1-9][0-9]*)?$",
    re.IGNORECASE,
)
_NCT_RE = re.compile(r"^NCT\d{8}$", re.IGNORECASE)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CT_PHASES = frozenset({"NA", "EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4"})
_CT_STATUSES = frozenset(
    {
        "ACTIVE_NOT_RECRUITING", "COMPLETED", "ENROLLING_BY_INVITATION", "NOT_YET_RECRUITING",
        "RECRUITING", "SUSPENDED", "TERMINATED", "WITHDRAWN", "AVAILABLE", "NO_LONGER_AVAILABLE",
        "TEMPORARILY_NOT_AVAILABLE", "APPROVED_FOR_MARKETING", "WITHHELD", "UNKNOWN",
    }
)
_CT_STUDY_TYPES = frozenset({"INTERVENTIONAL", "OBSERVATIONAL", "EXPANDED_ACCESS"})
_CT_SPONSOR_CLASSES = frozenset({"NIH", "FED", "OTHER_GOV", "INDIV", "INDUSTRY", "NETWORK", "AMBIG", "OTHER", "UNKNOWN"})
_RCSB_EXPERIMENTAL_METHODS = frozenset(
    {
        "ELECTRON CRYSTALLOGRAPHY", "ELECTRON MICROSCOPY", "EPR", "FIBER DIFFRACTION",
        "FLUORESCENCE TRANSFER", "INFRARED SPECTROSCOPY", "NEUTRON DIFFRACTION",
        "POWDER DIFFRACTION", "SOLID-STATE NMR", "SOLUTION NMR", "SOLUTION SCATTERING",
        "THEORETICAL MODEL", "X-RAY DIFFRACTION",
    }
)
_ALLOWED_HOSTS = frozenset(
    {
        "api.crossref.org",
        "www.ebi.ac.uk",
        "api.biorxiv.org",
        "pubchem.ncbi.nlm.nih.gov",
        "clinicaltrials.gov",
        "data.rcsb.org",
        "search.rcsb.org",
        "alphafold.ebi.ac.uk",
        "api.ncbi.nlm.nih.gov",
        "maayanlab.cloud",
        "ontology.jax.org",
        "rest.uniprot.org",
        "rest.ensembl.org",
        "reactome.org",
        "api.platform.opentargets.org",
        "gnomad.broadinstitute.org",
        "www.cbioportal.org",
        "iupred2a.elte.hu",
        "version-12-0.string-db.org",
    }
)


class PublicDatabaseError(RuntimeError):
    """A bounded, secret-free public database request or schema failure."""


def probe_enrichr_contract() -> str:
    """Expose the pinned Enrichr response contract for compatibility checks."""
    return ENRICHR_CONTRACT_VERSION


def probe_enrichr_library_contract() -> str:
    """Expose the observed Enrichr gene-set membership response contract."""
    return ENRICHR_LIBRARY_CONTRACT_VERSION


def probe_archs4_expression_contract() -> str:
    """Expose the observed ARCHS4 tissue and cell-line expression contract."""
    return ARCHS4_EXPRESSION_CONTRACT_VERSION


def probe_ensembl_gene_lookup_contract() -> str:
    """Expose the observed Ensembl lookup-by-symbol response contract."""
    return ENSEMBL_GENE_LOOKUP_CONTRACT_VERSION


def probe_reactome_pathway_contract() -> str:
    """Expose the observed Reactome stable-pathway record contract."""
    return REACTOME_PATHWAY_CONTRACT_VERSION


def probe_opentargets_evidence_contract() -> str:
    """Expose the observed Open Targets disease-evidence GraphQL contract."""
    return OPENTARGETS_EVIDENCE_CONTRACT_VERSION


HPO_TERM_CONTRACT_VERSION = "term-v1-observed-2026-07-23"
UNIPROT_RECORD_CONTRACT_VERSION = "uniprotkb-json-v1-observed-2026-07-23"
UNIPROT_TO_ENSEMBL_MAPPING_CONTRACT_VERSION = "idmapping-uniprot-to-ensembl-v1-observed-2026-07-23"
QUICKGO_TERM_CONTRACT_VERSION = "ontology-go-terms-v1-observed-2026-07-23"


def probe_hpo_term_contract() -> str:
    """Expose the observed HPO term record contract."""
    return HPO_TERM_CONTRACT_VERSION


def probe_uniprot_record_contract() -> str:
    """Expose the observed UniProtKB JSON record contract."""
    return UNIPROT_RECORD_CONTRACT_VERSION


def probe_uniprot_to_ensembl_mapping_contract() -> str:
    """Expose the observed UniProt asynchronous mapping contract."""
    return UNIPROT_TO_ENSEMBL_MAPPING_CONTRACT_VERSION


def probe_quickgo_term_contract() -> str:
    """Expose the observed QuickGO term response contract."""
    return QUICKGO_TERM_CONTRACT_VERSION


def probe_iupred2a_contract() -> str:
    """Expose the observed accession-based IUPred2A JSON contract."""
    return IUPRED2A_CONTRACT_VERSION


@dataclass(frozen=True)
class HTTPResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


Transport = Callable[[str, Mapping[str, str], float], HTTPResponse]
PostTransport = Callable[[str, Mapping[str, str], bytes, float], HTTPResponse]


def _default_transport(url: str, headers: Mapping[str, str], timeout: float) -> HTTPResponse:
    request = Request(url, headers=dict(headers), method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(body) > _MAX_RESPONSE_BYTES:
                raise PublicDatabaseError("public database response exceeded the 20 MiB safety limit")
            return HTTPResponse(response.status, dict(response.headers.items()), body)
    except HTTPError as exc:
        return HTTPResponse(exc.code, dict(exc.headers.items()), exc.read(64 * 1024))
    except (IncompleteRead, URLError, TimeoutError, OSError) as exc:
        raise PublicDatabaseError(f"public database request failed: {type(exc).__name__}") from None


def _default_post_transport(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> HTTPResponse:
    request = Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            response_body = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(response_body) > _MAX_RESPONSE_BYTES:
                raise PublicDatabaseError("public database response exceeded the 20 MiB safety limit")
            return HTTPResponse(response.status, dict(response.headers.items()), response_body)
    except HTTPError as exc:
        return HTTPResponse(exc.code, dict(exc.headers.items()), exc.read(64 * 1024))
    except (IncompleteRead, URLError, TimeoutError, OSError) as exc:
        raise PublicDatabaseError(f"public database request failed: {type(exc).__name__}") from None


def _clean_text(value: Any, *, limit: int = 20_000) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text[:limit] if text else None


def _require_doi(value: str) -> str:
    normalized = value.strip()
    if normalized.lower().startswith("https://doi.org/"):
        normalized = normalized[16:]
    if not _DOI_RE.fullmatch(normalized):
        raise ValueError("DOI is not syntactically valid")
    return normalized.lower()


def _require_pdb_id(value: str) -> str:
    normalized = value.strip().upper()
    if not _PDB_RE.fullmatch(normalized):
        raise ValueError("PDB identifier must contain four alphanumeric characters and start with a digit")
    return normalized


def ncbi_gene_orthologs(
    gene_id: str, target_taxon_id: int, max_records: int = 100, *, client: PublicJSONClient | None = None
) -> dict[str, Any]:
    """Retrieve bounded NCBI Datasets ortholog records for one stable Gene ID."""
    normalized_gene = gene_id.strip()
    if not re.fullmatch(r"[1-9][0-9]*", normalized_gene):
        raise ValueError("gene_id must be a positive NCBI Gene identifier")
    if not 1 <= target_taxon_id <= 9_999_999 or not 1 <= max_records <= 100:
        raise ValueError("target_taxon_id or max_records is outside the bounded contract")
    ncbi_api_key = optional_credential("NCBI_API_KEY")
    payload, transport = (client or PublicJSONClient()).get_with_metadata(
        "https://api.ncbi.nlm.nih.gov",
        f"/datasets/v2/gene/id/{normalized_gene}/orthologs",
        api_key=ncbi_api_key,
    )
    reports = payload.get("reports")
    if not isinstance(reports, list):
        raise PublicDatabaseError("NCBI Datasets ortholog response lacks reports")
    source = None
    orthologs = []
    for item in reports:
        gene = item.get("gene") if isinstance(item, dict) else None
        if not isinstance(gene, dict) or not isinstance(gene.get("gene_id"), str):
            continue
        if gene["gene_id"] == normalized_gene:
            source = gene
        elif str(gene.get("tax_id", "")) == str(target_taxon_id):
            orthologs.append({
                "gene_id": gene["gene_id"], "symbol": _clean_text(gene.get("symbol")),
                "tax_id": str(gene.get("tax_id")), "taxname": _clean_text(gene.get("taxname")),
                "ensembl_gene_ids": sorted(str(value) for value in gene.get("ensembl_gene_ids", []) if isinstance(value, str)),
                "type": _clean_text(gene.get("type")),
            })
    if source is None:
        raise PublicDatabaseError("NCBI Datasets response did not preserve the requested source Gene ID")
    orthologs.sort(key=lambda record: (record["gene_id"], record["symbol"] or ""))
    return {"source": {"gene_id": source["gene_id"], "symbol": _clean_text(source.get("symbol")), "tax_id": str(source.get("tax_id", "")), "taxname": _clean_text(source.get("taxname")), "ensembl_gene_ids": sorted(str(value) for value in source.get("ensembl_gene_ids", []) if isinstance(value, str))}, "target_taxon_id": str(target_taxon_id), "orthologs": orthologs[:max_records], "total_target_orthologs": len(orthologs), "truncated": len(orthologs) > max_records, "provenance": {"service": "NCBI Datasets Gene API", "transport": transport, "api_key_used": bool(ncbi_api_key)}}


def ensembl_gene_lookup(
    gene_symbol: str, species: str = "human", *, client: PublicJSONClient | None = None
) -> dict[str, Any]:
    """Resolve one declared human or mouse gene symbol through Ensembl REST."""
    normalized_symbol = gene_symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,63}", normalized_symbol):
        raise ValueError("gene_symbol must be a bounded alphanumeric gene symbol")
    species_map = {"human": "homo_sapiens", "mouse": "mus_musculus"}
    normalized_species = species.strip().lower()
    if normalized_species not in species_map:
        raise ValueError("species must be human or mouse")
    payload, transport = (client or PublicJSONClient()).get_with_metadata(
        "https://rest.ensembl.org",
        f"/lookup/symbol/{species_map[normalized_species]}/{quote(normalized_symbol, safe='')}",
        {"expand": 0},
        not_found_as_empty_object=True,
    )
    if not payload:
        return {
            "requested_symbol": normalized_symbol,
            "species": normalized_species,
            "found": False,
            "record": None,
            "provenance": {"service": "Ensembl REST lookup/symbol", "contract_version": ENSEMBL_GENE_LOOKUP_CONTRACT_VERSION, "transport": transport},
            "limitations": ["A not-found response does not prove that the gene, alias, transcript, locus, or ortholog is absent from biology or another annotation release."],
        }
    identifier = _clean_text(payload.get("id"), limit=100)
    display_name = _clean_text(payload.get("display_name"), limit=100)
    assembly = _clean_text(payload.get("assembly_name"), limit=100)
    region = _clean_text(payload.get("seq_region_name"), limit=100)
    start, end, strand = payload.get("start"), payload.get("end"), payload.get("strand")
    if not identifier or not display_name or not assembly or not region or not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start or strand not in {-1, 1}:
        raise PublicDatabaseError("Ensembl lookup response lacks a valid exact gene identity and coordinate record")
    record = {
        "ensembl_gene_id": identifier,
        "display_name": display_name,
        "species": _clean_text(payload.get("species"), limit=100),
        "assembly_name": assembly,
        "seq_region_name": region,
        "start": start,
        "end": end,
        "strand": strand,
        "biotype": _clean_text(payload.get("biotype"), limit=100),
        "canonical_transcript": _clean_text(payload.get("canonical_transcript"), limit=100),
        "annotation_version": payload.get("version") if isinstance(payload.get("version"), int) else None,
        "description": _clean_text(payload.get("description")),
    }
    return {
        "requested_symbol": normalized_symbol,
        "species": normalized_species,
        "found": True,
        "record": record,
        "provenance": {"service": "Ensembl REST lookup/symbol", "contract_version": ENSEMBL_GENE_LOOKUP_CONTRACT_VERSION, "transport": transport},
        "limitations": ["This lookup resolves one current Ensembl gene record; it does not resolve aliases, infer equivalence across releases, identify a transcript or isoform for analysis, establish expression, disease relevance, function, or causality."],
    }


def opentargets_target_disease_evidence(
    ensembl_gene_id: str, disease_id: str, data_types: list[str] | None = None, max_records: int = 100, *, client: PublicJSONClient | None = None
) -> dict[str, Any]:
    """Retrieve bounded fixed-field Open Targets evidence for one target-disease pair."""
    gene_id, normalized_disease = ensembl_gene_id.strip().upper(), disease_id.strip().upper()
    if not re.fullmatch(r"ENS[A-Z]*G[0-9]{11}", gene_id) or not re.fullmatch(r"[A-Z][A-Z0-9]*_[0-9]+", normalized_disease):
        raise ValueError("ensembl_gene_id or disease_id is not in the bounded identifier grammar")
    if not 1 <= max_records <= 500:
        raise ValueError("max_records must be within 1..500")
    normalized_types = None
    if data_types is not None:
        if not 1 <= len(data_types) <= 30:
            raise ValueError("data_types must contain 1..30 values when supplied")
        normalized_types = sorted({value.strip().lower() for value in data_types})
        if len(normalized_types) != len(data_types) or any(not re.fullmatch(r"[a-z0-9_]{1,100}", value) for value in normalized_types):
            raise ValueError("data_types must be unique lowercase Open Targets datatype identifiers")
    query = """query Evidence($diseaseId: String!, $geneId: String!, $size: Int!) { disease(efoId: $diseaseId) { id name evidences(ensemblIds: [$geneId], size: $size) { count rows { datasourceId datatypeId score targetFromSourceId studyId literature } } } }"""
    payload, transport = (client or PublicJSONClient()).post_with_metadata("https://api.platform.opentargets.org", "/api/v4/graphql", {"query": query, "variables": {"diseaseId": normalized_disease, "geneId": gene_id, "size": max_records}})
    if isinstance(payload.get("errors"), list):
        raise PublicDatabaseError("Open Targets GraphQL returned errors")
    data = payload.get("data")
    disease = data.get("disease") if isinstance(data, dict) else None
    if disease is None:
        return {"ensembl_gene_id": gene_id, "disease_id": normalized_disease, "data_types": normalized_types, "found": False, "total_count": 0, "returned_count": 0, "truncated": False, "evidence": [], "provenance": {"service": "Open Targets Platform GraphQL", "contract_version": OPENTARGETS_EVIDENCE_CONTRACT_VERSION, "transport": transport}, "limitations": ["A missing disease record does not establish the absence of a disease concept or target-disease biology."]}
    if not isinstance(disease, dict) or disease.get("id") != normalized_disease or not isinstance(disease.get("name"), str) or not isinstance(disease.get("evidences"), dict):
        raise PublicDatabaseError("Open Targets response lacks an exact disease and evidence container")
    evidence_container = disease["evidences"]
    total, rows = evidence_container.get("count"), evidence_container.get("rows")
    if not isinstance(total, int) or total < 0 or not isinstance(rows, list):
        raise PublicDatabaseError("Open Targets evidence response lacks count or rows")
    records = []
    for item in rows:
        if not isinstance(item, dict) or item.get("targetFromSourceId") != gene_id:
            continue
        score = item.get("score")
        if not isinstance(score, (int, float)) or score < 0:
            continue
        if normalized_types is not None and _clean_text(item.get("datatypeId"), limit=100) not in normalized_types:
            continue
        records.append({"datasource_id": _clean_text(item.get("datasourceId"), limit=100), "datatype_id": _clean_text(item.get("datatypeId"), limit=100), "score": float(score), "study_id": _clean_text(item.get("studyId"), limit=500), "literature_ids": sorted({_clean_text(value, limit=100) for value in item.get("literature", []) if _clean_text(value, limit=100)})})
    records.sort(key=lambda item: (-item["score"], item["datatype_id"] or "", item["datasource_id"] or "", item["study_id"] or ""))
    return {"ensembl_gene_id": gene_id, "disease_id": normalized_disease, "disease_name": _clean_text(disease["name"], limit=1000), "data_types": normalized_types, "found": True, "total_count": total, "returned_count": len(records), "truncated": total > max_records, "evidence": records, "provenance": {"service": "Open Targets Platform GraphQL", "contract_version": OPENTARGETS_EVIDENCE_CONTRACT_VERSION, "data_type_filter_mode": "local-returned-page" if normalized_types is not None else "none", "transport": transport}, "limitations": ["Open Targets no longer exposes a datatype argument on this evidence operation; any declared datatype filter is applied only to the bounded returned page and cannot support an exhaustive filtered count. Association evidence and aggregate scores are source-integrated context, not proof of a mechanism, clinical validity, actionability, treatment response, or causality."]}


def gnomad_gene_constraint_evidence(gene_symbol: str, *, client: PublicJSONClient | None = None) -> dict[str, Any]:
    """Retrieve fixed-field gnomAD GRCh38 gene-constraint context for one symbol."""
    symbol = gene_symbol.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9-]{0,39}", symbol):
        raise ValueError("gene_symbol must be a bounded uppercase HGNC-style symbol")
    query = """query GeneConstraint($symbol: String!, $reference: ReferenceGenomeId!) { gene(gene_symbol: $symbol, reference_genome: $reference) { gene_id symbol chrom start stop gnomad_constraint { exp_lof obs_lof oe_lof oe_lof_lower oe_lof_upper oe_lof_percentile pli flags } } }"""
    payload, transport = (client or PublicJSONClient()).post_with_metadata(
        "https://gnomad.broadinstitute.org", "/api", {"query": query, "variables": {"symbol": symbol, "reference": "GRCh38"}}
    )
    if isinstance(payload.get("errors"), list):
        raise PublicDatabaseError("gnomAD GraphQL returned errors")
    data = payload.get("data")
    gene = data.get("gene") if isinstance(data, dict) else None
    provenance = {"service": "gnomAD GraphQL", "contract_version": GNOMAD_GENE_CONSTRAINT_CONTRACT_VERSION, "transport": transport}
    if gene is None:
        return {"gene_symbol": symbol, "reference_genome": "GRCh38", "found": False, "gene": None, "constraint": None, "provenance": provenance, "limitations": ["A missing gnomAD result does not establish absence of a gene, constraint estimate, disease relationship, or variant effect."]}
    if not isinstance(gene, dict) or _clean_text(gene.get("symbol"), limit=40).upper() != symbol or not _clean_text(gene.get("gene_id"), limit=100):
        raise PublicDatabaseError("gnomAD response lacks an exact gene identity")
    raw = gene.get("gnomad_constraint")
    if raw is not None and not isinstance(raw, dict):
        raise PublicDatabaseError("gnomAD response has an invalid constraint object")
    fields = ("exp_lof", "obs_lof", "oe_lof", "oe_lof_lower", "oe_lof_upper", "oe_lof_percentile", "pli")
    constraint = None if raw is None else {field: raw.get(field) if isinstance(raw.get(field), (int, float)) else None for field in fields}
    if constraint is not None:
        constraint["flags"] = sorted({_clean_text(value, limit=200) for value in raw.get("flags", []) if _clean_text(value, limit=200)})
    return {"gene_symbol": symbol, "reference_genome": "GRCh38", "found": True, "gene": {"gene_id": _clean_text(gene["gene_id"], limit=100), "symbol": _clean_text(gene["symbol"], limit=40), "chrom": _clean_text(gene.get("chrom"), limit=50), "start": gene.get("start") if isinstance(gene.get("start"), int) else None, "stop": gene.get("stop") if isinstance(gene.get("stop"), int) else None}, "constraint": constraint, "provenance": provenance, "limitations": ["Gene constraint metrics describe aggregate depletion in the declared gnomAD release context. They do not establish disease causality, variant pathogenicity, individual risk, gene essentiality, or therapeutic actionability."]}


def cbioportal_study_evidence(study_id: str, *, client: PublicJSONClient | None = None) -> dict[str, Any]:
    """Retrieve a source-preserved public cBioPortal study record by exact ID."""
    normalized = study_id.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", normalized):
        raise ValueError("study_id must be a bounded cBioPortal study identifier")
    payload, transport = (client or PublicJSONClient()).get_with_metadata(
        "https://www.cbioportal.org", f"/api/studies/{quote(normalized, safe='')}", not_found_as_empty_object=True
    )
    provenance = {"service": "cBioPortal public REST API", "contract_version": CBIOPORTAL_STUDY_CONTRACT_VERSION, "transport": transport}
    if not payload:
        return {"study_id": normalized, "found": False, "study": None, "provenance": provenance, "limitations": ["A missing cBioPortal study ID does not establish absence of a cohort, cancer type, molecular assay, result, or clinical evidence."]}
    if _clean_text(payload.get("studyId"), limit=100) != normalized:
        raise PublicDatabaseError("cBioPortal response does not preserve the requested study ID")
    name = _clean_text(payload.get("name"), limit=1000)
    cancer_type = payload.get("cancerType")
    if not name or not isinstance(cancer_type, dict) or not _clean_text(cancer_type.get("id"), limit=100):
        raise PublicDatabaseError("cBioPortal study response lacks required study identity or cancer type")
    sample_fields = (
        "allSampleCount", "sequencedSampleCount", "cnaSampleCount", "mrnaRnaSeqSampleCount",
        "mrnaRnaSeqV2SampleCount", "mrnaMicroarraySampleCount", "miRnaSampleCount",
        "methylationHm27SampleCount", "rppaSampleCount", "massSpectrometrySampleCount",
        "completeSampleCount", "structuralVariantCount", "treatmentCount",
    )
    sample_counts = {field: payload.get(field) if isinstance(payload.get(field), int) and payload[field] >= 0 else None for field in sample_fields}
    return {
        "study_id": normalized,
        "found": True,
        "study": {
            "study_id": normalized,
            "name": name,
            "description": _clean_text(payload.get("description"), limit=5000),
            "cancer_type": {"id": _clean_text(cancer_type.get("id"), limit=100), "name": _clean_text(cancer_type.get("name"), limit=500), "short_name": _clean_text(cancer_type.get("shortName"), limit=100), "parent": _clean_text(cancer_type.get("parent"), limit=100)},
            "reference_genome": _clean_text(payload.get("referenceGenome"), limit=100),
            "citation": _clean_text(payload.get("citation"), limit=2000),
            "pmid": _clean_text(payload.get("pmid"), limit=100),
            "public_study": payload.get("publicStudy") if isinstance(payload.get("publicStudy"), bool) else None,
            "read_permission": payload.get("readPermission") if isinstance(payload.get("readPermission"), bool) else None,
            "sample_counts": sample_counts,
        },
        "provenance": provenance,
        "limitations": ["This is a public study metadata record, not patient-level data, a mutation or copy-number analysis, a survival analysis, a treatment-response result, or a clinical recommendation.", "cBioPortal sample counts are assay-specific cohort metadata and should not be treated as a uniformly analyzable sample size without checking data-type, sample-list, consent, preprocessing, and study documentation."],
    }


def cbioportal_gene_mutation_evidence(
    study_id: str,
    gene_symbol: str,
    max_records: int = 100,
    molecular_profile_id: str | None = None,
    sample_list_id: str | None = None,
    *,
    client: PublicJSONClient | None = None,
) -> dict[str, Any]:
    """Retrieve bounded, source-preserved mutations for one gene in one public study."""
    normalized_study = study_id.strip()
    symbol = gene_symbol.strip().upper()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", normalized_study):
        raise ValueError("study_id must be a bounded cBioPortal study identifier")
    if not re.fullmatch(r"[A-Z][A-Z0-9-]{0,39}", symbol) or not 1 <= max_records <= 500:
        raise ValueError("gene_symbol or max_records is outside the bounded contract")
    for label, value in (("molecular_profile_id", molecular_profile_id), ("sample_list_id", sample_list_id)):
        if value is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}", value.strip()):
            raise ValueError(f"{label} must be a bounded cBioPortal identifier when declared")
    active = client or PublicJSONClient()
    gene, gene_transport = active.get_with_metadata("https://www.cbioportal.org", f"/api/genes/{quote(symbol, safe='')}", not_found_as_empty_object=True)
    provenance = {"service": "cBioPortal public REST API", "contract_version": CBIOPORTAL_STUDY_CONTRACT_VERSION, "gene_transport": gene_transport}
    if not gene:
        return {"study_id": normalized_study, "gene_symbol": symbol, "found": False, "resolution_status": "gene_not_found", "molecular_profile": None, "sample_list": None, "records": [], "returned_count": 0, "truncated": False, "provenance": provenance, "limitations": ["A cBioPortal gene lookup miss does not establish absence of a gene, synonym, mutation, or biological role."]}
    entrez_gene_id = gene.get("entrezGeneId")
    if _clean_text(gene.get("hugoGeneSymbol"), limit=40).upper() != symbol or not isinstance(entrez_gene_id, int) or entrez_gene_id <= 0:
        raise PublicDatabaseError("cBioPortal gene response does not preserve an exact gene identity")
    profiles, profile_transport = active.get_array_with_metadata("https://www.cbioportal.org", f"/api/studies/{quote(normalized_study, safe='')}/molecular-profiles")
    mutation_profiles = [
        item for item in profiles
        if isinstance(item, dict)
        and _clean_text(item.get("studyId"), limit=100) == normalized_study
        and _clean_text(item.get("molecularAlterationType"), limit=100) == "MUTATION_EXTENDED"
        and _clean_text(item.get("molecularProfileId"), limit=200)
    ]
    mutation_profiles.sort(key=lambda item: _clean_text(item.get("molecularProfileId"), limit=200))
    requested_profile = molecular_profile_id.strip() if molecular_profile_id else None
    selected_profiles = [item for item in mutation_profiles if _clean_text(item.get("molecularProfileId"), limit=200) == requested_profile] if requested_profile else mutation_profiles
    provenance["profile_transport"] = profile_transport
    if len(selected_profiles) != 1:
        return {"study_id": normalized_study, "gene_symbol": symbol, "entrez_gene_id": entrez_gene_id, "found": False, "resolution_status": "mutation_profile_not_resolved", "molecular_profile": None, "sample_list": None, "available_mutation_profile_ids": [_clean_text(item.get("molecularProfileId"), limit=200) for item in mutation_profiles], "records": [], "returned_count": 0, "truncated": False, "provenance": provenance, "limitations": ["The study did not expose exactly one usable mutation profile under this bounded request. Declare a valid molecular_profile_id when a study has multiple mutation profiles."]}
    profile = selected_profiles[0]
    profile_id = _clean_text(profile.get("molecularProfileId"), limit=200)
    sample_lists, sample_transport = active.get_array_with_metadata("https://www.cbioportal.org", f"/api/studies/{quote(normalized_study, safe='')}/sample-lists")
    mutation_sample_lists = [
        item for item in sample_lists
        if isinstance(item, dict)
        and _clean_text(item.get("studyId"), limit=100) == normalized_study
        and _clean_text(item.get("category"), limit=100) == "all_cases_with_mutation_data"
        and _clean_text(item.get("sampleListId"), limit=200)
    ]
    mutation_sample_lists.sort(key=lambda item: _clean_text(item.get("sampleListId"), limit=200))
    requested_sample_list = sample_list_id.strip() if sample_list_id else None
    selected_lists = [item for item in mutation_sample_lists if _clean_text(item.get("sampleListId"), limit=200) == requested_sample_list] if requested_sample_list else mutation_sample_lists
    provenance["sample_list_transport"] = sample_transport
    if len(selected_lists) != 1:
        return {"study_id": normalized_study, "gene_symbol": symbol, "entrez_gene_id": entrez_gene_id, "found": False, "resolution_status": "mutation_sample_list_not_resolved", "molecular_profile": {"id": profile_id, "name": _clean_text(profile.get("name"), limit=1000), "datatype": _clean_text(profile.get("datatype"), limit=100)}, "sample_list": None, "available_mutation_sample_list_ids": [_clean_text(item.get("sampleListId"), limit=200) for item in mutation_sample_lists], "records": [], "returned_count": 0, "truncated": False, "provenance": provenance, "limitations": ["The study did not expose exactly one all-cases mutation sample list under this bounded request. Declare a valid sample_list_id when an explicit cohort subset is scientifically justified."]}
    selected_list = selected_lists[0]
    selected_sample_list_id = _clean_text(selected_list.get("sampleListId"), limit=200)
    raw_records, mutation_transport = active.post_array_with_metadata(
        "https://www.cbioportal.org",
        f"/api/molecular-profiles/{quote(profile_id, safe='')}/mutations/fetch",
        {"entrezGeneIds": [entrez_gene_id], "sampleListId": selected_sample_list_id},
        {"projection": "SUMMARY"},
    )
    records = []
    for item in raw_records[:max_records]:
        if not isinstance(item, dict):
            raise PublicDatabaseError("cBioPortal mutation response contains a non-object record")
        if _clean_text(item.get("studyId"), limit=100) != normalized_study or _clean_text(item.get("molecularProfileId"), limit=200) != profile_id or item.get("entrezGeneId") != entrez_gene_id:
            raise PublicDatabaseError("cBioPortal mutation response violates study, profile, or gene identity")
        start, end = item.get("startPosition"), item.get("endPosition")
        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
            raise PublicDatabaseError("cBioPortal mutation response lacks valid genomic positions")
        records.append({"sample_id": _clean_text(item.get("sampleId"), limit=500), "entrez_gene_id": entrez_gene_id, "chromosome": _clean_text(item.get("chr"), limit=100), "start": start, "end": end, "reference_allele": _clean_text(item.get("referenceAllele"), limit=10000), "variant_allele": _clean_text(item.get("variantAllele"), limit=10000), "ncbi_build": _clean_text(item.get("ncbiBuild"), limit=100), "variant_type": _clean_text(item.get("variantType"), limit=100), "mutation_type": _clean_text(item.get("mutationType"), limit=200), "protein_change": _clean_text(item.get("proteinChange"), limit=500), "refseq_mrna_id": _clean_text(item.get("refseqMrnaId"), limit=200), "tumor_alt_count": item.get("tumorAltCount") if isinstance(item.get("tumorAltCount"), int) and item["tumorAltCount"] >= 0 else None, "tumor_ref_count": item.get("tumorRefCount") if isinstance(item.get("tumorRefCount"), int) and item["tumorRefCount"] >= 0 else None})
    provenance["mutation_transport"] = mutation_transport
    return {"study_id": normalized_study, "gene_symbol": symbol, "entrez_gene_id": entrez_gene_id, "found": True, "resolution_status": "resolved", "molecular_profile": {"id": profile_id, "name": _clean_text(profile.get("name"), limit=1000), "datatype": _clean_text(profile.get("datatype"), limit=100)}, "sample_list": {"id": selected_sample_list_id, "name": _clean_text(selected_list.get("name"), limit=1000), "description": _clean_text(selected_list.get("description"), limit=2000), "sample_count": selected_list.get("sampleCount") if isinstance(selected_list.get("sampleCount"), int) and selected_list["sampleCount"] >= 0 else None}, "records": records, "returned_count": len(records), "truncated": len(raw_records) > max_records, "provenance": provenance, "limitations": ["This bounded public mutation retrieval does not estimate cohort-wide mutation frequency, prevalence, clonality, allele fraction reliability, coverage, calling sensitivity, patient outcome, treatment response, pathogenicity, clinical actionability, or causality.", "Returned records are capped and ordered by the service; a truncated result is not an exhaustive mutation set. Reconcile genome build, transcript, assay panel, cohort definition and original study documentation before downstream analysis."]}


def cbioportal_gene_copy_number_evidence(
    study_id: str, gene_symbol: str, max_records: int = 100, event_type: str = "HOMDEL_AND_AMP", *, client: PublicJSONClient | None = None
) -> dict[str, Any]:
    """Retrieve bounded discrete copy-number events via cBioPortal's required POST filter."""
    study, symbol = study_id.strip(), gene_symbol.strip().upper()
    events = {"HOMDEL_AND_AMP", "HOMDEL", "AMP", "GAIN", "HETLOSS", "DIPLOID", "ALL"}
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", study) or not re.fullmatch(r"[A-Z][A-Z0-9-]{0,39}", symbol) or not 1 <= max_records <= 500 or event_type not in events:
        raise ValueError("study_id, gene_symbol, max_records, or event_type is outside the bounded contract")
    active = client or PublicJSONClient()
    gene, gene_transport = active.get_with_metadata("https://www.cbioportal.org", f"/api/genes/{quote(symbol, safe='')}", not_found_as_empty_object=True)
    provenance = {"service": "cBioPortal public REST API", "contract_version": CBIOPORTAL_STUDY_CONTRACT_VERSION, "gene_transport": gene_transport}
    if not gene:
        return {"study_id": study, "gene_symbol": symbol, "event_type": event_type, "found": False, "resolution_status": "gene_not_found", "molecular_profile": None, "sample_list": None, "records": [], "returned_count": 0, "service_record_count": 0, "truncated": False, "provenance": provenance, "limitations": ["A cBioPortal gene lookup miss does not establish absence of a gene, synonym, copy-number event, or biological role."]}
    gene_id = gene.get("entrezGeneId")
    if _clean_text(gene.get("hugoGeneSymbol"), limit=40).upper() != symbol or not isinstance(gene_id, int) or gene_id <= 0:
        raise PublicDatabaseError("cBioPortal gene response does not preserve an exact gene identity")
    profiles, profile_transport = active.get_array_with_metadata("https://www.cbioportal.org", f"/api/studies/{quote(study, safe='')}/molecular-profiles")
    profiles = [row for row in profiles if isinstance(row, dict) and _clean_text(row.get("studyId"), limit=100) == study and _clean_text(row.get("molecularAlterationType"), limit=100) == "COPY_NUMBER_ALTERATION" and _clean_text(row.get("datatype"), limit=100) == "DISCRETE"]
    profiles.sort(key=lambda row: _clean_text(row.get("molecularProfileId"), limit=200))
    provenance["profile_transport"] = profile_transport
    if len(profiles) != 1:
        return {"study_id": study, "gene_symbol": symbol, "entrez_gene_id": gene_id, "event_type": event_type, "found": False, "resolution_status": "copy_number_profile_not_resolved", "molecular_profile": None, "sample_list": None, "records": [], "returned_count": 0, "service_record_count": 0, "truncated": False, "provenance": provenance, "limitations": ["The study did not expose exactly one usable discrete copy-number profile; choose a study with one declared profile or resolve profile identity before interpretation."]}
    profile = profiles[0]
    profile_id = _clean_text(profile.get("molecularProfileId"), limit=200)
    sample_lists, sample_transport = active.get_array_with_metadata("https://www.cbioportal.org", f"/api/studies/{quote(study, safe='')}/sample-lists")
    sample_lists = [row for row in sample_lists if isinstance(row, dict) and _clean_text(row.get("studyId"), limit=100) == study and _clean_text(row.get("category"), limit=100) == "all_cases_with_cna_data"]
    sample_lists.sort(key=lambda row: _clean_text(row.get("sampleListId"), limit=200))
    provenance["sample_list_transport"] = sample_transport
    if len(sample_lists) != 1:
        return {"study_id": study, "gene_symbol": symbol, "entrez_gene_id": gene_id, "event_type": event_type, "found": False, "resolution_status": "copy_number_sample_list_not_resolved", "molecular_profile": {"id": profile_id, "datatype": _clean_text(profile.get("datatype"), limit=100)}, "sample_list": None, "records": [], "returned_count": 0, "service_record_count": 0, "truncated": False, "provenance": provenance, "limitations": ["The study did not expose exactly one all-cases copy-number sample list; resolve cohort identity before interpretation."]}
    sample_list = sample_lists[0]
    sample_list_id = _clean_text(sample_list.get("sampleListId"), limit=200)
    raw, cna_transport = active.post_array_with_metadata("https://www.cbioportal.org", f"/api/molecular-profiles/{quote(profile_id, safe='')}/discrete-copy-number/fetch", {"entrezGeneIds": [gene_id], "sampleListId": sample_list_id}, {"discreteCopyNumberEventType": event_type, "projection": "SUMMARY"})
    labels = {-2: "homozygous_deletion", -1: "hemizygous_deletion", 0: "diploid", 1: "gain", 2: "amplification"}
    records = []
    for row in raw[:max_records]:
        if not isinstance(row, dict) or _clean_text(row.get("studyId"), limit=100) != study or _clean_text(row.get("molecularProfileId"), limit=200) != profile_id or row.get("entrezGeneId") != gene_id or row.get("alteration") not in labels:
            raise PublicDatabaseError("cBioPortal copy-number response violates the requested identity contract")
        records.append({"sample_id": _clean_text(row.get("sampleId"), limit=500), "entrez_gene_id": gene_id, "alteration": row["alteration"], "alteration_label": labels[row["alteration"]]})
    provenance["copy_number_transport"] = cna_transport
    return {"study_id": study, "gene_symbol": symbol, "entrez_gene_id": gene_id, "event_type": event_type, "found": True, "resolution_status": "resolved", "molecular_profile": {"id": profile_id, "name": _clean_text(profile.get("name"), limit=1000), "datatype": _clean_text(profile.get("datatype"), limit=100)}, "sample_list": {"id": sample_list_id, "name": _clean_text(sample_list.get("name"), limit=1000), "sample_count": sample_list.get("sampleCount") if isinstance(sample_list.get("sampleCount"), int) and sample_list["sampleCount"] >= 0 else None}, "records": records, "returned_count": len(records), "service_record_count": len(raw), "truncated": len(raw) > max_records, "provenance": provenance, "limitations": ["Discrete copy-number calls are assay- and pipeline-specific categorical events, not absolute copy number, clonality, expression effect, driver status, treatment response, clinical actionability, or causality.", "The API POST filter is required because the analogous GET route can ignore gene filters. Output is locally capped and carries the complete service record count for the declared event type."]}


def reactome_pathway_record(pathway_id: str, *, client: PublicJSONClient | None = None) -> dict[str, Any]:
    """Retrieve one exact Reactome pathway record without arbitrary endpoint access."""
    normalized = pathway_id.strip().upper()
    if not re.fullmatch(r"R-[A-Z]{3}-[1-9][0-9]{0,11}", normalized):
        raise ValueError("pathway_id must be a canonical Reactome stable pathway identifier")
    payload, transport = (client or PublicJSONClient()).get_with_metadata(
        "https://reactome.org", f"/ContentService/data/query/{normalized}", not_found_as_empty_object=True
    )
    if not payload:
        return {"requested_pathway_id": normalized, "found": False, "record": None, "provenance": {"service": "Reactome Content Service", "contract_version": REACTOME_PATHWAY_CONTRACT_VERSION, "transport": transport}, "limitations": ["A not-found response does not establish that a pathway concept, related reaction, gene set, or biological process is absent."]}
    identifier = _clean_text(payload.get("stId"), limit=100)
    display_name = _clean_text(payload.get("displayName"), limit=500)
    species = _clean_text(payload.get("speciesName"), limit=200)
    if identifier != normalized or payload.get("schemaClass") != "Pathway" or not display_name or not species:
        raise PublicDatabaseError("Reactome response is not an exact pathway record with identity and species")
    go_process = payload.get("goBiologicalProcess")
    go_record = None
    if isinstance(go_process, dict):
        accession = _clean_text(go_process.get("accession"), limit=100)
        if accession:
            go_record = {"accession": f"GO:{accession}" if not accession.startswith("GO:") else accession, "name": _clean_text(go_process.get("displayName"), limit=500)}
    return {
        "requested_pathway_id": normalized,
        "found": True,
        "record": {"stable_id": identifier, "stable_id_version": _clean_text(payload.get("stIdVersion"), limit=100), "display_name": display_name, "species": species, "release_date": _clean_text(payload.get("releaseDate"), limit=100), "is_in_disease": payload.get("isInDisease") if isinstance(payload.get("isInDisease"), bool) else None, "is_inferred": payload.get("isInferred") if isinstance(payload.get("isInferred"), bool) else None, "go_biological_process": go_record},
        "provenance": {"service": "Reactome Content Service", "contract_version": REACTOME_PATHWAY_CONTRACT_VERSION, "transport": transport},
        "limitations": ["A pathway record is curated reference context; it does not quantify pathway activity, test enrichment, prove membership for a project gene list, establish mechanism, or causality."],
    }


def reactome_gene_set_overrepresentation(
    identifiers: list[str], max_pathways: int = 100, *, client: PublicJSONClient | None = None
) -> dict[str, Any]:
    """Run one bounded Reactome identifier overrepresentation request."""
    if not 1 <= len(identifiers) <= 5_000 or not 1 <= max_pathways <= 500:
        raise ValueError("identifiers and max_pathways are outside the bounded contract")
    normalized = []
    for value in identifiers:
        identifier = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", identifier):
            raise ValueError("each identifier must be a bounded, whitespace-free token")
        normalized.append(identifier)
    if len(set(normalized)) != len(normalized):
        raise ValueError("identifiers must be unique")
    payload, transport = (client or PublicJSONClient()).post_text_with_metadata(
        "https://reactome.org", "/AnalysisService/identifiers/", "\n".join(normalized) + "\n"
    )
    summary, pathways = payload.get("summary"), payload.get("pathways")
    if not isinstance(summary, dict) or not isinstance(pathways, list) or _clean_text(summary.get("type"), limit=100) != "OVERREPRESENTATION":
        raise PublicDatabaseError("Reactome analysis response lacks an overrepresentation summary and pathway list")
    results = []
    for item in pathways:
        if not isinstance(item, dict) or not isinstance(item.get("entities"), dict):
            continue
        stable_id, name, entities = _clean_text(item.get("stId"), limit=100), _clean_text(item.get("name"), limit=1000), item["entities"]
        p_value, fdr, found, total = entities.get("pValue"), entities.get("fdr"), entities.get("found"), entities.get("total")
        if not stable_id or not name or not all(isinstance(value, (int, float)) and value >= 0 for value in (p_value, fdr)) or not isinstance(found, int) or not isinstance(total, int) or not 0 <= found <= total:
            continue
        species = item.get("species")
        results.append({"stable_id": stable_id, "name": name, "species": _clean_text(species.get("name"), limit=200) if isinstance(species, dict) else None, "found_identifiers": found, "pathway_identifier_count": total, "p_value": float(p_value), "fdr": float(fdr), "in_disease": item.get("inDisease") if isinstance(item.get("inDisease"), bool) else None})
    results.sort(key=lambda item: (item["fdr"], item["p_value"], item["stable_id"]))
    return {"requested_identifiers": normalized, "input_identifier_count": len(normalized), "unmapped_identifier_count": payload.get("identifiersNotFound") if isinstance(payload.get("identifiersNotFound"), int) else None, "pathway_count": len(results), "returned_pathway_count": min(len(results), max_pathways), "truncated": len(results) > max_pathways, "pathways": results[:max_pathways], "provenance": {"service": "Reactome Analysis Service", "contract_version": REACTOME_PATHWAY_CONTRACT_VERSION, "analysis_token": _clean_text(summary.get("token"), limit=500), "transport": transport}, "limitations": ["Reactome performs its own identifier mapping and universe definition; this result cannot replace a project-specific background, ranked analysis, donor-aware differential model, multiple testing plan, or independent biological validation."]}


def enrichr_library_catalog(category_id: int | None = None, max_libraries: int = 500, *, client: PublicJSONClient | None = None) -> dict[str, Any]:
    """Retrieve bounded Enrichr library metadata without treating it as gene-set evidence."""
    if category_id is not None and not 1 <= category_id <= 10_000:
        raise ValueError("category_id must be within 1..10000 when supplied")
    if not 1 <= max_libraries <= 1000:
        raise ValueError("max_libraries must be within 1..1000")
    payload, transport = (client or PublicJSONClient()).get_with_metadata("https://maayanlab.cloud", "/Enrichr/datasetStatistics")
    statistics = payload.get("statistics")
    if not isinstance(statistics, list):
        raise PublicDatabaseError("Enrichr datasetStatistics response lacks a statistics list")
    libraries = []
    for item in statistics:
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("libraryName"), limit=500)
        observed_category = item.get("categoryId")
        terms = item.get("numTerms")
        coverage = item.get("geneCoverage")
        if not name or not isinstance(observed_category, int) or not isinstance(terms, int) or not isinstance(coverage, int):
            continue
        if category_id is not None and observed_category != category_id:
            continue
        libraries.append({"library_name": name, "category_id": observed_category, "term_count": terms, "gene_coverage": coverage, "genes_per_term": item.get("genesPerTerm") if isinstance(item.get("genesPerTerm"), int) else None, "resource_link": _clean_text(item.get("link"), limit=2000)})
    libraries.sort(key=lambda item: (item["category_id"], item["library_name"]))
    return {"category_id": category_id, "library_count": len(libraries), "returned_library_count": min(len(libraries), max_libraries), "truncated": len(libraries) > max_libraries, "libraries": libraries[:max_libraries], "provenance": {"service": "Enrichr datasetStatistics", "contract_version": ENRICHR_CONTRACT_VERSION, "transport": transport}, "limitations": ["Library metadata describes a selectable resource and does not establish that any term is enriched for a project gene list.", "Library membership, identifiers, species scope and curation can change; freeze the selected library and retrieval provenance before enrichment."]}


def enrichr_gene_set_library(
    library_name: str, max_terms: int = 5000, max_members_per_term: int = 10000, *, client: PublicJSONClient | None = None
) -> dict[str, Any]:
    """Retrieve a bounded Enrichr library snapshot for explicit local analysis."""
    normalized = library_name.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.+() -]{1,200}", normalized):
        raise ValueError("library_name contains unsupported characters or length")
    if not 1 <= max_terms <= 5000 or not 1 <= max_members_per_term <= 10000:
        raise ValueError("max_terms or max_members_per_term is outside the bounded contract")
    payload, transport = (client or PublicJSONClient()).get_with_metadata(
        "https://maayanlab.cloud", "/Enrichr/geneSetLibrary", {"mode": "json", "libraryName": normalized}
    )
    library = payload.get(normalized)
    if not isinstance(library, dict) or library.get("libraryName") != normalized or not isinstance(library.get("terms"), dict):
        raise PublicDatabaseError("Enrichr geneSetLibrary response lacks the requested library and terms")
    terms = []
    for term, members in library["terms"].items():
        term_name = _clean_text(term, limit=2000)
        if not term_name or not isinstance(members, dict):
            continue
        genes = sorted({gene.strip() for gene in members if isinstance(gene, str) and gene.strip()})
        terms.append({"term": term_name, "gene_count": len(genes), "genes": genes[:max_members_per_term], "members_truncated": len(genes) > max_members_per_term})
    terms.sort(key=lambda row: row["term"])
    return {"library_name": normalized, "is_fuzzy": bool(library.get("isFuzzy", False)), "term_count": len(terms), "returned_term_count": min(len(terms), max_terms), "truncated": len(terms) > max_terms, "terms": terms[:max_terms], "provenance": {"service": "Enrichr geneSetLibrary", "contract_version": ENRICHR_LIBRARY_CONTRACT_VERSION, "transport": transport}, "limitations": ["This is a bounded retrieval snapshot, not an enrichment result or a biological interpretation.", "Term membership can change; retain the response provenance and reconcile gene identifiers, species, release scope, background and multiple-testing family before enrichment."]}


def archs4_expression_atlas(
    gene_symbol: str,
    species: str = "human",
    atlas: str = "tissue",
    max_records: int = 50,
    *,
    client: PublicJSONClient | None = None,
) -> dict[str, Any]:
    """Retrieve a bounded ARCHS4 tissue or cell-line expression overview.

    ARCHS4 returns a CSV hierarchy containing nonnumeric grouping rows. Those
    rows are preserved as neither samples nor expression observations; only rows
    with all five declared numeric summary statistics become evidence records.
    """
    normalized_gene = gene_symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,99}", normalized_gene):
        raise ValueError("gene_symbol must be a short gene symbol or stable identifier token")
    normalized_species = species.strip().lower()
    if normalized_species not in {"human", "mouse"}:
        raise ValueError("species must be human or mouse")
    normalized_atlas = atlas.strip().lower()
    if normalized_atlas not in {"tissue", "cellline"}:
        raise ValueError("atlas must be tissue or cellline")
    if not 1 <= max_records <= 500:
        raise ValueError("max_records must be within 1..500")
    text, transport = (client or PublicJSONClient()).get_text_with_metadata(
        "https://maayanlab.cloud",
        "/archs4/search/loadExpressionTissue.php",
        {"search": normalized_gene, "species": normalized_species, "type": normalized_atlas},
        accepted_content_types=("text/csv", "text/plain", "text/html", "application/octet-stream"),
    )
    try:
        rows = list(csv.DictReader(io.StringIO(text)))
    except csv.Error as exc:
        raise PublicDatabaseError(f"ARCHS4 expression response is not parseable CSV: {exc}") from None
    expected_fields = {"id", "min", "q1", "median", "q3", "max"}
    if not rows or not expected_fields <= set(rows[0]):
        raise PublicDatabaseError("ARCHS4 expression CSV lacks the required summary-statistic fields")
    observations = []
    hierarchy_rows = 0
    malformed_rows = 0
    for row in rows:
        label = _clean_text(row.get("id"), limit=2000)
        if not label:
            malformed_rows += 1
            continue
        try:
            minimum, q1, median, q3, maximum = (float(row[field]) for field in ("min", "q1", "median", "q3", "max"))
        except (TypeError, ValueError):
            hierarchy_rows += 1
            continue
        if not all(value >= 0 for value in (minimum, q1, median, q3, maximum)) or not minimum <= q1 <= median <= q3 <= maximum:
            malformed_rows += 1
            continue
        observations.append({"label": label, "minimum": minimum, "q1": q1, "median": median, "q3": q3, "maximum": maximum})
    observations.sort(key=lambda item: (-item["median"], item["label"]))
    return {
        "gene_symbol": normalized_gene,
        "species": normalized_species,
        "atlas": normalized_atlas,
        "observation_count": len(observations),
        "returned_count": min(len(observations), max_records),
        "truncated": len(observations) > max_records,
        "hierarchy_row_count": hierarchy_rows,
        "malformed_row_count": malformed_rows,
        "observations": observations[:max_records],
        "provenance": {"service": "ARCHS4 expression atlas", "contract_version": ARCHS4_EXPRESSION_CONTRACT_VERSION, "transport": transport},
        "limitations": [
            "ARCHS4 is a public cross-study expression resource; its summary statistics do not establish differential expression, tissue specificity, cell type specificity, disease relevance, or causal mechanism.",
            "Rows without all numeric summary statistics are hierarchy labels rather than observations and are excluded from ranked expression records.",
            "Use a study-design-aware project analysis with declared samples, normalization, covariates, and biological replication for inferential claims.",
        ],
    }


def hpo_term_records(hpo_ids: list[str], *, client: PublicJSONClient | None = None) -> dict[str, Any]:
    """Resolve bounded HPO identifiers while retaining explicit not-found states."""
    if not isinstance(hpo_ids, list) or not 1 <= len(hpo_ids) <= 100:
        raise ValueError("hpo_ids must contain 1..100 identifiers")
    normalized_ids = [term.strip().upper() for term in hpo_ids]
    if len(set(normalized_ids)) != len(normalized_ids) or any(not re.fullmatch(r"HP:[0-9]{7}", term) for term in normalized_ids):
        raise ValueError("hpo_ids must be unique HPO identifiers in HP:0000000 form")
    client = client or PublicJSONClient()
    records = []
    not_found = []
    for term_id in normalized_ids:
        payload, transport = client.get_with_metadata(
            "https://ontology.jax.org", f"/api/hp/terms/{quote(term_id, safe='')}", not_found_as_empty_object=True
        )
        if transport.get("not_found"):
            not_found.append(term_id)
            continue
        if payload.get("id") != term_id or not isinstance(payload.get("name"), str) or not payload["name"].strip():
            raise PublicDatabaseError("HPO term response does not preserve the requested identifier and name")
        synonyms = sorted({_clean_text(value, limit=1000) for value in payload.get("synonyms", []) if _clean_text(value, limit=1000)})
        records.append({"id": term_id, "name": _clean_text(payload["name"], limit=1000), "definition": _clean_text(payload.get("definition"), limit=10000), "synonyms": synonyms[:100], "synonyms_truncated": len(synonyms) > 100, "descendant_count": payload.get("descendantCount") if isinstance(payload.get("descendantCount"), int) and payload["descendantCount"] >= 0 else None, "transport": transport})
    return {"requested_ids": normalized_ids, "returned_count": len(records), "not_found_ids": not_found, "records": records, "provenance": {"service": "Human Phenotype Ontology API", "contract_version": HPO_TERM_CONTRACT_VERSION}, "limitations": ["An HPO term label, definition, synonym, or hierarchy count does not establish that a participant has the phenotype, that a diagnosis is correct, or that a gene, variant, or intervention is causal.", "Clinical phenotyping requires source records, temporal context, negated findings, ascertainment, and qualified review."]}


def uniprot_protein_record(accession: str, *, client: PublicJSONClient | None = None) -> dict[str, Any]:
    """Retrieve identity-critical fields for one exact UniProtKB accession."""
    normalized = _require_uniprot_accession(accession)
    payload, transport = (client or PublicJSONClient()).get_with_metadata(
        "https://rest.uniprot.org", f"/uniprotkb/{quote(normalized, safe='')}.json"
    )
    if payload.get("primaryAccession") != normalized or not isinstance(payload.get("uniProtkbId"), str):
        raise PublicDatabaseError("UniProtKB response does not preserve the requested accession and entry identifier")
    organism = payload.get("organism") if isinstance(payload.get("organism"), dict) else {}
    sequence = payload.get("sequence") if isinstance(payload.get("sequence"), dict) else {}
    genes = []
    for item in payload.get("genes", []):
        if not isinstance(item, dict):
            continue
        name = item.get("geneName") if isinstance(item.get("geneName"), dict) else {}
        value = _clean_text(name.get("value"), limit=500)
        if value:
            genes.append(value)
    description = payload.get("proteinDescription") if isinstance(payload.get("proteinDescription"), dict) else {}
    recommended = description.get("recommendedName") if isinstance(description.get("recommendedName"), dict) else {}
    full_name = recommended.get("fullName") if isinstance(recommended.get("fullName"), dict) else {}
    length = sequence.get("length")
    if not isinstance(length, int) or length <= 0:
        raise PublicDatabaseError("UniProtKB response lacks a positive sequence length")
    return {"accession": normalized, "entry_id": _clean_text(payload["uniProtkbId"], limit=500), "entry_type": _clean_text(payload.get("entryType"), limit=500), "protein_name": _clean_text(full_name.get("value"), limit=2000), "gene_names": sorted(set(genes)), "organism": {"scientific_name": _clean_text(organism.get("scientificName"), limit=1000), "taxon_id": organism.get("taxonId") if isinstance(organism.get("taxonId"), int) else None}, "sequence": {"length": length, "molecular_weight": sequence.get("molWeight") if isinstance(sequence.get("molWeight"), int) else None, "crc64": _clean_text(sequence.get("crc64"), limit=100), "md5": _clean_text(sequence.get("md5"), limit=100)}, "provenance": {"service": "UniProtKB REST API", "contract_version": UNIPROT_RECORD_CONTRACT_VERSION, "transport": transport}, "limitations": ["A UniProt record establishes a database identity and annotation snapshot, not protein abundance, tissue activity, disease mechanism, interaction, phenotype, or causal effect.", "Review status and annotations can change; retain the accession, observed contract, and retrieval provenance for downstream use."]}


def uniprot_to_ensembl_gene_mapping(
    accessions: list[str], max_polls: int = 12, *, client: PublicJSONClient | None = None
) -> dict[str, Any]:
    """Map bounded UniProt accessions to Ensembl gene IDs via a fixed job contract."""
    if not 1 <= len(accessions) <= 500 or not 1 <= max_polls <= 30:
        raise ValueError("accessions and max_polls are outside the bounded contract")
    normalized = [_require_uniprot_accession(accession).upper() for accession in accessions]
    if len(set(normalized)) != len(normalized):
        raise ValueError("accessions must be unique")
    active = client or PublicJSONClient()
    submitted, submission_transport = active.post_form_with_metadata("https://rest.uniprot.org", "/idmapping/run", {"from": "UniProtKB_AC-ID", "to": "Ensembl", "ids": ",".join(normalized)})
    job_id = _clean_text(submitted.get("jobId"), limit=100)
    if not job_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", job_id):
        raise PublicDatabaseError("UniProt mapping submission lacks a bounded job identifier")
    result_payload, polls = None, []
    for _ in range(max_polls):
        payload, transport = active.get_with_metadata("https://rest.uniprot.org", f"/idmapping/status/{quote(job_id, safe='')}")
        polls.append(transport)
        if isinstance(payload.get("results"), list):
            result_payload = payload
            break
        if _clean_text(payload.get("jobStatus"), limit=100) not in {"RUNNING", "NEW"}:
            raise PublicDatabaseError("UniProt mapping job returned an unsupported terminal state")
    if result_payload is None:
        raise PublicDatabaseError("UniProt mapping job did not finish within the declared polling bound")
    mapped = {accession: set() for accession in normalized}
    for item in result_payload["results"]:
        if not isinstance(item, dict):
            continue
        source, target = _clean_text(item.get("from"), limit=100), _clean_text(item.get("to"), limit=100)
        if source in mapped and target and re.fullmatch(r"ENS[A-Z]*G[0-9]+(?:\.[0-9]+)?", target):
            mapped[source].add(target)
    records = [{"accession": accession, "ensembl_gene_ids": sorted(mapped[accession]), "mapped": bool(mapped[accession])} for accession in normalized]
    return {"requested_accessions": normalized, "job_id": job_id, "poll_count": len(polls), "mapped_count": sum(record["mapped"] for record in records), "unmapped_accessions": [record["accession"] for record in records if not record["mapped"]], "records": records, "provenance": {"service": "UniProt ID Mapping", "contract_version": UNIPROT_TO_ENSEMBL_MAPPING_CONTRACT_VERSION, "submission_transport": submission_transport, "poll_transports": polls}, "limitations": ["This service mapping is identifier reconciliation, not orthology, transcript selection, annotation-release equivalence, gene-function evidence, or a biological conclusion."]}


def quickgo_term_records(go_ids: list[str], *, client: PublicJSONClient | None = None) -> dict[str, Any]:
    """Resolve exact GO term identifiers through the bounded QuickGO term API."""
    if not isinstance(go_ids, list) or not 1 <= len(go_ids) <= 100:
        raise ValueError("go_ids must contain 1..100 identifiers")
    normalized = [value.strip().upper() for value in go_ids]
    if len(set(normalized)) != len(normalized) or any(not re.fullmatch(r"GO:[0-9]{7}", value) for value in normalized):
        raise ValueError("go_ids must be unique GO identifiers in GO:0000000 form")
    client = client or PublicJSONClient()
    records, not_found = [], []
    for term_id in normalized:
        payload, transport = client.get_with_metadata("https://www.ebi.ac.uk", f"/QuickGO/services/ontology/go/terms/{quote(term_id, safe='')}", not_found_as_empty_object=True)
        if transport.get("not_found"):
            not_found.append(term_id)
            continue
        results = payload.get("results")
        if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
            raise PublicDatabaseError("QuickGO term response lacks one exact result")
        item = results[0]
        if item.get("id") != term_id or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise PublicDatabaseError("QuickGO response does not preserve requested GO ID and term name")
        definition = item.get("definition") if isinstance(item.get("definition"), dict) else {}
        synonyms = sorted({_clean_text(value.get("name"), limit=1000) for value in item.get("synonyms", []) if isinstance(value, dict) and _clean_text(value.get("name"), limit=1000)})
        records.append({"id": term_id, "name": _clean_text(item["name"], limit=1000), "aspect": _clean_text(item.get("aspect"), limit=100), "is_obsolete": bool(item.get("isObsolete", False)), "definition": _clean_text(definition.get("text"), limit=10000), "synonyms": synonyms[:100], "synonyms_truncated": len(synonyms) > 100, "transport": transport})
    return {"requested_ids": normalized, "returned_count": len(records), "not_found_ids": not_found, "records": records, "provenance": {"service": "QuickGO ontology API", "contract_version": QUICKGO_TERM_CONTRACT_VERSION}, "limitations": ["A GO term label, definition, aspect, or synonym does not establish gene function, expression, pathway activity, mechanism, or causality in a project.", "Use evidence-coded annotations, a declared gene universe, multiple-testing control, and project data before functional claims."]}


class PublicJSONClient:
    """HTTPS-only JSON transport with host allow-listing and bounded retries."""

    def __init__(
        self,
        *,
        transport: Transport | None = None,
        post_transport: PostTransport | None = None,
        timeout: float = 20.0,
        retries: int = 2,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout <= 0 or retries < 0:
            raise ValueError("timeout must be positive and retries non-negative")
        self._transport = transport or _default_transport
        self._post_transport = post_transport or _default_post_transport
        self._timeout = timeout
        self._retries = retries
        self._sleeper = sleeper

    def get_with_metadata(
        self,
        base_url: str,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        not_found_as_empty_object: bool = False,
        api_key: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not path.startswith("/") or ".." in path:
            raise ValueError("database path must be absolute and traversal-free")
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS or parsed.path or parsed.query:
            raise ValueError("database base URL is not approved")
        query = urlencode({key: value for key, value in (params or {}).items() if value is not None}, doseq=True)
        url = f"{base_url}{path}{'?' + query if query else ''}"
        headers = {
            "Accept": "application/json",
            "User-Agent": "biomed-workbench/0.2 (+https://github.com/JunyanKang/biomed-workbench)",
        }
        if api_key is not None:
            if not isinstance(api_key, str) or not api_key.strip():
                raise ValueError("api_key must be nonempty when supplied")
            headers["api-key"] = api_key.strip()
        response: HTTPResponse | None = None
        attempts = 0
        for attempt in range(self._retries + 1):
            attempts = attempt + 1
            try:
                response = self._transport(url, headers, self._timeout)
            except PublicDatabaseError:
                if attempt >= self._retries:
                    raise
                self._sleeper(min(2**attempt, 4))
                continue
            if response.status not in {429, 500, 502, 503, 504} or attempt >= self._retries:
                break
            self._sleeper(min(2**attempt, 4))
        assert response is not None
        metadata = {"url": url, "status_code": response.status, "bytes": len(response.body), "attempts": attempts}
        if response.status == 404 and not_found_as_empty_object:
            return {}, {**metadata, "not_found": True}
        if response.status < 200 or response.status >= 300:
            raise PublicDatabaseError(f"public database request failed with HTTP {response.status}")
        if len(response.body) > _MAX_RESPONSE_BYTES:
            raise PublicDatabaseError("public database response exceeded the 20 MiB safety limit")
        try:
            payload = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise PublicDatabaseError("public database returned invalid JSON") from None
        if not isinstance(payload, dict):
            raise PublicDatabaseError("public database JSON root must be an object")
        return payload, metadata

    def get(self, base_url: str, path: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload, _metadata = self.get_with_metadata(base_url, path, params)
        return payload

    def get_text_with_metadata(
        self,
        base_url: str,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        accepted_content_types: tuple[str, ...] = ("text/csv", "text/plain", "application/octet-stream"),
    ) -> tuple[str, dict[str, Any]]:
        """Retrieve bounded text without treating a non-JSON endpoint as JSON."""
        if not path.startswith("/") or ".." in path:
            raise ValueError("database path must be absolute and traversal-free")
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS or parsed.path or parsed.query:
            raise ValueError("database base URL is not approved")
        query = urlencode({key: value for key, value in (params or {}).items() if value is not None}, doseq=True)
        url = f"{base_url}{path}{'?' + query if query else ''}"
        headers = {
            "Accept": ", ".join(accepted_content_types),
            "User-Agent": "biomed-workbench/0.2 (+https://github.com/JunyanKang/biomed-workbench)",
        }
        response: HTTPResponse | None = None
        attempts = 0
        for attempt in range(self._retries + 1):
            attempts = attempt + 1
            try:
                response = self._transport(url, headers, self._timeout)
            except PublicDatabaseError:
                if attempt >= self._retries:
                    raise
                self._sleeper(min(2**attempt, 4))
                continue
            if response.status not in {429, 500, 502, 503, 504} or attempt >= self._retries:
                break
            self._sleeper(min(2**attempt, 4))
        assert response is not None
        if response.status < 200 or response.status >= 300:
            raise PublicDatabaseError(f"public database request failed with HTTP {response.status}")
        if len(response.body) > _MAX_RESPONSE_BYTES:
            raise PublicDatabaseError("public database response exceeded the 20 MiB safety limit")
        content_type = response.headers.get("Content-Type", "").lower()
        if content_type and not any(token in content_type for token in accepted_content_types):
            raise PublicDatabaseError("public database returned an unexpected text content type")
        try:
            text = response.body.decode("utf-8")
        except UnicodeDecodeError:
            raise PublicDatabaseError("public database text response is not UTF-8") from None
        return text, {"url": url, "status_code": response.status, "bytes": len(response.body), "attempts": attempts, "content_type": content_type or None}

    def get_array_with_metadata(
        self,
        base_url: str,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        not_found_as_empty: bool = False,
    ) -> tuple[list[Any], dict[str, Any]]:
        """Retrieve a bounded JSON array while retaining an explicit 404 state."""
        if not path.startswith("/") or ".." in path:
            raise ValueError("database path must be absolute and traversal-free")
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS or parsed.path or parsed.query:
            raise ValueError("database base URL is not approved")
        query = urlencode({key: value for key, value in (params or {}).items() if value is not None}, doseq=True)
        url = f"{base_url}{path}{'?' + query if query else ''}"
        headers = {
            "Accept": "application/json",
            "User-Agent": "biomed-workbench/0.2 (+https://github.com/JunyanKang/biomed-workbench)",
        }
        response: HTTPResponse | None = None
        attempts = 0
        for attempt in range(self._retries + 1):
            attempts = attempt + 1
            try:
                response = self._transport(url, headers, self._timeout)
            except PublicDatabaseError:
                if attempt >= self._retries:
                    raise
                self._sleeper(min(2**attempt, 4))
                continue
            if response.status not in {429, 500, 502, 503, 504} or attempt >= self._retries:
                break
            self._sleeper(min(2**attempt, 4))
        assert response is not None
        metadata = {
            "url": url,
            "status_code": response.status,
            "bytes": len(response.body),
            "attempts": attempts,
        }
        if response.status == 404 and not_found_as_empty:
            return [], {**metadata, "not_found": True}
        if response.status < 200 or response.status >= 300:
            raise PublicDatabaseError(f"public database request failed with HTTP {response.status}")
        if len(response.body) > _MAX_RESPONSE_BYTES:
            raise PublicDatabaseError("public database response exceeded the 20 MiB safety limit")
        try:
            payload = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise PublicDatabaseError("public database returned invalid JSON") from None
        if not isinstance(payload, list):
            raise PublicDatabaseError("public database JSON root must be an array")
        return payload, metadata

    def post_with_metadata(
        self,
        base_url: str,
        path: str,
        payload: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not path.startswith("/") or ".." in path:
            raise ValueError("database path must be absolute and traversal-free")
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS or parsed.path or parsed.query:
            raise ValueError("database base URL is not approved")
        if not isinstance(payload, Mapping):
            raise ValueError("database POST payload must be an object")
        body = json.dumps(dict(payload), separators=(",", ":"), sort_keys=True).encode("utf-8")
        if len(body) > _MAX_REQUEST_BYTES:
            raise ValueError("public database request exceeded the 1 MiB safety limit")
        url = f"{base_url}{path}"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "biomed-workbench/0.2 (+https://github.com/JunyanKang/biomed-workbench)",
        }
        response: HTTPResponse | None = None
        attempts = 0
        for attempt in range(self._retries + 1):
            attempts = attempt + 1
            try:
                response = self._post_transport(url, headers, body, self._timeout)
            except PublicDatabaseError:
                if attempt >= self._retries:
                    raise
                self._sleeper(min(2**attempt, 4))
                continue
            if response.status not in {429, 500, 502, 503, 504} or attempt >= self._retries:
                break
            self._sleeper(min(2**attempt, 4))
        assert response is not None
        if response.status < 200 or response.status >= 300:
            raise PublicDatabaseError(f"public database request failed with HTTP {response.status}")
        if len(response.body) > _MAX_RESPONSE_BYTES:
            raise PublicDatabaseError("public database response exceeded the 20 MiB safety limit")
        if response.status == 204 and not response.body:
            decoded = {}
        else:
            try:
                decoded = json.loads(response.body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise PublicDatabaseError("public database returned invalid JSON") from None
        if not isinstance(decoded, dict):
            raise PublicDatabaseError("public database JSON root must be an object")
        return decoded, {
            "url": url,
            "status_code": response.status,
            "request_bytes": len(body),
            "response_bytes": len(response.body),
            "attempts": attempts,
        }

    def post_array_with_metadata(
        self, base_url: str, path: str, payload: Mapping[str, Any], params: Mapping[str, Any] | None = None
    ) -> tuple[list[Any], dict[str, Any]]:
        """POST a bounded JSON object to a fixed endpoint that returns an array."""
        if not path.startswith("/") or ".." in path:
            raise ValueError("database path must be absolute and traversal-free")
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS or parsed.path or parsed.query:
            raise ValueError("database base URL is not approved")
        if not isinstance(payload, Mapping):
            raise ValueError("database POST payload must be an object")
        body = json.dumps(dict(payload), separators=(",", ":"), sort_keys=True).encode("utf-8")
        if len(body) > _MAX_REQUEST_BYTES:
            raise ValueError("public database request exceeded the 1 MiB safety limit")
        query = urlencode({key: value for key, value in (params or {}).items() if value is not None}, doseq=True)
        url = f"{base_url}{path}{'?' + query if query else ''}"
        headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "biomed-workbench/0.2 (+https://github.com/JunyanKang/biomed-workbench)"}
        response: HTTPResponse | None = None
        attempts = 0
        for attempt in range(self._retries + 1):
            attempts = attempt + 1
            try:
                response = self._post_transport(url, headers, body, self._timeout)
            except PublicDatabaseError:
                if attempt >= self._retries:
                    raise
                self._sleeper(min(2**attempt, 4))
                continue
            if response.status not in {429, 500, 502, 503, 504} or attempt >= self._retries:
                break
            self._sleeper(min(2**attempt, 4))
        assert response is not None
        if response.status < 200 or response.status >= 300:
            raise PublicDatabaseError(f"public database request failed with HTTP {response.status}")
        if len(response.body) > _MAX_RESPONSE_BYTES:
            raise PublicDatabaseError("public database response exceeded the 20 MiB safety limit")
        try:
            decoded = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise PublicDatabaseError("public database returned invalid JSON") from None
        if not isinstance(decoded, list):
            raise PublicDatabaseError("public database JSON root must be an array")
        return decoded, {"url": url, "status_code": response.status, "request_bytes": len(body), "response_bytes": len(response.body), "attempts": attempts}

    def post_text_with_metadata(self, base_url: str, path: str, text: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """POST bounded UTF-8 text to a fixed approved endpoint and parse JSON."""
        if not path.startswith("/") or ".." in path:
            raise ValueError("database path must be absolute and traversal-free")
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS or parsed.path or parsed.query:
            raise ValueError("database base URL is not approved")
        body = text.encode("utf-8")
        if not body or len(body) > _MAX_REQUEST_BYTES:
            raise ValueError("public database text request is empty or exceeds the 1 MiB safety limit")
        url = f"{base_url}{path}"
        headers = {"Accept": "application/json", "Content-Type": "text/plain; charset=utf-8", "User-Agent": "biomed-workbench/0.2 (+https://github.com/JunyanKang/biomed-workbench)"}
        response = self._post_transport(url, headers, body, self._timeout)
        if response.status < 200 or response.status >= 300:
            raise PublicDatabaseError(f"public database request failed with HTTP {response.status}")
        if len(response.body) > _MAX_RESPONSE_BYTES:
            raise PublicDatabaseError("public database response exceeded the 20 MiB safety limit")
        try:
            decoded = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise PublicDatabaseError("public database returned invalid JSON") from None
        if not isinstance(decoded, dict):
            raise PublicDatabaseError("public database JSON root must be an object")
        return decoded, {"url": url, "status_code": response.status, "request_bytes": len(body), "response_bytes": len(response.body), "attempts": 1}

    def post_form_with_metadata(self, base_url: str, path: str, values: Mapping[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
        """POST a bounded URL-encoded form to a fixed approved endpoint."""
        if not path.startswith("/") or ".." in path:
            raise ValueError("database path must be absolute and traversal-free")
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS or parsed.path or parsed.query:
            raise ValueError("database base URL is not approved")
        if not values or any(not isinstance(key, str) or not isinstance(value, str) for key, value in values.items()):
            raise ValueError("public database form values must be nonempty strings")
        body = urlencode(dict(values)).encode("ascii")
        if len(body) > _MAX_REQUEST_BYTES:
            raise ValueError("public database form request exceeded the 1 MiB safety limit")
        url = f"{base_url}{path}"
        headers = {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "biomed-workbench/0.2 (+https://github.com/JunyanKang/biomed-workbench)"}
        response = self._post_transport(url, headers, body, self._timeout)
        if response.status < 200 or response.status >= 300:
            raise PublicDatabaseError(f"public database request failed with HTTP {response.status}")
        try:
            decoded = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise PublicDatabaseError("public database returned invalid JSON") from None
        if not isinstance(decoded, dict):
            raise PublicDatabaseError("public database JSON root must be an object")
        return decoded, {"url": url, "status_code": response.status, "request_bytes": len(body), "response_bytes": len(response.body), "attempts": 1}

    def post_form_array_with_metadata(self, base_url: str, path: str, values: Mapping[str, str]) -> tuple[list[Any], dict[str, Any]]:
        """POST a bounded form to a fixed endpoint whose JSON root is an array."""
        if not path.startswith("/") or ".." in path:
            raise ValueError("database path must be absolute and traversal-free")
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS or parsed.path or parsed.query:
            raise ValueError("database base URL is not approved")
        if not values or any(not isinstance(key, str) or not isinstance(value, str) for key, value in values.items()):
            raise ValueError("public database form values must be nonempty strings")
        body = urlencode(dict(values)).encode("ascii")
        if len(body) > _MAX_REQUEST_BYTES:
            raise ValueError("public database form request exceeded the 1 MiB safety limit")
        url = f"{base_url}{path}"
        headers = {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "biomed-workbench/0.2 (+https://github.com/JunyanKang/biomed-workbench)"}
        response = self._post_transport(url, headers, body, self._timeout)
        if response.status < 200 or response.status >= 300:
            raise PublicDatabaseError(f"public database request failed with HTTP {response.status}")
        if len(response.body) > _MAX_RESPONSE_BYTES:
            raise PublicDatabaseError("public database response exceeded the 20 MiB safety limit")
        try:
            decoded = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise PublicDatabaseError("public database returned invalid JSON") from None
        if not isinstance(decoded, list):
            raise PublicDatabaseError("public database JSON root must be an array")
        return decoded, {"url": url, "status_code": response.status, "request_bytes": len(body), "response_bytes": len(response.body), "attempts": 1}


from .public_database_groups.literature_clinical import *  # noqa: F401,F403
from .public_database_groups.structures import *  # noqa: F401,F403
from .public_database_groups.protein_interactions import *  # noqa: F401,F403
def probe_crossref_contract() -> str:
    return CROSSREF_CONTRACT_VERSION


def probe_europe_pmc_contract() -> str:
    return EUROPE_PMC_CONTRACT_VERSION


def probe_biorxiv_contract() -> str:
    return BIORXIV_CONTRACT_VERSION


def probe_pubchem_contract() -> str:
    return PUBCHEM_CONTRACT_VERSION


def probe_clinical_trials_contract() -> str:
    return CLINICAL_TRIALS_CONTRACT_VERSION


def probe_rcsb_contract() -> str:
    return RCSB_CONTRACT_VERSION


def probe_rcsb_search_contract() -> str:
    return RCSB_SEARCH_CONTRACT_VERSION


def probe_alphafold_contract() -> str:
    return ALPHAFOLD_CONTRACT_VERSION


def probe_string_contract() -> str:
    return STRING_CONTRACT_VERSION
