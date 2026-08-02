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


def resolve_citation_record(doi: str, *, client: PublicJSONClient | None = None) -> dict[str, Any]:
    """Resolve one DOI against Crossref and Europe PMC without merging conflicts."""
    doi = _require_doi(doi)
    client = client or PublicJSONClient()
    crossref_payload = client.get("https://api.crossref.org", f"/v1/works/{quote(doi, safe='')}")
    message = crossref_payload.get("message")
    if not isinstance(message, dict) or str(message.get("DOI", "")).lower() != doi:
        raise PublicDatabaseError("Crossref response did not preserve the requested DOI")
    europe_payload = client.get(
        "https://www.ebi.ac.uk",
        "/europepmc/webservices/rest/search",
        {"query": f'DOI:"{doi}"', "format": "json", "resultType": "core", "pageSize": 25},
    )
    result_list = europe_payload.get("resultList", {}).get("result", [])
    if not isinstance(result_list, list):
        raise PublicDatabaseError("Europe PMC search result schema is not recognized")
    europe_records = [record for record in result_list if isinstance(record, dict) and str(record.get("doi", "")).lower() == doi]
    crossref = {
        "doi": doi,
        "title": _clean_text((message.get("title") or [None])[0]),
        "type": _clean_text(message.get("type")),
        "publisher": _clean_text(message.get("publisher")),
        "container_title": _clean_text((message.get("container-title") or [None])[0]),
        "published": message.get("published") or message.get("published-print") or message.get("published-online"),
        "authors": message.get("author") if isinstance(message.get("author"), list) else [],
        "is_referenced_by_count": message.get("is-referenced-by-count"),
        "relation": message.get("relation") if isinstance(message.get("relation"), dict) else {},
        "update_to": message.get("update-to") if isinstance(message.get("update-to"), list) else [],
    }
    return {
        "query": {"doi": doi},
        "crossref": crossref,
        "europe_pmc_records": europe_records,
        "agreement": {
            "doi_confirmed_by_crossref": True,
            "europe_pmc_exact_doi_matches": len(europe_records),
            "title_comparison_required": bool(europe_records and crossref["title"]),
        },
        "provenance": {
            "retrieved_at_runtime": True,
            "services": ["Crossref REST API", "Europe PMC REST API"],
            "contracts": [CROSSREF_CONTRACT_VERSION, EUROPE_PMC_CONTRACT_VERSION],
        },
        "limitations": [
            "Metadata deposits may be incomplete or disagree across services; disagreements must remain explicit.",
            "A resolved DOI does not establish study validity, retraction status, or support for a scientific claim.",
        ],
    }


def preprint_record(doi: str, server: str, *, client: PublicJSONClient | None = None) -> dict[str, Any]:
    """Retrieve versioned bioRxiv or medRxiv metadata and publication links."""
    doi = _require_doi(doi)
    server = server.strip().lower()
    if server not in {"biorxiv", "medrxiv"}:
        raise ValueError("server must be biorxiv or medrxiv")
    client = client or PublicJSONClient()
    # bioRxiv models the DOI as two path segments and rejects an encoded slash.
    payload = client.get("https://api.biorxiv.org", f"/details/{server}/{quote(doi, safe='/')}/na/json")
    collection = payload.get("collection")
    if not isinstance(collection, list):
        raise PublicDatabaseError("bioRxiv details response schema is not recognized")
    versions = [record for record in collection if isinstance(record, dict) and str(record.get("doi", "")).lower() == doi]
    if not versions:
        raise PublicDatabaseError("bioRxiv details response did not contain the requested DOI")
    versions.sort(key=lambda record: (str(record.get("version", "")), str(record.get("date", ""))))
    published = [record.get("published") for record in versions if record.get("published") and record.get("published") != "NA"]
    return {
        "query": {"doi": doi, "server": server},
        "versions": versions,
        "latest_version": versions[-1],
        "published_dois": sorted({str(value).lower() for value in published}),
        "version_count": len(versions),
        "provenance": {
            "retrieved_at_runtime": True,
            "service": f"{server} details API",
            "contract": BIORXIV_CONTRACT_VERSION,
        },
        "limitations": [
            "A preprint is not peer reviewed unless an independently verified publication record is supplied.",
            "Versions must not be collapsed; conclusions and citations must identify the analyzed version.",
        ],
    }


def pubchem_compound(identifier: str, namespace: str = "name", *, client: PublicJSONClient | None = None) -> dict[str, Any]:
    """Retrieve identity-critical PubChem properties and synonyms."""
    value = identifier.strip()
    namespace = namespace.strip().lower()
    if namespace not in {"name", "cid", "inchikey"}:
        raise ValueError("namespace must be name, cid, or inchikey")
    if not value or len(value) > 500 or (namespace == "cid" and not value.isdigit()):
        raise ValueError("compound identifier is invalid")
    client = client or PublicJSONClient()
    encoded = quote(value, safe="")
    properties = "Title,IUPACName,MolecularFormula,MolecularWeight,SMILES,ConnectivitySMILES,InChI,InChIKey,XLogP,TPSA,Charge"
    property_payload = client.get(
        "https://pubchem.ncbi.nlm.nih.gov",
        f"/rest/pug/compound/{namespace}/{encoded}/property/{properties}/JSON",
    )
    rows = property_payload.get("PropertyTable", {}).get("Properties", [])
    if not isinstance(rows, list) or not rows:
        raise PublicDatabaseError("PubChem response contained no compound properties")
    synonym_payload = client.get(
        "https://pubchem.ncbi.nlm.nih.gov",
        f"/rest/pug/compound/cid/{rows[0].get('CID')}/synonyms/JSON",
    )
    information = synonym_payload.get("InformationList", {}).get("Information", [])
    synonyms = information[0].get("Synonym", []) if isinstance(information, list) and information and isinstance(information[0], dict) else []
    return {
        "query": {"identifier": value, "namespace": namespace},
        "compounds": rows,
        "synonyms": synonyms[:200] if isinstance(synonyms, list) else [],
        "identity_checks": {
            "result_count": len(rows),
            "unique_cids": sorted({row.get("CID") for row in rows if isinstance(row, dict) and row.get("CID") is not None}),
            "stereochemistry_fields_retained": all("SMILES" in row and "ConnectivitySMILES" in row and "InChIKey" in row for row in rows if isinstance(row, dict)),
        },
        "provenance": {
            "retrieved_at_runtime": True,
            "service": "PubChem PUG REST",
            "contract": PUBCHEM_CONTRACT_VERSION,
        },
        "limitations": [
            "Name searches can be ambiguous; a scientific claim requires reviewed CID, structure, charge, stereochemistry, and salt form.",
            "Database properties are identifiers and descriptors, not evidence of biological activity or clinical efficacy.",
        ],
    }


def _essie_quote(value: str) -> str:
    if not value.strip() or any(character in value for character in "\r\n"):
        raise ValueError("ClinicalTrials.gov phrase filters must be nonempty single-line strings")
    return '"' + value.replace('"', '\\"') + '"'


def _range_expression(area: str, lower: Any, upper: Any, *, dates: bool = False) -> str:
    if lower is None and upper is None:
        raise ValueError(f"{area} range must contain at least one bound")
    values = []
    for name, value in (("minimum", lower), ("maximum", upper)):
        if value is None:
            values.append("MIN" if name == "minimum" else "MAX")
        elif dates:
            if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
                raise ValueError(f"{area} {name} must use YYYY-MM-DD")
            values.append(value)
        else:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{area} {name} must be a non-negative integer")
            values.append(str(value))
    if lower is not None and upper is not None and lower > upper:
        raise ValueError(f"{area} minimum exceeds maximum")
    return f"AREA[{area}]RANGE[{values[0]},{values[1]}]"


def _clinical_trial_params(query: str | None, filters: Mapping[str, Any], advanced_query: str | None) -> tuple[dict[str, Any], list[str]]:
    allowed = {
        "condition", "intervention", "overall_status", "phase", "study_type", "enrollment_min", "enrollment_max",
        "primary_completion_start", "primary_completion_end", "first_posted_start", "first_posted_end",
        "location_country", "lead_sponsor_class", "investigator", "sex", "healthy_volunteers",
        "minimum_age", "maximum_age", "location_city", "location_state", "location_recruiting_only",
        "sponsor_name", "sponsor_scope", "eligibility_keywords", "investigator_role",
    }
    unknown = sorted(set(filters) - allowed)
    if unknown:
        raise ValueError(f"unsupported ClinicalTrials.gov filters: {', '.join(unknown)}")
    params: dict[str, Any] = {}
    if query:
        if len(query) > 2_000 or any(character in query for character in "\r\n"):
            raise ValueError("query must be a bounded single-line expression")
        params["query.term"] = query
    if filters.get("condition"):
        params["query.cond"] = str(filters["condition"])
    if filters.get("intervention"):
        params["query.intr"] = str(filters["intervention"])
    statuses = list(filters.get("overall_status") or [])
    if any(status not in _CT_STATUSES for status in statuses):
        raise ValueError("overall_status contains an unsupported API v2 enum")
    if statuses:
        params["filter.overallStatus"] = "|".join(statuses)
    advanced = []
    phases = list(filters.get("phase") or [])
    if any(phase not in _CT_PHASES for phase in phases):
        raise ValueError("phase contains an unsupported API v2 enum")
    if phases:
        phase_terms = [f"AREA[Phase]{phase}" for phase in phases]
        advanced.append(phase_terms[0] if len(phase_terms) == 1 else "(" + " OR ".join(phase_terms) + ")")
    study_type = filters.get("study_type")
    if study_type:
        if study_type not in _CT_STUDY_TYPES:
            raise ValueError("study_type contains an unsupported API v2 enum")
        advanced.append(f"AREA[StudyType]{study_type}")
    if filters.get("enrollment_min") is not None or filters.get("enrollment_max") is not None:
        advanced.append(_range_expression("EnrollmentCount", filters.get("enrollment_min"), filters.get("enrollment_max")))
    if filters.get("primary_completion_start") or filters.get("primary_completion_end"):
        advanced.append(_range_expression("PrimaryCompletionDate", filters.get("primary_completion_start"), filters.get("primary_completion_end"), dates=True))
    if filters.get("first_posted_start") or filters.get("first_posted_end"):
        advanced.append(_range_expression("StudyFirstPostDate", filters.get("first_posted_start"), filters.get("first_posted_end"), dates=True))
    sponsor_class = filters.get("lead_sponsor_class")
    if sponsor_class:
        if sponsor_class not in _CT_SPONSOR_CLASSES:
            raise ValueError("lead_sponsor_class contains an unsupported API v2 enum")
        advanced.append(f"AREA[LeadSponsorClass]{sponsor_class}")
    if filters.get("investigator"):
        name = _essie_quote(str(filters["investigator"]))
        role = filters.get("investigator_role", "any")
        if role == "official":
            advanced.append(f"AREA[OverallOfficialName]{name}")
        elif role == "responsible_party":
            advanced.append(f"AREA[ResponsiblePartyInvestigatorFullName]{name}")
        elif role == "any":
            advanced.append(f"(AREA[OverallOfficialName]{name} OR AREA[ResponsiblePartyInvestigatorFullName]{name})")
        else:
            raise ValueError("investigator_role must be any, official, or responsible_party")
    elif filters.get("investigator_role") is not None:
        raise ValueError("investigator_role requires investigator")
    if filters.get("sponsor_name"):
        name = _essie_quote(str(filters["sponsor_name"]))
        scope = filters.get("sponsor_scope", "lead")
        if scope == "lead":
            advanced.append(f"AREA[LeadSponsorName]{name}")
        elif scope == "any":
            advanced.append(f"(AREA[LeadSponsorName]{name} OR AREA[CollaboratorName]{name})")
        else:
            raise ValueError("sponsor_scope must be lead or any")
    elif filters.get("sponsor_scope") is not None:
        raise ValueError("sponsor_scope requires sponsor_name")
    eligibility_keywords = filters.get("eligibility_keywords") or []
    if not isinstance(eligibility_keywords, list) or len(eligibility_keywords) > 20:
        raise ValueError("eligibility_keywords must be a list of at most 20 phrases")
    for keyword in eligibility_keywords:
        advanced.append(f"AREA[EligibilityCriteria]{_essie_quote(str(keyword))}")
    sex = filters.get("sex")
    if sex:
        if sex not in {"FEMALE", "MALE", "ALL"}:
            raise ValueError("sex must be FEMALE, MALE, or ALL")
        advanced.append(f"AREA[Sex]{sex}")
    if filters.get("healthy_volunteers") is not None:
        if not isinstance(filters["healthy_volunteers"], bool):
            raise ValueError("healthy_volunteers must be boolean")
        advanced.append(f"AREA[HealthyVolunteers]{'y' if filters['healthy_volunteers'] else 'n'}")
    if filters.get("minimum_age"):
        advanced.append(f"AREA[MinimumAge]RANGE[{filters['minimum_age']},MAX]")
    if filters.get("maximum_age"):
        advanced.append(f"AREA[MaximumAge]RANGE[MIN,{filters['maximum_age']}]")
    location_terms = []
    for key, area in (("location_city", "LocationCity"), ("location_state", "LocationState")):
        if filters.get(key):
            location_terms.append(f"AREA[{area}]{_essie_quote(str(filters[key]))}")
    if filters.get("location_recruiting_only"):
        if not isinstance(filters["location_recruiting_only"], bool):
            raise ValueError("location_recruiting_only must be boolean")
        location_terms.append("AREA[LocationStatus]RECRUITING")
    if filters.get("location_country"):
        location_terms.append(f"AREA[LocationCountry]{_essie_quote(str(filters['location_country']))}")
    if location_terms:
        advanced.append("SEARCH[Location](" + " AND ".join(location_terms) + ")")
    if advanced_query:
        if len(advanced_query) > 4_000 or any(character in advanced_query for character in "\r\n"):
            raise ValueError("advanced_query must be a bounded single-line Essie expression")
        advanced.append(f"({advanced_query})")
    if advanced:
        params["filter.advanced"] = " AND ".join(advanced)
    if not params:
        raise ValueError("at least one query, filter, or advanced expression is required")
    return params, advanced


def _trim_clinical_trial(study: Mapping[str, Any], *, include_full_record: bool) -> dict[str, Any]:
    protocol = study.get("protocolSection", {}) if isinstance(study, Mapping) else {}
    identification = protocol.get("identificationModule", {}) or {}
    design = protocol.get("designModule", {}) or {}
    status = protocol.get("statusModule", {}) or {}
    conditions = protocol.get("conditionsModule", {}) or {}
    arms = protocol.get("armsInterventionsModule", {}) or {}
    sponsor = (protocol.get("sponsorCollaboratorsModule", {}) or {}).get("leadSponsor", {}) or {}
    contacts = protocol.get("contactsLocationsModule", {}) or {}
    outcomes = protocol.get("outcomesModule", {}) or {}
    eligibility = protocol.get("eligibilityModule", {}) or {}
    nct_id = identification.get("nctId")
    if not isinstance(nct_id, str) or not _NCT_RE.fullmatch(nct_id):
        raise PublicDatabaseError("ClinicalTrials.gov study lacks a valid NCT identifier")
    locations = contacts.get("locations", []) or []
    record = {
        "nct_id": nct_id.upper(),
        "brief_title": _clean_text(identification.get("briefTitle")),
        "official_title": _clean_text(identification.get("officialTitle")),
        "overall_status": status.get("overallStatus"),
        "status_dates": {
            "verified": status.get("statusVerifiedDate"),
            "first_posted": (status.get("studyFirstPostDateStruct") or {}).get("date"),
            "last_update_posted": (status.get("lastUpdatePostDateStruct") or {}).get("date"),
            "primary_completion": (status.get("primaryCompletionDateStruct") or {}).get("date"),
        },
        "study_type": design.get("studyType"),
        "phases": design.get("phases", []) or [],
        "enrollment": design.get("enrollmentInfo", {}) or {},
        "design_info": design.get("designInfo", {}) or {},
        "conditions": conditions.get("conditions", []) or [],
        "interventions": [
            {"type": item.get("type"), "name": item.get("name"), "other_names": item.get("otherNames", []) or []}
            for item in arms.get("interventions", []) or []
            if isinstance(item, Mapping)
        ],
        "lead_sponsor": {"name": sponsor.get("name"), "class": sponsor.get("class")},
        "eligibility": {
            "sex": eligibility.get("sex"),
            "minimum_age": eligibility.get("minimumAge"),
            "maximum_age": eligibility.get("maximumAge"),
            "healthy_volunteers": eligibility.get("healthyVolunteers"),
        },
        "outcome_counts": {
            "primary": len(outcomes.get("primaryOutcomes", []) or []),
            "secondary": len(outcomes.get("secondaryOutcomes", []) or []),
            "other": len(outcomes.get("otherOutcomes", []) or []),
        },
        "locations": [
            {
                "facility": item.get("facility"), "status": item.get("status"), "city": item.get("city"),
                "state": item.get("state"), "country": item.get("country"),
            }
            for item in locations
            if isinstance(item, Mapping)
        ],
        "has_results": bool(study.get("hasResults")),
        "results_section_present": isinstance(study.get("resultsSection"), Mapping),
    }
    if include_full_record:
        record["source_record"] = dict(study)
    return record


def clinical_trial_records(
    query: str | None = None,
    page_size: int = 100,
    filters: Mapping[str, Any] | None = None,
    max_records: int = 1_000,
    advanced_query: str | None = None,
    include_full_record: bool = False,
    *,
    client: PublicJSONClient | None = None,
) -> dict[str, Any]:
    """Retrieve a count-verified, deterministically ordered API v2 cohort."""
    query = query.strip() if query else None
    if not 1 <= page_size <= 1_000 or not 1 <= max_records <= 10_000:
        raise ValueError("page_size must be 1..1000 and max_records must be 1..10000")
    if not isinstance(include_full_record, bool):
        raise ValueError("include_full_record must be boolean")
    declared_filters = dict(filters or {})
    base_params, generated_advanced = _clinical_trial_params(query, declared_filters, advanced_query)
    client = client or PublicJSONClient()
    raw_studies: list[dict[str, Any]] = []
    provenance = []
    total_count: int | None = None
    page_token: str | None = None
    page_index = 0
    while len(raw_studies) < max_records:
        remaining = max_records - len(raw_studies)
        params = {**base_params, "pageSize": min(page_size, remaining), "format": "json"}
        if page_index == 0:
            params["countTotal"] = "true"
        if page_token:
            params["pageToken"] = page_token
        payload, request_meta = client.get_with_metadata("https://clinicaltrials.gov", "/api/v2/studies", params)
        page = payload.get("studies", [])
        if not isinstance(page, list):
            raise PublicDatabaseError("ClinicalTrials.gov response schema is not recognized")
        if page_index == 0:
            try:
                total_count = int(payload["totalCount"])
            except (KeyError, TypeError, ValueError):
                raise PublicDatabaseError("ClinicalTrials.gov first page lacks a valid totalCount") from None
        raw_studies.extend(item for item in page if isinstance(item, dict))
        provenance.append(
            {
                "page_index": page_index,
                "page_token_used": page_token,
                "request": request_meta,
                "parameters": params,
                "studies_in_page": len(page),
                "total_count": total_count if page_index == 0 else None,
            }
        )
        page_token = payload.get("nextPageToken")
        page_index += 1
        if not page_token:
            break
    assert total_count is not None
    by_id: dict[str, dict[str, Any]] = {}
    duplicate_ids = []
    for study in raw_studies:
        record = _trim_clinical_trial(study, include_full_record=include_full_record)
        if record["nct_id"] in by_id:
            duplicate_ids.append(record["nct_id"])
        else:
            by_id[record["nct_id"]] = record
    nct_ids = sorted(by_id)
    records_truncated = total_count > len(nct_ids)
    if not records_truncated and len(nct_ids) != total_count:
        raise PublicDatabaseError("ClinicalTrials.gov completed pagination does not reconcile with totalCount")
    return {
        "query": {
            "term": query,
            "filters": declared_filters,
            "advanced_query": advanced_query,
            "generated_advanced_terms": generated_advanced,
            "page_size": page_size,
            "max_records": max_records,
            "include_full_record": include_full_record,
        },
        "api_total_count": total_count,
        "returned_count": len(nct_ids),
        "nct_ids": nct_ids,
        "studies": [by_id[nct_id] for nct_id in nct_ids],
        "records_truncated": records_truncated,
        "next_page_token_present": bool(page_token),
        "duplicate_nct_ids": sorted(set(duplicate_ids)),
        "local_post_filters_applied": [],
        "provenance": {
            "retrieved_at_runtime": True,
            "service": "ClinicalTrials.gov API v2",
            "contract": CLINICAL_TRIALS_CONTRACT_VERSION,
            "requests": provenance,
        },
        "limitations": [
            "Registry records are sponsor-submitted and require status, dates, protocol, amendments, results, and linked publications to be interpreted together.",
            "A registered or completed study is not evidence of efficacy, and missing results must remain explicit.",
            "When records_truncated is true, the returned cohort is incomplete and cannot support prevalence or exhaustive-review claims.",
        ],
    }


def rcsb_structure_records(pdb_ids: list[str], *, client: PublicJSONClient | None = None) -> dict[str, Any]:
    """Retrieve entry-level RCSB PDB metadata without inferring biological validity."""
    if not 1 <= len(pdb_ids) <= 25:
        raise ValueError("one to 25 PDB identifiers are required")
    normalized = [_require_pdb_id(value) for value in pdb_ids]
    if len(normalized) != len(set(normalized)):
        raise ValueError("PDB identifiers must be unique")
    client = client or PublicJSONClient()
    records = []
    for pdb_id in normalized:
        payload = client.get("https://data.rcsb.org", f"/rest/v1/core/entry/{pdb_id}")
        returned_id = str(payload.get("rcsb_id", "")).upper()
        if returned_id != pdb_id:
            raise PublicDatabaseError("RCSB response did not preserve the requested PDB identifier")
        records.append(
            {
                "pdb_id": pdb_id,
                "title": _clean_text(payload.get("struct", {}).get("title")),
                "experimental_methods": [record.get("method") for record in payload.get("exptl", []) if isinstance(record, dict)],
                "resolution_combined": payload.get("rcsb_entry_info", {}).get("resolution_combined", []),
                "release": payload.get("rcsb_accession_info", {}),
                "primary_citation": payload.get("rcsb_primary_citation", {}),
                "entity_ids": payload.get("rcsb_entry_container_identifiers", {}),
                "deposition": payload.get("pdbx_database_status", {}),
            }
        )
    return {
        "query": {"pdb_ids": normalized},
        "structures": records,
        "returned_count": len(records),
        "provenance": {
            "retrieved_at_runtime": True,
            "service": "RCSB PDB Data API",
            "contract": RCSB_CONTRACT_VERSION,
            "data_model": "PDBx/mmCIF-derived JSON",
        },
        "limitations": [
            "A deposited structure requires review of construct, assembly, model quality, ligands, experimental method, resolution, and biological context.",
            "Entry-level metadata does not establish interaction affinity, conformational relevance, or suitability for molecular design.",
        ],
    }


def _rcsb_text_node(attribute: str, operator: str, value: Any) -> dict[str, Any]:
    return {"type": "terminal", "service": "text", "parameters": {"attribute": attribute, "operator": operator, "value": value}}


def rcsb_structure_search(
    text: str | None = None,
    organism: str | None = None,
    taxonomy_id: int | None = None,
    uniprot_accession: str | None = None,
    experimental_method: str | None = None,
    max_resolution: float | None = None,
    ligand_comp_id: str | None = None,
    include_computed_models: bool = False,
    max_records: int = 100,
    *,
    client: PublicJSONClient | None = None,
) -> dict[str, Any]:
    """Run a bounded, count-verified RCSB attribute search."""
    if not 1 <= max_records <= 1_000:
        raise ValueError("max_records must be 1..1000")
    if taxonomy_id is not None and taxonomy_id <= 0:
        raise ValueError("taxonomy_id must be positive")
    if max_resolution is not None and max_resolution <= 0:
        raise ValueError("max_resolution must be positive")
    nodes = []
    if text:
        nodes.append({"type": "terminal", "service": "full_text", "parameters": {"value": _clean_text(text, limit=1000)}})
    if organism:
        nodes.append(_rcsb_text_node("rcsb_entity_source_organism.taxonomy_lineage.name", "exact_match", _clean_text(organism, limit=300)))
    if taxonomy_id is not None:
        nodes.append(_rcsb_text_node("rcsb_entity_source_organism.ncbi_taxonomy_id", "equals", taxonomy_id))
    if uniprot_accession:
        nodes.extend(
            [
                _rcsb_text_node("rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_accession", "exact_match", _clean_text(uniprot_accession, limit=100)),
                _rcsb_text_node("rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_name", "exact_match", "UniProt"),
            ]
        )
    if experimental_method:
        method = experimental_method.strip().upper()
        if method not in _RCSB_EXPERIMENTAL_METHODS:
            raise ValueError("experimental_method is not in the supported RCSB vocabulary")
        nodes.append(_rcsb_text_node("exptl.method", "exact_match", method))
    if max_resolution is not None:
        nodes.append(_rcsb_text_node("rcsb_entry_info.resolution_combined", "less_or_equal", float(max_resolution)))
    if ligand_comp_id:
        nodes.append(_rcsb_text_node("rcsb_nonpolymer_entity_container_identifiers.nonpolymer_comp_id", "exact_match", ligand_comp_id.strip().upper()))
    if not nodes:
        raise ValueError("at least one RCSB search criterion is required")
    query = nodes[0] if len(nodes) == 1 else {"type": "group", "logical_operator": "and", "nodes": nodes}
    client = client or PublicJSONClient()
    records = []
    requests = []
    total_count: int | None = None
    start = 0
    while len(records) < max_records:
        rows = min(100, max_records - len(records))
        request_payload = {
            "query": query,
            "return_type": "entry",
            "request_options": {
                "paginate": {"start": start, "rows": rows},
                "results_content_type": ["experimental", "computational"] if include_computed_models else ["experimental"],
            },
        }
        response, metadata = client.post_with_metadata("https://search.rcsb.org", "/rcsbsearch/v2/query", request_payload)
        if metadata["status_code"] == 204:
            if start != 0:
                raise PublicDatabaseError("RCSB search returned HTTP 204 after pagination began")
            total_count = 0
            requests.append({"start": start, "rows": rows, "results_in_page": 0, "request": metadata})
            break
        try:
            page_total = int(response["total_count"])
        except (KeyError, TypeError, ValueError):
            raise PublicDatabaseError("RCSB search response lacks a valid total_count") from None
        if total_count is None:
            total_count = page_total
        elif page_total != total_count:
            raise PublicDatabaseError("RCSB search total_count changed during pagination")
        page = response.get("result_set", [])
        if not isinstance(page, list):
            raise PublicDatabaseError("RCSB search result_set schema is not recognized")
        requests.append({"start": start, "rows": rows, "results_in_page": len(page), "request": metadata})
        for item in page:
            if not isinstance(item, Mapping) or not _PDB_RE.fullmatch(str(item.get("identifier", ""))):
                raise PublicDatabaseError("RCSB search returned an invalid entry identifier")
            records.append({"pdb_id": str(item["identifier"]).upper(), "score": item.get("score")})
        start += len(page)
        if len(records) >= min(total_count, max_records):
            break
        if not page:
            raise PublicDatabaseError("RCSB search returned an empty page before total_count was reached")
    assert total_count is not None
    duplicate_ids = sorted({item["pdb_id"] for item in records if sum(row["pdb_id"] == item["pdb_id"] for row in records) > 1})
    if duplicate_ids:
        raise PublicDatabaseError("RCSB search returned duplicate entry identifiers")
    truncated = total_count > len(records)
    if not truncated and len(records) != total_count:
        raise PublicDatabaseError("RCSB search pagination does not reconcile with total_count")
    return {
        "query": {
            "text": text, "organism": organism, "taxonomy_id": taxonomy_id, "uniprot_accession": uniprot_accession,
            "experimental_method": experimental_method, "max_resolution": max_resolution, "ligand_comp_id": ligand_comp_id,
            "include_computed_models": include_computed_models, "max_records": max_records,
        },
        "total_count": total_count,
        "returned_count": len(records),
        "records_truncated": truncated,
        "records": records,
        "provenance": {"service": "RCSB PDB Search API", "contract": RCSB_SEARCH_CONTRACT_VERSION, "requests": requests},
        "limitations": [
            "Search relevance and metadata are discovery signals, not validation of biological assembly or model quality.",
            "A truncated result set cannot support exhaustive structure availability claims.",
        ],
    }


def rcsb_polymer_entity_records(
    pdb_id: str,
    entity_ids: list[str] | None = None,
    include_sequences: bool = False,
    *,
    client: PublicJSONClient | None = None,
) -> dict[str, Any]:
    """Retrieve polymer entity metadata with explicit truncation and not-found state."""
    pdb_id = _require_pdb_id(pdb_id)
    if not isinstance(include_sequences, bool):
        raise ValueError("include_sequences must be boolean")
    client = client or PublicJSONClient()
    if entity_ids is None:
        entry = client.get("https://data.rcsb.org", f"/rest/v1/core/entry/{pdb_id}")
        all_ids = (entry.get("rcsb_entry_container_identifiers") or {}).get("polymer_entity_ids") or []
    else:
        if not 1 <= len(entity_ids) <= 25 or any(not str(value).strip() for value in entity_ids):
            raise ValueError("entity_ids must contain one to 25 nonempty identifiers")
        all_ids = list(dict.fromkeys(str(value).strip() for value in entity_ids))
    selected = all_ids[:25]
    records = []
    not_found = []
    for entity_id in selected:
        try:
            raw = client.get("https://data.rcsb.org", f"/rest/v1/core/polymer_entity/{pdb_id}/{quote(str(entity_id), safe='')}")
        except PublicDatabaseError as exc:
            if "HTTP 404" not in str(exc):
                raise
            not_found.append(str(entity_id))
            continue
        entity = raw.get("rcsb_polymer_entity", {}) or {}
        identifiers = raw.get("rcsb_polymer_entity_container_identifiers", {}) or {}
        polymer = raw.get("entity_poly", {}) or {}
        record = {
            "rcsb_id": raw.get("rcsb_id"), "entry_id": identifiers.get("entry_id"), "entity_id": identifiers.get("entity_id"),
            "description": entity.get("pdbx_description"), "polymer_type": polymer.get("rcsb_entity_polymer_type"),
            "sequence_length": polymer.get("rcsb_sample_sequence_length"), "mutation_count": polymer.get("rcsb_mutation_count"),
            "uniprot_ids": identifiers.get("uniprot_ids") or [], "source_organisms": raw.get("rcsb_entity_source_organism", []) or [],
        }
        if include_sequences:
            record["sequence"] = polymer.get("pdbx_seq_one_letter_code_can")
        records.append(record)
    return {
        "pdb_id": pdb_id, "requested_entity_ids": selected, "entry_polymer_entity_count": len(all_ids) if entity_ids is None else None,
        "returned_count": len(records), "records_truncated": len(all_ids) > len(selected), "not_found": not_found, "entities": records,
        "provenance": {"service": "RCSB PDB Data API", "contract": RCSB_CONTRACT_VERSION},
        "limitations": ["Entity metadata and canonical sequence do not establish construct completeness, assembly state, or experimental relevance."],
    }


def rcsb_ligand_records(
    pdb_id: str,
    max_ligands: int = 25,
    *,
    client: PublicJSONClient | None = None,
) -> dict[str, Any]:
    """Walk entry, nonpolymer entities, and chemical components for bound ligands."""
    pdb_id = _require_pdb_id(pdb_id)
    if not 1 <= max_ligands <= 25:
        raise ValueError("max_ligands must be 1..25")
    client = client or PublicJSONClient()
    entry = client.get("https://data.rcsb.org", f"/rest/v1/core/entry/{pdb_id}")
    all_entity_ids = (entry.get("rcsb_entry_container_identifiers") or {}).get("non_polymer_entity_ids") or []
    selected = all_entity_ids[:max_ligands]
    entities = []
    not_found_entities = []
    for entity_id in selected:
        try:
            raw = client.get("https://data.rcsb.org", f"/rest/v1/core/nonpolymer_entity/{pdb_id}/{quote(str(entity_id), safe='')}")
        except PublicDatabaseError as exc:
            if "HTTP 404" not in str(exc):
                raise
            not_found_entities.append(str(entity_id))
            continue
        identifiers = raw.get("rcsb_nonpolymer_entity_container_identifiers", {}) or {}
        entity = raw.get("rcsb_nonpolymer_entity", {}) or {}
        entities.append(
            {
                "entity_id": identifiers.get("entity_id") or str(entity_id),
                "comp_id": identifiers.get("nonpolymer_comp_id"),
                "description": entity.get("pdbx_description"),
                "copy_count": entity.get("pdbx_number_of_molecules"),
                "auth_asym_ids": identifiers.get("auth_asym_ids") or [],
            }
        )
    component_records = {}
    missing_components = []
    for comp_id in sorted({str(item["comp_id"]).upper() for item in entities if item.get("comp_id")}):
        try:
            raw = client.get("https://data.rcsb.org", f"/rest/v1/core/chemcomp/{quote(comp_id, safe='')}")
        except PublicDatabaseError as exc:
            if "HTTP 404" not in str(exc):
                raise
            missing_components.append(comp_id)
            continue
        component = raw.get("chem_comp", {}) or {}
        descriptors = raw.get("rcsb_chem_comp_descriptor", {}) or {}
        component_records[comp_id] = {
            "comp_id": component.get("id") or comp_id,
            "name": component.get("name"),
            "formula": component.get("formula"),
            "formula_weight": component.get("formula_weight"),
            "formal_charge": component.get("pdbx_formal_charge"),
            "type": component.get("type"),
            "inchikey": descriptors.get("InChIKey"),
            "smiles": descriptors.get("SMILES_stereo") or descriptors.get("SMILES"),
        }
    ligands = [{**entity, "chemical_component": component_records.get(str(entity.get("comp_id", "")).upper())} for entity in entities]
    return {
        "pdb_id": pdb_id,
        "entry_nonpolymer_entity_count": len(all_entity_ids),
        "returned_count": len(ligands),
        "records_truncated": len(all_entity_ids) > len(selected),
        "not_found_entity_ids": not_found_entities,
        "not_found_component_ids": missing_components,
        "ligands": ligands,
        "provenance": {"service": "RCSB PDB Data API", "contract": RCSB_CONTRACT_VERSION},
        "limitations": [
            "A deposited bound component does not establish physiological binding, affinity, occupancy, or a design-ready pose.",
            "Chemical-component identity must be reconciled with protonation, charge, stereochemistry, covalent state, and experimental density.",
        ],
    }


_ALPHAFOLD_URL_FIELDS = {
    "cif": "cifUrl",
    "bcif": "bcifUrl",
    "pdb": "pdbUrl",
    "pae_image": "paeImageUrl",
    "pae_json": "paeDocUrl",
    "plddt_json": "plddtDocUrl",
    "msa": "msaUrl",
    "alphamissense_csv": "amAnnotationsUrl",
}


def _require_uniprot_accession(value: str) -> str:
    accession = value.strip().upper()
    if not _UNIPROT_ACCESSION_RE.fullmatch(accession):
        raise ValueError("UniProt accession must be a valid 6- or 10-character accession with an optional isoform suffix")
    return accession


def _alphafold_model_record(raw: Mapping[str, Any], *, include_sequence: bool) -> dict[str, Any]:
    accession = _require_uniprot_accession(str(raw.get("uniprotAccession", "")))
    global_plddt = raw.get("globalMetricValue")
    if global_plddt is not None and (not isinstance(global_plddt, (int, float)) or not 0 <= float(global_plddt) <= 100):
        raise PublicDatabaseError("AlphaFold globalMetricValue is outside the declared pLDDT range")
    fractions = {
        "very_low": raw.get("fractionPlddtVeryLow"),
        "low": raw.get("fractionPlddtLow"),
        "confident": raw.get("fractionPlddtConfident"),
        "very_high": raw.get("fractionPlddtVeryHigh"),
    }
    observed_fractions = [float(value) for value in fractions.values() if value is not None]
    if any(value < 0 or value > 1 for value in observed_fractions):
        raise PublicDatabaseError("AlphaFold pLDDT fractions are outside 0..1")
    if len(observed_fractions) == 4 and abs(sum(observed_fractions) - 1.0) > 0.02:
        raise PublicDatabaseError("AlphaFold pLDDT fractions do not reconcile to one")
    urls = {}
    for name, field in _ALPHAFOLD_URL_FIELDS.items():
        value = raw.get(field)
        if value is None:
            continue
        parsed = urlsplit(str(value))
        if parsed.scheme != "https" or parsed.hostname != "alphafold.ebi.ac.uk":
            raise PublicDatabaseError("AlphaFold resource URL is outside the approved HTTPS host")
        urls[name] = str(value)
    sequence = str(raw.get("sequence") or "").replace("\n", "").replace(" ", "")
    if sequence and re.fullmatch(r"[A-Z]+", sequence) is None:
        raise PublicDatabaseError("AlphaFold sequence is not an uppercase protein sequence")
    start = raw.get("uniprotStart")
    end = raw.get("uniprotEnd")
    if start is not None and end is not None and int(end) < int(start):
        raise PublicDatabaseError("AlphaFold UniProt coordinate range is inverted")
    record = {
        "model_entity_id": raw.get("modelEntityId"),
        "entry_id": raw.get("entryId"),
        "provider_id": raw.get("providerId"),
        "tool_used": raw.get("toolUsed"),
        "uniprot_accession": accession,
        "uniprot_id": raw.get("uniprotId"),
        "uniprot_description": _clean_text(raw.get("uniprotDescription")),
        "gene": raw.get("gene"),
        "organism_scientific_name": raw.get("organismScientificName"),
        "tax_id": raw.get("taxId"),
        "is_uniprot_reviewed": raw.get("isUniProtReviewed"),
        "is_reference_proteome": raw.get("isReferenceProteome"),
        "is_complex": raw.get("isComplex"),
        "sequence_length": len(sequence) if sequence else None,
        "uniprot_start": start,
        "uniprot_end": end,
        "global_plddt": float(global_plddt) if global_plddt is not None else None,
        "fraction_plddt": fractions,
        "fraction_plddt_sum": sum(observed_fractions) if len(observed_fractions) == 4 else None,
        "latest_version": raw.get("latestVersion"),
        "all_versions": raw.get("allVersions") or [],
        "model_created_date": raw.get("modelCreatedDate"),
        "urls": urls,
    }
    if include_sequence:
        record["sequence"] = sequence or None
    return record


def alphafold_structure_records(
    uniprot_accessions: list[str],
    include_sequence: bool = False,
    *,
    client: PublicJSONClient | None = None,
) -> dict[str, Any]:
    """Retrieve AlphaFold DB model metadata with explicit coverage accounting."""
    if not 1 <= len(uniprot_accessions) <= 40:
        raise ValueError("one to 40 UniProt accessions are required")
    if not isinstance(include_sequence, bool):
        raise ValueError("include_sequence must be boolean")
    normalized = [_require_uniprot_accession(value) for value in uniprot_accessions]
    if len(normalized) != len(set(normalized)):
        raise ValueError("UniProt accessions must be unique")
    client = client or PublicJSONClient()
    records = []
    requests = []
    for requested in normalized:
        payload, metadata = client.get_array_with_metadata(
            "https://alphafold.ebi.ac.uk",
            f"/api/prediction/{quote(requested, safe='')}",
            not_found_as_empty=True,
        )
        requests.append(metadata)
        models = []
        for raw in payload:
            if not isinstance(raw, Mapping):
                raise PublicDatabaseError("AlphaFold prediction array contains a non-object record")
            model = _alphafold_model_record(raw, include_sequence=include_sequence)
            returned = model["uniprot_accession"]
            if returned != requested and not returned.startswith(f"{requested}-"):
                raise PublicDatabaseError("AlphaFold response does not preserve the requested UniProt accession")
            models.append(model)
        records.append(
            {
                "requested_uniprot_accession": requested,
                "has_model": bool(models),
                "model_count": len(models),
                "models": models,
            }
        )
    return {
        "query": {"uniprot_accessions": normalized, "include_sequence": include_sequence},
        "requested_count": len(normalized),
        "covered_count": sum(record["has_model"] for record in records),
        "not_covered_count": sum(not record["has_model"] for record in records),
        "records": records,
        "provenance": {
            "retrieved_at_runtime": True,
            "service": "AlphaFold Protein Structure Database API",
            "contract": ALPHAFOLD_CONTRACT_VERSION,
            "requests": requests,
        },
        "limitations": [
            "Predicted coordinates and confidence are model evidence, not experimental validation of structure, state, assembly, dynamics, or function.",
            "Global and binned pLDDT do not establish domain orientation, interface accuracy, ligand pose, or biological relevance; inspect per-residue confidence and PAE before interpretation.",
            "This operation returns metadata and approved resource URLs only; coordinate, PAE, MSA, and annotation payloads are not silently downloaded.",
        ],
    }


_IUPRED2A_PREDICTION_TYPES = frozenset({"long", "short", "glob"})


def _iupred2a_disordered_spans(scores: list[float], threshold: float, minimum_span: int) -> list[dict[str, Any]]:
    """Call contiguous score-threshold spans without smoothing the server profile."""
    spans: list[dict[str, Any]] = []
    start: int | None = None
    for position, score in enumerate(scores, start=1):
        if score >= threshold and start is None:
            start = position
        elif score < threshold and start is not None:
            end = position - 1
            if end - start + 1 >= minimum_span:
                values = scores[start - 1:end]
                spans.append({"start": start, "end": end, "length": len(values), "mean_score": sum(values) / len(values)})
            start = None
    if start is not None:
        end = len(scores)
        if end - start + 1 >= minimum_span:
            values = scores[start - 1:end]
            spans.append({"start": start, "end": end, "length": len(values), "mean_score": sum(values) / len(values)})
    return spans


def iupred2a_disorder_prediction(
    uniprot_accessions: list[str],
    prediction_type: str = "long",
    score_threshold: float = 0.5,
    minimum_span_length: int = 20,
    *,
    client: PublicJSONClient | None = None,
) -> dict[str, Any]:
    """Retrieve bounded IUPred2A residue-level disorder tendencies by accession.

    The service accepts stable UniProt accessions.  It deliberately does not
    submit arbitrary sequences or infer any structural, mechanistic, or
    functional conclusion from a score profile.
    """
    if not 1 <= len(uniprot_accessions) <= 20:
        raise ValueError("one to 20 UniProt accessions are required")
    normalized = [_require_uniprot_accession(value) for value in uniprot_accessions]
    if len(normalized) != len(set(normalized)):
        raise ValueError("UniProt accessions must be unique")
    normalized_type = prediction_type.strip().lower()
    if normalized_type not in _IUPRED2A_PREDICTION_TYPES:
        raise ValueError("prediction_type must be long, short, or glob")
    if not isinstance(score_threshold, (int, float)) or not math.isfinite(float(score_threshold)) or not 0 <= float(score_threshold) <= 1:
        raise ValueError("score_threshold must be a finite value from 0 through 1")
    if not isinstance(minimum_span_length, int) or not 1 <= minimum_span_length <= 500:
        raise ValueError("minimum_span_length must be an integer from 1 through 500")
    active = client or PublicJSONClient()
    records = []
    requests = []
    for accession in normalized:
        payload, transport = active.get_with_metadata(
            "https://iupred2a.elte.hu",
            f"/iupred2a/{normalized_type}/{quote(accession, safe='')}.json",
            not_found_as_empty_object=True,
        )
        requests.append(transport)
        if transport.get("not_found"):
            records.append({"requested_uniprot_accession": accession, "found": False, "prediction_type": normalized_type})
            continue
        sequence = str(payload.get("sequence") or "").strip().upper()
        returned_type = str(payload.get("type") or "").strip().lower()
        raw_scores = payload.get("iupred2")
        if not sequence or re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWY]+", sequence) is None:
            raise PublicDatabaseError("IUPred2A response lacks a valid protein sequence")
        if returned_type != normalized_type:
            raise PublicDatabaseError("IUPred2A response does not preserve the requested prediction type")
        if not isinstance(raw_scores, list) or len(raw_scores) != len(sequence):
            raise PublicDatabaseError("IUPred2A score profile does not reconcile with the returned sequence")
        try:
            scores = [float(value) for value in raw_scores]
        except (TypeError, ValueError):
            raise PublicDatabaseError("IUPred2A score profile contains a non-numeric value") from None
        if any(not math.isfinite(score) or score < 0 or score > 1 for score in scores):
            raise PublicDatabaseError("IUPred2A score profile contains a value outside 0..1")
        records.append(
            {
                "requested_uniprot_accession": accession,
                "found": True,
                "prediction_type": normalized_type,
                "sequence_length": len(sequence),
                "scores": scores,
                "score_count": len(scores),
                "score_threshold": float(score_threshold),
                "minimum_span_length": minimum_span_length,
                "threshold_spans": _iupred2a_disordered_spans(scores, float(score_threshold), minimum_span_length),
            }
        )
    return {
        "query": {
            "uniprot_accessions": normalized,
            "prediction_type": normalized_type,
            "score_threshold": float(score_threshold),
            "minimum_span_length": minimum_span_length,
        },
        "requested_count": len(normalized),
        "found_count": sum(record["found"] for record in records),
        "not_found_count": sum(not record["found"] for record in records),
        "records": records,
        "provenance": {
            "retrieved_at_runtime": True,
            "service": "IUPred2A REST API",
            "contract": IUPRED2A_CONTRACT_VERSION,
            "requests": requests,
        },
        "limitations": [
            "IUPred2A scores are a sequence-based disorder tendency prediction, not experimental structural evidence.",
            "Threshold spans are a transparent score summary, not validated protein domains, binding sites, functional regions, or mechanisms.",
            "The module accepts accession-based requests only and does not transmit arbitrary protein sequences to a third-party service.",
        ],
    }


def string_protein_interaction_evidence(
    identifiers: list[str],
    species: int,
    network_type: str = "functional",
    required_score: int = 700,
    add_nodes: int = 0,
    *,
    client: PublicJSONClient | None = None,
) -> dict[str, Any]:
    """Resolve identifiers and retrieve a bounded, version-pinned STRING network.

    STRING's functional network represents associations; its physical network is
    restricted to evidence compatible with physical interaction but still does
    not establish an interaction in the user's biological system.
    """
    if not isinstance(identifiers, list) or not 2 <= len(identifiers) <= 100:
        raise ValueError("identifiers must contain 2..100 protein identifiers")
    normalized = [str(value).strip() for value in identifiers]
    if any(not value or len(value) > 100 or re.search(r"[\r\n]", value) for value in normalized):
        raise ValueError("protein identifiers must be nonempty single-line values up to 100 characters")
    if len(set(normalized)) != len(normalized):
        raise ValueError("protein identifiers must be unique")
    if not isinstance(species, int) or not 1 <= species <= 9_999_999:
        raise ValueError("species must be a positive NCBI taxonomy identifier")
    if network_type not in {"functional", "physical"}:
        raise ValueError("network_type must be functional or physical")
    if not isinstance(required_score, int) or not 0 <= required_score <= 1000:
        raise ValueError("required_score must be an integer from 0 to 1000")
    if not isinstance(add_nodes, int) or not 0 <= add_nodes <= 50:
        raise ValueError("add_nodes must be an integer from 0 to 50")

    client = client or PublicJSONClient()
    joined = "\r".join(normalized)
    mapping_raw, mapping_transport = client.post_form_array_with_metadata(
        STRING_BASE_URL,
        "/api/json/get_string_ids",
        {"identifiers": joined, "species": str(species), "limit": "1", "echo_query": "1"},
    )
    mapping_by_index: dict[int, dict[str, Any]] = {}
    for raw in mapping_raw:
        if not isinstance(raw, dict):
            raise PublicDatabaseError("STRING identifier mapping contains a non-object record")
        query_index, string_id = raw.get("queryIndex"), _clean_text(raw.get("stringId"), limit=100)
        if not isinstance(query_index, int) or not 0 <= query_index < len(normalized) or not string_id:
            raise PublicDatabaseError("STRING identifier mapping does not preserve query index and STRING ID")
        if query_index in mapping_by_index:
            raise PublicDatabaseError("STRING returned more than one primary mapping for a query identifier")
        if int(raw.get("ncbiTaxonId", -1)) != species:
            raise PublicDatabaseError("STRING mapped an identifier outside the requested species")
        mapping_by_index[query_index] = {
            "query_index": query_index,
            "query_identifier": normalized[query_index],
            "string_id": string_id,
            "preferred_name": _clean_text(raw.get("preferredName"), limit=500),
            "taxon_id": species,
            "taxon_name": _clean_text(raw.get("taxonName"), limit=500),
            "annotation": _clean_text(raw.get("annotation"), limit=5_000),
        }
    mappings = [mapping_by_index[index] for index in sorted(mapping_by_index)]
    unmapped = [value for index, value in enumerate(normalized) if index not in mapping_by_index]
    if len(mappings) < 2:
        raise PublicDatabaseError("fewer than two requested identifiers mapped uniquely in STRING")

    mapped_ids = "\r".join(record["string_id"] for record in mappings)
    network_raw, network_transport = client.post_form_array_with_metadata(
        STRING_BASE_URL,
        "/api/json/network",
        {
            "identifiers": mapped_ids,
            "species": str(species),
            "required_score": str(required_score),
            "network_type": network_type,
            "add_nodes": str(add_nodes),
        },
    )
    score_fields = ("score", "nscore", "fscore", "pscore", "ascore", "escore", "dscore", "tscore")
    edges = []
    for raw in network_raw:
        if not isinstance(raw, dict):
            raise PublicDatabaseError("STRING network contains a non-object edge")
        string_a, string_b = _clean_text(raw.get("stringId_A"), limit=100), _clean_text(raw.get("stringId_B"), limit=100)
        if not string_a or not string_b or string_a == string_b:
            raise PublicDatabaseError("STRING network contains an invalid edge identity")
        scores: dict[str, float] = {}
        for field in score_fields:
            value = raw.get(field, 0.0)
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not 0 <= float(value) <= 1:
                raise PublicDatabaseError(f"STRING edge {field} is outside 0..1")
            scores[field] = float(value)
        edge = {
            "string_id_a": string_a,
            "string_id_b": string_b,
            "preferred_name_a": _clean_text(raw.get("preferredName_A"), limit=500),
            "preferred_name_b": _clean_text(raw.get("preferredName_B"), limit=500),
            "taxon_id": int(raw.get("ncbiTaxonId", species)),
            **scores,
        }
        edges.append(edge)
    edges.sort(key=lambda row: (-row["score"], row["string_id_a"], row["string_id_b"]))

    enrichment_raw, enrichment_transport = client.post_form_array_with_metadata(
        STRING_BASE_URL,
        "/api/json/ppi_enrichment",
        {"identifiers": mapped_ids, "species": str(species)},
    )
    if len(enrichment_raw) != 1 or not isinstance(enrichment_raw[0], dict):
        raise PublicDatabaseError("STRING PPI enrichment response must contain one summary record")
    enrichment = enrichment_raw[0]
    return {
        "query": {
            "identifiers": normalized,
            "species": species,
            "network_type": network_type,
            "required_score": required_score,
            "add_nodes": add_nodes,
        },
        "mappings": mappings,
        "mapped_count": len(mappings),
        "unmapped_identifiers": unmapped,
        "edges": edges,
        "edge_count": len(edges),
        "ppi_enrichment": {
            "number_of_nodes": int(enrichment.get("number_of_nodes", 0)),
            "number_of_edges": int(enrichment.get("number_of_edges", 0)),
            "expected_number_of_edges": float(enrichment.get("expected_number_of_edges", 0)),
            "p_value": float(enrichment.get("p_value", 1)),
            "average_node_degree": float(enrichment.get("average_node_degree", 0)),
            "local_clustering_coefficient": float(enrichment.get("local_clustering_coefficient", 0)),
        },
        "provenance": {
            "service": "STRING database API",
            "release": "12.0",
            "contract": STRING_CONTRACT_VERSION,
            "requests": [mapping_transport, network_transport, enrichment_transport],
        },
        "limitations": [
            "A STRING functional edge is an association supported by one or more evidence channels, not necessarily a physical interaction.",
            "A STRING physical edge is database evidence compatible with physical interaction, not proof of binding in the user's tissue, cell state, condition, or assay.",
            "PPI enrichment tests whether the submitted proteins have more STRING edges than expected; it does not establish pathway activation, causality, direct binding, affinity, or direction.",
        ],
    }


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
