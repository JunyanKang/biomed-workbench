#!/usr/bin/env python3
"""Generate the reviewed public-database module manifests deterministically."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.contract import parse_manifest  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402


VERIFIED_AT = "2026-07-13"


def _tool(
    name: str,
    identity: str,
    contract: str,
    probe: str,
    source: str,
    differences: list[dict[str, object]],
    *,
    verified_at: str = VERIFIED_AT,
) -> dict[str, object]:
    return {
        "name": name,
        "ecosystem": "service",
        "identity": identity,
        "required": True,
        "tested_versions": [contract],
        "allowed_versions": [f"=={contract}"],
        "version_source": source,
        "verified_at": verified_at,
        "version_probe": [probe],
        "version_probe_kind": "service_contract",
        "version_probe_timeout_seconds": 10,
        "version_pattern": "([a-z0-9-]+-observed-[0-9]{4}-[0-9]{2}-[0-9]{2})",
        "mismatch_policy": "block",
        "version_differences": differences,
        "platforms": ["any"],
    }


TOOLS = {
    "crossref": _tool(
        "crossref-rest",
        "api.crossref.org/v1",
        "rest-v1-observed-2026-07-13",
        "biomed_workbench.services.public_databases:probe_crossref_contract",
        "https://www.crossref.org/documentation/retrieve-metadata/rest-api/",
        [
            {
                "id": "crossref-depositor-metadata",
                "affected_versions": ["==rest-v1-observed-2026-07-13"],
                "category": "field",
                "description": "Crossref fields are depositor supplied and title, relation, update, abstract, and author completeness vary by record.",
                "compatibility_effect": "requires-parser",
                "required_action": "Retain absent and conflicting metadata and never infer retraction or claim validity from DOI resolution alone.",
                "source": "https://www.crossref.org/documentation/retrieve-metadata/rest-api/",
            }
        ],
    ),
    "europe-pmc": _tool(
        "europe-pmc-rest",
        "www.ebi.ac.uk/europepmc/webservices/rest",
        "rest-observed-2026-07-13",
        "biomed_workbench.services.public_databases:probe_europe_pmc_contract",
        "https://europepmc.org/RestfulWebService",
        [
            {
                "id": "europe-pmc-result-types",
                "affected_versions": ["==rest-observed-2026-07-13"],
                "category": "output-format",
                "description": "Europe PMC search fields differ between lite and core result types and identifiers vary by source database.",
                "compatibility_effect": "requires-parameter",
                "required_action": "Request JSON core results and match the normalized DOI explicitly before cross-source comparison.",
                "source": "https://europepmc.org/RestfulWebService",
            }
        ],
    ),
    "biorxiv": _tool(
        "biorxiv-details",
        "api.biorxiv.org/details",
        "details-v1-observed-2026-07-13",
        "biomed_workbench.services.public_databases:probe_biorxiv_contract",
        "https://api.biorxiv.org/",
        [
            {
                "id": "biorxiv-versioned-records",
                "affected_versions": ["==details-v1-observed-2026-07-13"],
                "category": "field",
                "description": "The details endpoint returns one row per preprint version and a published DOI may be absent or reported as NA.",
                "compatibility_effect": "requires-parser",
                "required_action": "Retain all versions, sort them explicitly, and never treat a preprint as peer reviewed without independent publication evidence.",
                "source": "https://api.biorxiv.org/",
            }
        ],
    ),
    "pubchem": _tool(
        "pubchem-pug-rest",
        "pubchem.ncbi.nlm.nih.gov/rest/pug",
        "pug-rest-observed-2026-07-13",
        "biomed_workbench.services.public_databases:probe_pubchem_contract",
        "https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest",
        [
            {
                "id": "pubchem-namespace-and-structure",
                "affected_versions": ["==pug-rest-observed-2026-07-13"],
                "category": "input-format",
                "description": "PUG REST namespaces can resolve one name to multiple compounds and structure identity depends on charge, isotope, stereochemistry, and salt form.",
                "compatibility_effect": "requires-format",
                "required_action": "Declare the namespace and retain CID, InChIKey, isomeric representation, formula, charge, and all ambiguous hits.",
                "source": "https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest",
            },
            {
                "id": "pubchem-smiles-field-names",
                "affected_versions": ["==pug-rest-observed-2026-07-13"],
                "category": "field",
                "description": "The observed property response uses SMILES and ConnectivitySMILES rather than historical IsomericSMILES and CanonicalSMILES keys.",
                "compatibility_effect": "breaking",
                "required_action": "Request and validate the observed SMILES and ConnectivitySMILES fields while retaining InChI and InChIKey for identity review.",
                "source": "https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest",
            }
        ],
    ),
    "clinical-trials": _tool(
        "clinicaltrials-gov-api",
        "clinicaltrials.gov/api/v2",
        "api-v2-observed-2026-07-13",
        "biomed_workbench.services.public_databases:probe_clinical_trials_contract",
        "https://clinicaltrials.gov/data-api/about-api",
        [
            {
                "id": "clinical-trials-v2-data-model",
                "affected_versions": ["==api-v2-observed-2026-07-13"],
                "category": "api",
                "description": "API v2 uses nested protocol and results modules and differs from the retired classic API field layout.",
                "compatibility_effect": "breaking",
                "required_action": "Parse API v2 protocol and results sections, retain status and amendment context, and reject legacy-field assumptions.",
                "source": "https://clinicaltrials.gov/data-api/about-api/api-migration",
            },
            {
                "id": "clinical-trials-v2-pagination-and-essie",
                "affected_versions": ["==api-v2-observed-2026-07-13"],
                "category": "behavior",
                "description": "API v2 uses opaque page tokens, first-page totalCount, field-specific parameters, and Essie expressions for ranges and same-site location constraints.",
                "compatibility_effect": "requires-parameter",
                "required_action": "Walk page tokens to the declared cap, verify unique NCT IDs against totalCount, preserve every request, and mark capped cohorts as truncated.",
                "source": "https://clinicaltrials.gov/data-api/about-api",
            }
        ],
    ),
    "rcsb": _tool(
        "rcsb-pdb-data-api",
        "data.rcsb.org/rest/v1/core",
        "data-rest-v1-observed-2026-07-13",
        "biomed_workbench.services.public_databases:probe_rcsb_contract",
        "https://data.rcsb.org/",
        [
            {
                "id": "rcsb-pdbx-derived-json",
                "affected_versions": ["==data-rest-v1-observed-2026-07-13"],
                "category": "output-format",
                "description": "RCSB Data API JSON follows PDBx/mmCIF-derived object schemas augmented by RCSB annotations and core object identifiers.",
                "compatibility_effect": "requires-parser",
                "required_action": "Validate the returned entry identifier and retain experimental method, resolution, release, citation, entity, and status context.",
                "source": "https://data.rcsb.org/",
            }
        ],
    ),
    "rcsb-search": _tool(
        "rcsb-pdb-search-api",
        "search.rcsb.org/rcsbsearch/v2/query",
        "search-v2-observed-2026-07-13",
        "biomed_workbench.services.public_databases:probe_rcsb_search_contract",
        "https://search.rcsb.org/",
        [
            {
                "id": "rcsb-search-post-and-zero-result",
                "affected_versions": ["==search-v2-observed-2026-07-13"],
                "category": "api",
                "description": "RCSB Search API v2 uses JSON POST queries, count-bearing result pages, and may return HTTP 204 for a valid query with no matches.",
                "compatibility_effect": "requires-parser",
                "required_action": "Submit a bounded JSON query, reconcile total_count and unique entry identifiers across pages, and interpret first-page HTTP 204 only as an explicit zero-result set.",
                "source": "https://search.rcsb.org/",
            }
        ],
    ),
    "alphafold": _tool(
        "alphafold-db-api",
        "alphafold.ebi.ac.uk/api/prediction",
        "prediction-api-observed-2026-07-14",
        "biomed_workbench.services.public_databases:probe_alphafold_contract",
        "https://alphafold.ebi.ac.uk/api-docs",
        [
            {
                "id": "alphafold-prediction-metadata-and-confidence",
                "affected_versions": ["==prediction-api-observed-2026-07-14"],
                "category": "output-format",
                "description": "Prediction records expose provider, tool, model version, sequence coverage, global and binned pLDDT, and versioned resource URLs; coverage and resource availability vary by accession and model provider.",
                "compatibility_effect": "requires-parser",
                "required_action": "Preserve no-model state, validate accession and confidence ranges, record provider/tool/version, and treat coordinate and PAE URLs as unexecuted resources until separately retrieved and checked.",
                "source": "https://alphafold.ebi.ac.uk/api-docs",
            }
        ],
        verified_at="2026-07-14",
    ),
    "ensembl": _tool(
        "ensembl-rest-lookup-symbol",
        "rest.ensembl.org/lookup/symbol",
        "lookup-symbol-v1-observed-2026-07-23",
        "biomed_workbench.services.public_databases:probe_ensembl_gene_lookup_contract",
        "https://rest.ensembl.org/documentation/info/symbol_lookup",
        [
            {
                "id": "ensembl-symbol-lookup-identity-and-coordinate-fields",
                "affected_versions": ["==lookup-symbol-v1-observed-2026-07-23"],
                "category": "field",
                "description": "A symbol lookup returns one current Ensembl gene record with stable ID, display name, assembly, region, coordinates, strand, biotype, and optional canonical transcript fields.",
                "compatibility_effect": "requires-parser",
                "required_action": "Accept only an exact requested symbol lookup with a stable gene ID and internally ordered coordinate interval; preserve explicit not-found state and retrieval provenance.",
                "source": "https://rest.ensembl.org/documentation/info/symbol_lookup",
            }
        ],
        verified_at="2026-07-23",
    ),
    "reactome": _tool(
        "reactome-content-service",
        "reactome.org/ContentService/data/query",
        "content-query-pathway-v1-observed-2026-07-23",
        "biomed_workbench.services.public_databases:probe_reactome_pathway_contract",
        "https://reactome.org/dev/content-service",
        [
            {
                "id": "reactome-stable-pathway-identity-fields",
                "affected_versions": ["==content-query-pathway-v1-observed-2026-07-23"],
                "category": "field",
                "description": "A stable pathway query returns an exact pathway object with stable ID, display name, species, and optional release, disease, inference, and GO-process context.",
                "compatibility_effect": "requires-parser",
                "required_action": "Accept only an exact stable-ID Pathway object with a nonempty display name and species; preserve explicit not-found state and retrieval provenance.",
                "source": "https://reactome.org/dev/content-service",
            }
        ],
        verified_at="2026-07-23",
    ),
    "uniprot-idmapping": _tool(
        "uniprot-id-mapping",
        "rest.uniprot.org/idmapping/run",
        "idmapping-uniprot-to-ensembl-v1-observed-2026-07-23",
        "biomed_workbench.services.public_databases:probe_uniprot_to_ensembl_mapping_contract",
        "https://www.uniprot.org/help/id_mapping",
        [{"id": "uniprot-idmapping-async-job-and-results", "affected_versions": ["==idmapping-uniprot-to-ensembl-v1-observed-2026-07-23"], "category": "api", "description": "The service accepts a form submission, returns a job ID, reports a pending job state, then redirects or returns JSON mapping results.", "compatibility_effect": "requires-parser", "required_action": "Restrict the supported mapping pair, retain job and polling provenance, validate every source accession and Ensembl target, and explicitly retain every unmapped accession.", "source": "https://www.uniprot.org/help/id_mapping"}],
        verified_at="2026-07-23",
    ),
    "opentargets": _tool(
        "open-targets-platform-graphql",
        "api.platform.opentargets.org/api/v4/graphql",
        "disease-evidences-v4-observed-2026-07-23",
        "biomed_workbench.services.public_databases:probe_opentargets_evidence_contract",
        "https://platform-docs.opentargets.org/data-access/graphql-api",
        [{"id": "opentargets-disease-evidences-fixed-fields", "affected_versions": ["==disease-evidences-v4-observed-2026-07-23"], "category": "api", "description": "Disease evidence accepts an Ensembl target list and bounded size, exposes aggregate count and source rows, and no longer accepts the historical datatypes argument.", "compatibility_effect": "breaking", "required_action": "Use only the fixed query, retain total count and source fields, and label any declared datatype selection as local filtering of the bounded returned page rather than an exhaustive server-side result.", "source": "https://platform-docs.opentargets.org/data-access/graphql-api"}],
        verified_at="2026-07-23",
    ),
}


SPECS = {
    "citation-record-resolution": {
        "title": "Resolve and cross-check a scholarly citation record",
        "description": "Resolve one DOI against Crossref and Europe PMC while retaining missing fields, source disagreement, updates, and repository identifiers.",
        "entrypoint": "biomed_workbench.capabilities.evidence:citation_record_resolution",
        "intents": ["resolve DOI metadata", "verify citation record across Crossref and Europe PMC", "核验DOI与文献元数据"],
        "questions": ["Do independent bibliographic services resolve the same DOI, and which metadata conflicts remain?"],
        "input_properties": {"doi": {"type": "string", "minLength": 7, "maxLength": 500}},
        "input_required": ["doi"],
        "output_properties": {
            "query": {"type": "object"}, "crossref": {"type": "object"}, "europe_pmc_records": {"type": "array"},
            "agreement": {"type": "object"}, "provenance": {"type": "object"}, "limitations": {"type": "array"},
        },
        "output_required": ["query", "crossref", "europe_pmc_records", "agreement", "provenance", "limitations"],
        "tools": ["crossref", "europe-pmc"],
        "quality": "The requested DOI must be preserved by Crossref; exact DOI matches from Europe PMC and all cross-source disagreements remain explicit before citation use.",
        "assumption": "The DOI identifies the intended work, while bibliographic deposits may be incomplete or inconsistent.",
        "limitations": ["Identifier resolution does not establish retraction status, methodological validity, or support for a claim."],
        "complements": ["citation-resolution-adjudication", "assertion-citation-coverage-audit", "source-freshness-audit"],
        "effect": "grounds-cross-source-citation-identity",
    },
    "preprint-evidence": {
        "title": "Retrieve version-aware bioRxiv or medRxiv evidence",
        "description": "Retrieve every API-visible version of one preprint DOI and preserve any separately reported publication DOI.",
        "entrypoint": "biomed_workbench.capabilities.evidence:preprint_evidence",
        "intents": ["retrieve bioRxiv preprint versions", "find medRxiv publication link", "检索预印本版本与正式发表记录"],
        "questions": ["Which preprint versions exist, and is a later peer-reviewed publication identifier independently reported?"],
        "input_properties": {"doi": {"type": "string", "minLength": 7, "maxLength": 500}, "server": {"type": "string", "enum": ["biorxiv", "medrxiv"]}},
        "input_required": ["doi"],
        "output_properties": {
            "query": {"type": "object"}, "versions": {"type": "array"}, "latest_version": {"type": "object"},
            "published_dois": {"type": "array"}, "version_count": {"type": "integer"}, "provenance": {"type": "object"}, "limitations": {"type": "array"},
        },
        "output_required": ["query", "versions", "latest_version", "published_dois", "version_count", "provenance", "limitations"],
        "tools": ["biorxiv"],
        "quality": "All returned versions must preserve the requested DOI, remain distinct, and be ordered without upgrading a preprint to peer-reviewed evidence.",
        "assumption": "The DOI and selected server identify the intended preprint record.",
        "limitations": ["Preprint metadata and reported publication links require independent citation resolution before synthesis."],
        "complements": ["citation-record-resolution", "literature-evidence", "source-freshness-audit"],
        "effect": "grounds-versioned-preprint-evidence",
    },
    "chemical-evidence": {
        "title": "Resolve PubChem compound identity and descriptors",
        "description": "Resolve a compound by declared namespace and retain all matched CIDs, structure identifiers, stereochemistry-sensitive fields, synonyms, and ambiguity.",
        "entrypoint": "biomed_workbench.capabilities.evidence:chemical_evidence",
        "intents": ["resolve PubChem compound", "retrieve CID InChIKey SMILES and formula", "核验化合物身份和立体化学"],
        "questions": ["Which PubChem compound identities match the declared identifier, and is chemical form ambiguity resolved?"],
        "input_properties": {"identifier": {"type": "string", "minLength": 1, "maxLength": 500}, "namespace": {"type": "string", "enum": ["name", "cid", "inchikey"]}},
        "input_required": ["identifier"],
        "output_properties": {
            "query": {"type": "object"}, "compounds": {"type": "array"}, "synonyms": {"type": "array"},
            "identity_checks": {"type": "object"}, "provenance": {"type": "object"}, "limitations": {"type": "array"},
        },
        "output_required": ["query", "compounds", "synonyms", "identity_checks", "provenance", "limitations"],
        "tools": ["pubchem"],
        "quality": "CID, structure identifiers, formula, charge, stereochemistry fields, query namespace, and ambiguity must be reviewed before chemical evidence is admitted.",
        "assumption": "The supplied identifier and namespace describe the intended compound search rather than a mixture, formulation, or class.",
        "limitations": ["Compound identity and computed descriptors do not establish target binding, activity, safety, or efficacy."],
        "complements": ["gene-evidence", "literature-evidence", "structure-evidence"],
        "effect": "grounds-chemical-identity-evidence",
    },
    "clinical-trial-evidence": {
        "version": "1.1.0",
        "title": "Retrieve design-aware ClinicalTrials.gov evidence",
        "description": "Retrieve count-verified ClinicalTrials.gov API v2 cohorts with declarative server-side filters, complete bounded pagination, deterministic NCT ordering, request provenance, protocol design, enrollment, outcomes, locations, and results state.",
        "entrypoint": "biomed_workbench.capabilities.evidence:clinical_trial_evidence",
        "intents": ["search ClinicalTrials.gov", "retrieve trial design and results status", "检索临床试验注册设计和结果状态"],
        "questions": ["Which registered studies match the question, and what do their protocol, status, enrollment, results, and amendment context permit us to conclude?"],
        "input_properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 2000},
            "page_size": {"type": "integer", "minimum": 1, "maximum": 1000},
            "max_records": {"type": "integer", "minimum": 1, "maximum": 10000},
            "advanced_query": {"type": "string", "minLength": 1, "maxLength": 4000},
            "include_full_record": {"type": "boolean"},
            "filters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "condition": {"type": "string", "minLength": 1, "maxLength": 500},
                    "intervention": {"type": "string", "minLength": 1, "maxLength": 500},
                    "overall_status": {"type": "array", "items": {"type": "string"}, "maxItems": 16, "uniqueItems": True},
                    "phase": {"type": "array", "items": {"type": "string"}, "maxItems": 6, "uniqueItems": True},
                    "study_type": {"type": "string"},
                    "enrollment_min": {"type": "integer", "minimum": 0},
                    "enrollment_max": {"type": "integer", "minimum": 0},
                    "primary_completion_start": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
                    "primary_completion_end": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
                    "first_posted_start": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
                    "first_posted_end": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
                    "location_country": {"type": "string", "minLength": 1, "maxLength": 200},
                    "lead_sponsor_class": {"type": "string"},
                    "investigator": {"type": "string", "minLength": 1, "maxLength": 300},
                    "investigator_role": {"type": "string", "enum": ["any", "official", "responsible_party"]},
                    "sponsor_name": {"type": "string", "minLength": 1, "maxLength": 300},
                    "sponsor_scope": {"type": "string", "enum": ["lead", "any"]},
                    "eligibility_keywords": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 300}, "maxItems": 20},
                    "sex": {"type": "string"},
                    "healthy_volunteers": {"type": "boolean"},
                    "minimum_age": {"type": "string", "minLength": 1, "maxLength": 40},
                    "maximum_age": {"type": "string", "minLength": 1, "maxLength": 40},
                    "location_city": {"type": "string", "minLength": 1, "maxLength": 200},
                    "location_state": {"type": "string", "minLength": 1, "maxLength": 200},
                    "location_recruiting_only": {"type": "boolean"}
                }
            }
        },
        "input_required": [],
        "output_properties": {
            "query": {"type": "object"}, "api_total_count": {"type": "integer"}, "returned_count": {"type": "integer"},
            "nct_ids": {"type": "array"}, "studies": {"type": "array"}, "records_truncated": {"type": "boolean"},
            "next_page_token_present": {"type": "boolean"}, "duplicate_nct_ids": {"type": "array"},
            "local_post_filters_applied": {"type": "array"}, "provenance": {"type": "object"}, "limitations": {"type": "array"},
        },
        "output_required": ["query", "api_total_count", "returned_count", "nct_ids", "studies", "records_truncated", "next_page_token_present", "duplicate_nct_ids", "local_post_filters_applied", "provenance", "limitations"],
        "tools": ["clinical-trials"],
        "quality": "Every study must preserve a valid unique NCT identifier and protocol context; declared dimensions execute server-side; page tokens are walked to the cap; totalCount, returned IDs, duplicates, truncation, and every request reconcile before cohort interpretation.",
        "assumption": "The search expression identifies a scientifically meaningful cohort, intervention, condition, or study identifier.",
        "limitations": ["Registry records are sponsor-submitted; registration or completion is not evidence of efficacy, missing results remain explicit, and truncated cohorts cannot support exhaustive-review claims."],
        "complements": ["cohort-summary", "survival-analysis", "clinical-report-audit", "literature-evidence"],
        "effect": "grounds-clinical-trial-registry-evidence",
    },
    "structure-evidence": {
        "title": "Retrieve RCSB PDB structure evidence",
        "description": "Retrieve entry-level RCSB PDB metadata for explicit identifiers and retain experimental method, resolution, release, citation, entity, and deposition context.",
        "entrypoint": "biomed_workbench.capabilities.evidence:structure_evidence",
        "intents": ["retrieve RCSB PDB metadata", "inspect structure method resolution and release", "核验PDB结构方法分辨率和实体信息"],
        "questions": ["Which deposited structures correspond to the requested identifiers, and are their method and quality context suitable for the scientific use?"],
        "input_properties": {"pdb_ids": {"type": "array", "items": {"type": "string", "pattern": "^[0-9][A-Za-z0-9]{3}$"}, "minItems": 1, "maxItems": 25, "uniqueItems": True}},
        "input_required": ["pdb_ids"],
        "output_properties": {
            "query": {"type": "object"}, "structures": {"type": "array"}, "returned_count": {"type": "integer"},
            "provenance": {"type": "object"}, "limitations": {"type": "array"},
        },
        "output_required": ["query", "structures", "returned_count", "provenance", "limitations"],
        "tools": ["rcsb"],
        "quality": "Every response must preserve its requested PDB identifier and expose method, resolution, release, citation, entity, and deposition state before structural interpretation.",
        "assumption": "The supplied PDB identifiers refer to structures relevant to the intended construct, assembly, state, and biological question.",
        "limitations": ["Entry metadata alone does not validate assembly, construct relevance, model quality, ligand pose, affinity, or design suitability."],
        "complements": ["chemical-evidence", "gene-evidence", "literature-evidence"],
        "effect": "grounds-macromolecular-structure-evidence",
    },
    "ensembl-gene-evidence": {
        "title": "Resolve a bounded Ensembl gene record",
        "description": "Resolve one explicit human or mouse gene symbol through Ensembl REST while preserving the current stable ID, assembly-aware interval, strand, biotype, canonical transcript, annotation version, source provenance, and an explicit not-found state.",
        "entrypoint": "biomed_workbench.capabilities.evidence:ensembl_gene_evidence",
        "intents": ["Ensembl gene lookup", "retrieve Ensembl gene coordinates", "resolve Ensembl gene symbol", "Ensembl基因坐标查询"],
        "questions": ["Which current Ensembl gene record exactly matches this declared human or mouse symbol, and which assembly-aware coordinates does it report?"],
        "input_properties": {"gene_symbol": {"type": "string", "minLength": 1, "maxLength": 64}, "species": {"type": "string", "enum": ["human", "mouse"]}},
        "input_required": ["gene_symbol"],
        "output_properties": {"requested_symbol": {"type": "string"}, "species": {"type": "string"}, "found": {"type": "boolean"}, "record": {"type": "object", "nullable": True}, "provenance": {"type": "object"}, "limitations": {"type": "array"}},
        "output_required": ["requested_symbol", "species", "found", "record", "provenance", "limitations"],
        "tools": ["ensembl"],
        "quality": "A found result must preserve a stable Ensembl gene ID, nonempty display name and assembly, a positive internally ordered coordinate interval, strand, and retrieval provenance; a 404 remains explicit rather than becoming a biological absence claim.",
        "assumption": "The declared symbol and species identify the intended current Ensembl gene record.",
        "limitations": ["This fixed lookup does not search aliases, map identifiers across annotation releases, select an analysis transcript or isoform, retrieve regulatory features, establish expression, disease relevance, function, or causality."],
        "complements": ["gene-identifier-resolution", "gene-ortholog-evidence", "variant-evidence", "archs4-expression-evidence"],
        "effect": "grounds-assembly-aware-ensembl-gene-identity",
        "verified_at": "2026-07-23",
    },
    "reactome-pathway-evidence": {
        "title": "Resolve a bounded Reactome pathway record",
        "description": "Retrieve one exact Reactome stable pathway record while preserving its versioned identity, species, release context, disease and inference flags, linked GO biological-process context, provenance, and explicit not-found state.",
        "entrypoint": "biomed_workbench.capabilities.evidence:reactome_pathway_evidence",
        "intents": ["Reactome pathway record", "retrieve Reactome pathway", "resolve Reactome stable ID", "Reactome通路记录查询"],
        "questions": ["What curated Reactome pathway record is currently returned for this explicitly declared stable pathway identifier?"],
        "input_properties": {"pathway_id": {"type": "string", "pattern": "^R-[A-Za-z]{3}-[1-9][0-9]{0,11}$"}},
        "input_required": ["pathway_id"],
        "output_properties": {"requested_pathway_id": {"type": "string"}, "found": {"type": "boolean"}, "record": {"type": "object", "nullable": True}, "provenance": {"type": "object"}, "limitations": {"type": "array"}},
        "output_required": ["requested_pathway_id", "found", "record", "provenance", "limitations"],
        "tools": ["reactome"],
        "quality": "A found response must remain an exact stable-ID Pathway object with nonempty display name and species; it must retain versioned identity and retrieval provenance, while a 404 remains explicit.",
        "assumption": "The declared Reactome stable ID identifies the intended pathway rather than an entity, reaction, or free-text concept.",
        "limitations": ["A curated pathway record is reference context only; it does not calculate pathway activity or enrichment, infer project gene membership, establish a mechanism, or prove causality."],
        "complements": ["quickgo-term-evidence", "gene-set-library-membership", "gene-evidence", "literature-evidence"],
        "effect": "grounds-curated-reactome-pathway-identity",
        "verified_at": "2026-07-23",
    },
    "reactome-overrepresentation-evidence": {
        "title": "Retrieve bounded Reactome gene-set overrepresentation context",
        "description": "Submit one explicit, bounded identifier set to the Reactome Analysis Service and preserve service-side mapping loss, ranked pathway statistics, FDR, truncation, analysis token, and strict limits on scientific interpretation.",
        "entrypoint": "biomed_workbench.capabilities.evidence:reactome_overrepresentation_evidence",
        "intents": ["Reactome pathway enrichment", "Reactome gene set overrepresentation", "analyze genes with Reactome", "Reactome基因集通路富集"],
        "questions": ["Which Reactome pathways does the service return for this declared identifier set, and what mapping, background, and inferential limits constrain the result?"],
        "input_properties": {"identifiers": {"type": "array", "minItems": 1, "maxItems": 5000, "uniqueItems": True, "items": {"type": "string", "minLength": 1, "maxLength": 100}}, "max_pathways": {"type": "integer", "minimum": 1, "maximum": 500}},
        "input_required": ["identifiers"],
        "output_properties": {"requested_identifiers": {"type": "array"}, "input_identifier_count": {"type": "integer"}, "unmapped_identifier_count": {"type": "integer", "nullable": True}, "pathway_count": {"type": "integer"}, "returned_pathway_count": {"type": "integer"}, "truncated": {"type": "boolean"}, "pathways": {"type": "array"}, "provenance": {"type": "object"}, "limitations": {"type": "array"}},
        "output_required": ["requested_identifiers", "input_identifier_count", "unmapped_identifier_count", "pathway_count", "returned_pathway_count", "truncated", "pathways", "provenance", "limitations"],
        "tools": ["reactome"],
        "quality": "Require unique bounded input identifiers, explicit service-side mapping-loss count, nonnegative p-values and FDR values, internally valid found/total counts, deterministic significance ordering, truncation state, and analysis-token provenance before interpreting the result.",
        "assumption": "The declared identifier set is scientifically coherent enough for an exploratory overrepresentation query and its identifier namespace is compatible with Reactome mapping.",
        "limitations": ["Reactome controls identifier mapping and its effective background. This result is exploratory reference context, not a replacement for project-specific gene-universe definition, ranked or donor-aware analysis, multiplicity planning, biological mechanism, or independent validation."],
        "complements": ["enrichment-analysis", "quickgo-term-evidence", "reactome-pathway-evidence", "single-cell-donor-inference"],
        "effect": "adds-bounded-reactome-overrepresentation-context",
        "verified_at": "2026-07-23",
    },
    "uniprot-to-ensembl-evidence": {
        "title": "Map bounded UniProt accessions to Ensembl gene IDs",
        "description": "Map one to 500 exact UniProtKB accessions to Ensembl gene identifiers through a bounded asynchronous UniProt job while retaining per-accession success or loss, job state, poll count, and service provenance.",
        "entrypoint": "biomed_workbench.capabilities.evidence:uniprot_to_ensembl_evidence",
        "intents": ["map UniProt accessions to Ensembl genes", "UniProt to Ensembl mapping", "batch protein identifier mapping", "UniProt映射Ensembl基因"],
        "questions": ["Which Ensembl gene identifiers does UniProt currently return for these exact protein accessions, and which inputs remain unmapped?"],
        "input_properties": {"accessions": {"type": "array", "minItems": 1, "maxItems": 500, "uniqueItems": True, "items": {"type": "string", "minLength": 6, "maxLength": 20}}, "max_polls": {"type": "integer", "minimum": 1, "maximum": 30}},
        "input_required": ["accessions"],
        "output_properties": {"requested_accessions": {"type": "array"}, "job_id": {"type": "string"}, "poll_count": {"type": "integer"}, "mapped_count": {"type": "integer"}, "unmapped_accessions": {"type": "array"}, "records": {"type": "array"}, "provenance": {"type": "object"}, "limitations": {"type": "array"}},
        "output_required": ["requested_accessions", "job_id", "poll_count", "mapped_count", "unmapped_accessions", "records", "provenance", "limitations"],
        "tools": ["uniprot-idmapping"],
        "quality": "Every request accession must be syntactically valid and represented exactly once in the output; Ensembl targets must match their identifier grammar, job and polling state must remain explicit, and every non-mapped input must be retained rather than silently dropped.",
        "assumption": "The declared accession set is UniProtKB accession space and a current UniProt-to-Ensembl mapping is appropriate for identifier reconciliation.",
        "limitations": ["This is a current identifier mapping only. It does not establish orthology, transcript or isoform selection, annotation-release equivalence, protein-to-gene uniqueness, gene function, expression, or biological causality."],
        "complements": ["uniprot-protein-evidence", "ensembl-gene-evidence", "gene-ortholog-evidence", "gene-identifier-resolution"],
        "effect": "adds-bounded-uniprot-to-ensembl-identifier-reconciliation",
        "verified_at": "2026-07-23",
    },
    "opentargets-target-disease-evidence": {
        "title": "Retrieve bounded Open Targets target-disease evidence",
        "description": "Retrieve fixed-field, source-resolved Open Targets evidence for one Ensembl target and one disease ontology identifier while retaining service total, returned-page truncation, datasource, datatype, score, study, literature, and local-filter limitations.",
        "entrypoint": "biomed_workbench.capabilities.evidence:opentargets_target_disease_evidence",
        "intents": ["Open Targets target disease evidence", "target disease association evidence", "Open Targets gene disease evidence", "Open Targets靶点疾病证据"],
        "questions": ["Which source-resolved Open Targets evidence records are currently returned for this exact Ensembl target and disease identifier?"],
        "input_properties": {"ensembl_gene_id": {"type": "string", "pattern": "^ENS[A-Za-z]*G[0-9]{11}$"}, "disease_id": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9]*_[0-9]+$"}, "data_types": {"type": "array", "minItems": 1, "maxItems": 30, "uniqueItems": True, "items": {"type": "string", "minLength": 1, "maxLength": 100}}, "max_records": {"type": "integer", "minimum": 1, "maximum": 500}},
        "input_required": ["ensembl_gene_id", "disease_id"],
        "output_properties": {"ensembl_gene_id": {"type": "string"}, "disease_id": {"type": "string"}, "disease_name": {"type": "string", "nullable": True}, "data_types": {"type": "array", "nullable": True}, "found": {"type": "boolean"}, "total_count": {"type": "integer"}, "returned_count": {"type": "integer"}, "truncated": {"type": "boolean"}, "evidence": {"type": "array"}, "provenance": {"type": "object"}, "limitations": {"type": "array"}},
        "output_required": ["ensembl_gene_id", "disease_id", "data_types", "found", "total_count", "returned_count", "truncated", "evidence", "provenance", "limitations"],
        "tools": ["opentargets"],
        "quality": "Require exact target and disease identifiers, a nonnegative service total, fixed source rows with nonnegative scores, an explicit returned-page truncation state, and a declared local-only filter mode when data types are supplied.",
        "assumption": "The declared Ensembl target and disease ontology identifier are appropriate for a source-integrated association evidence lookup.",
        "limitations": ["Open Targets evidence and scores are source-integrated context, not proof of mechanism, clinical validity, actionability, treatment response, or causality. The current service no longer filters datatypes server-side; any such selection is local to the bounded returned page."],
        "complements": ["ensembl-gene-evidence", "uniprot-to-ensembl-evidence", "variant-evidence", "literature-evidence"],
        "effect": "adds-bounded-source-resolved-target-disease-evidence",
        "verified_at": "2026-07-23",
    },
}


CASES = {
    "citation-record-resolution": {
        "name": "resolve-nature-doi-across-two-services",
        "input": {"doi": "10.1038/s41586-020-2649-2"},
        "expected_subset": {"query": {"doi": "10.1038/s41586-020-2649-2"}, "agreement": {"doi_confirmed_by_crossref": True}},
        "http_fixtures": [
            {
                "url": "https://api.crossref.org/v1/works/10.1038%2Fs41586-020-2649-2",
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "json": {
                    "message": {
                        "DOI": "10.1038/s41586-020-2649-2",
                        "title": ["Array programming with NumPy"],
                        "type": "journal-article",
                        "publisher": "Springer Science and Business Media LLC",
                        "container-title": ["Nature"],
                        "published": {"date-parts": [[2020, 9, 16]]},
                        "author": [],
                        "is-referenced-by-count": 0,
                        "relation": {},
                        "update-to": [],
                    }
                },
            },
            {
                "url": "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI%3A%2210.1038%2Fs41586-020-2649-2%22&format=json&resultType=core&pageSize=25",
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "json": {"resultList": {"result": [{"doi": "10.1038/s41586-020-2649-2", "title": "Array programming with NumPy"}]}},
            },
        ],
    },
    "preprint-evidence": {
        "name": "retain-biorxiv-version-history",
        "input": {"doi": "10.1101/339747", "server": "biorxiv"},
        "expected_subset": {"query": {"doi": "10.1101/339747", "server": "biorxiv"}},
        "http_fixtures": [
            {
                "url": "https://api.biorxiv.org/details/biorxiv/10.1101/339747/na/json",
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "json": {"collection": [{"doi": "10.1101/339747", "version": "1", "date": "2018-06-06", "published": "NA"}]},
            }
        ],
    },
    "chemical-evidence": {
        "name": "resolve-aspirin-with-structure-identity",
        "input": {"identifier": "aspirin", "namespace": "name"},
        "expected_subset": {"query": {"identifier": "aspirin", "namespace": "name"}},
        "http_fixtures": [
            {
                "url": "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/aspirin/property/Title,IUPACName,MolecularFormula,MolecularWeight,SMILES,ConnectivitySMILES,InChI,InChIKey,XLogP,TPSA,Charge/JSON",
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "json": {
                    "PropertyTable": {
                        "Properties": [
                            {
                                "CID": 2244,
                                "Title": "Aspirin",
                                "MolecularFormula": "C9H8O4",
                                "SMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
                                "ConnectivitySMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
                                "InChIKey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
                            }
                        ]
                    }
                },
            },
            {
                "url": "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244/synonyms/JSON",
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "json": {"InformationList": {"Information": [{"CID": 2244, "Synonym": ["Aspirin", "Acetylsalicylic acid"]}]}},
            },
        ],
    },
    "clinical-trial-evidence": {
        "name": "resolve-one-nct-record-with-design-context",
        "input": {"query": "NCT00000102", "page_size": 1},
        "expected_subset": {"query": {"term": "NCT00000102", "page_size": 1}, "nct_ids": ["NCT00000102"], "records_truncated": False},
        "http_fixtures": [
            {
                "url": "https://clinicaltrials.gov/api/v2/studies?query.term=NCT00000102&pageSize=1&format=json&countTotal=true",
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "json": {
                    "totalCount": 1,
                    "studies": [
                        {
                            "protocolSection": {
                                "identificationModule": {"nctId": "NCT00000102", "briefTitle": "Congenital adrenal hyperplasia trial"},
                                "designModule": {"studyType": "INTERVENTIONAL", "phases": ["PHASE1"]},
                                "statusModule": {"overallStatus": "COMPLETED"},
                            },
                            "hasResults": False,
                        }
                    ],
                },
            }
        ],
    },
    "structure-evidence": {
        "name": "resolve-hemoglobin-structure-context",
        "input": {"pdb_ids": ["4HHB"]},
        "expected_subset": {"query": {"pdb_ids": ["4HHB"]}, "returned_count": 1},
        "http_fixtures": [
            {
                "url": "https://data.rcsb.org/rest/v1/core/entry/4HHB",
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "json": {
                    "rcsb_id": "4HHB",
                    "struct": {"title": "The crystal structure of human deoxyhaemoglobin"},
                    "exptl": [{"method": "X-RAY DIFFRACTION"}],
                    "rcsb_entry_info": {"resolution_combined": [1.74]},
                    "rcsb_accession_info": {"initial_release_date": "1984-07-17"},
                    "rcsb_primary_citation": {},
                    "rcsb_entry_container_identifiers": {"polymer_entity_ids": ["1", "2"]},
                    "pdbx_database_status": {"status_code": "REL"},
                },
            }
        ],
    },
    "ensembl-gene-evidence": {
        "name": "resolve-human-tp53-assembly-aware-gene-record",
        "input": {"gene_symbol": "TP53", "species": "human"},
        "expected_subset": {"requested_symbol": "TP53", "species": "human", "found": True},
        "http_fixtures": [
            {
                "url": "https://rest.ensembl.org/lookup/symbol/homo_sapiens/TP53?expand=0",
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "json": {"id": "ENSG00000141510", "display_name": "TP53", "species": "homo_sapiens", "assembly_name": "GRCh38", "seq_region_name": "17", "start": 7661779, "end": 7687546, "strand": -1, "biotype": "protein_coding", "canonical_transcript": "ENST00000269305.9", "version": 21},
            }
        ],
    },
    "reactome-pathway-evidence": {
        "name": "resolve-human-apoptosis-pathway-record",
        "input": {"pathway_id": "R-HSA-109581"},
        "expected_subset": {"requested_pathway_id": "R-HSA-109581", "found": True},
        "http_fixtures": [
            {
                "url": "https://reactome.org/ContentService/data/query/R-HSA-109581",
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "json": {"stId": "R-HSA-109581", "stIdVersion": "R-HSA-109581.6", "displayName": "Apoptosis", "speciesName": "Homo sapiens", "schemaClass": "Pathway", "releaseDate": "2004-09-20", "isInDisease": False, "isInferred": False, "goBiologicalProcess": {"accession": "0006915", "displayName": "apoptotic process"}},
            }
        ],
    },
    "reactome-overrepresentation-evidence": {
        "name": "retain-reactome-mapping-and-ranked-pathway-statistics",
        "input": {"identifiers": ["TP53", "BRCA1"], "max_pathways": 1},
        "expected_subset": {"input_identifier_count": 2, "unmapped_identifier_count": 1, "pathway_count": 2, "returned_pathway_count": 1, "truncated": True},
        "http_fixtures": [
            {
                "url": "https://reactome.org/AnalysisService/identifiers/",
                "method": "POST",
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "request_text": "TP53\nBRCA1\n",
                "json": {"summary": {"type": "OVERREPRESENTATION", "token": "bounded-token"}, "identifiersNotFound": 1, "pathways": [{"stId": "R-HSA-6796648", "name": "TP53 repair", "species": {"name": "Homo sapiens"}, "inDisease": False, "entities": {"total": 86, "found": 4, "pValue": 0.0000022, "fdr": 0.00058}}, {"stId": "R-HSA-000001", "name": "Later", "entities": {"total": 10, "found": 1, "pValue": 0.02, "fdr": 0.03}}]},
            }
        ],
    },
    "uniprot-to-ensembl-evidence": {
        "name": "map-one-uniprot-accession-and-retain-one-unmapped-input",
        "input": {"accessions": ["P04637", "Q99999"], "max_polls": 1},
        "expected_subset": {"mapped_count": 1, "unmapped_accessions": ["Q99999"]},
        "http_fixtures": [
            {"url": "https://rest.uniprot.org/idmapping/run", "method": "POST", "status": 200, "headers": {"Content-Type": "application/json"}, "request_form": {"from": "UniProtKB_AC-ID", "to": "Ensembl", "ids": "P04637,Q99999"}, "json": {"jobId": "job-1"}},
            {"url": "https://rest.uniprot.org/idmapping/status/job-1", "status": 200, "headers": {"Content-Type": "application/json"}, "json": {"results": [{"from": "P04637", "to": "ENSG00000141510.20"}]}},
        ],
    },
    "opentargets-target-disease-evidence": {
        "name": "retain-source-resolved-target-disease-evidence-and-page-limit",
        "input": {"ensembl_gene_id": "ENSG00000141510", "disease_id": "MONDO_0007254", "max_records": 1},
        "expected_subset": {"found": True, "total_count": 2, "returned_count": 1, "truncated": True},
        "http_fixtures": [{"url": "https://api.platform.opentargets.org/api/v4/graphql", "method": "POST", "status": 200, "headers": {"Content-Type": "application/json"}, "request_json": {"query": "query Evidence($diseaseId: String!, $geneId: String!, $size: Int!) { disease(efoId: $diseaseId) { id name evidences(ensemblIds: [$geneId], size: $size) { count rows { datasourceId datatypeId score targetFromSourceId studyId literature } } } }", "variables": {"diseaseId": "MONDO_0007254", "geneId": "ENSG00000141510", "size": 1}}, "json": {"data": {"disease": {"id": "MONDO_0007254", "name": "breast cancer", "evidences": {"count": 2, "rows": [{"datasourceId": "cancer_gene_census", "datatypeId": "somatic_mutation", "score": 1, "targetFromSourceId": "ENSG00000141510", "studyId": None, "literature": ["22722193"]}]}}}}}],
    },
}


def _format(name: str, orientation: str) -> dict[str, object]:
    return {
        "name": name,
        "versions": ["1"],
        "representations": ["structured"],
        "compression": ["none"],
        "required_indexes": [],
        "coordinate_systems": [],
        "genome_build_policy": "not_applicable",
        "genome_builds": [],
        "annotation_releases": [],
        "orientations": [orientation],
    }


def _manifest(module_id: str, spec: dict[str, object], python_dependency: dict[str, object]) -> dict[str, object]:
    tools = [deepcopy(TOOLS[name]) for name in spec["tools"]]
    tool_versions = {tool["name"]: [f"=={tool['tested_versions'][0]}"] for tool in tools}
    module_version = str(spec.get("version", "1.0.0"))
    gate_id = f"{module_id}-validity"
    input_name = f"{module_id}-query"
    output_name = f"{module_id}-result"
    verified_at = str(spec.get("verified_at", VERIFIED_AT))
    return {
        "schema_version": 1,
        "id": module_id,
        "version": module_version,
        "title": spec["title"],
        "description": spec["description"],
        "module_type": "data_source",
        "domains": ["evidence"],
        "intents": spec["intents"],
        "questions": spec["questions"],
        "entrypoint": spec["entrypoint"],
        "execution": {"kind": "service", "timeout_seconds": 90, "max_output_bytes": 20_000_000},
        "maturity": "validated",
        "input_artifacts": [
            {
                "name": input_name,
                "artifact_type": "database_query",
                "formats": [_format("inline-json", "request-object")],
                "processing_levels": ["declared"],
                "required_metadata": [],
            }
        ],
        "output_artifacts": [
            {
                "name": output_name,
                "artifact_type": "evidence_bundle",
                "formats": [_format("normalized-json", "module-output")],
                "processing_levels": ["source-preserved", "derived"],
                "required_metadata": ["module_version", "compatibility_row_id", "service_contract", "retrieval_time"],
            }
        ],
        "preconditions": ["A schema-valid, bounded database query is available and public HTTPS access is permitted."],
        "assumptions": [spec["assumption"]],
        "quality_gates": [{"id": gate_id, "severity": "fatal", "description": spec["quality"], "blocks_interpretation": True}],
        "limitations": spec["limitations"],
        "evidence_effects": [spec["effect"]],
        "alternatives": ["literature-evidence"],
        "complements": spec["complements"],
        "tool_requirements": tools,
        "dependencies": [deepcopy(python_dependency)],
        "compatibility_matrix": [
            {
                "id": f"public-database-contract-{verified_at}-{module_id}",
                "module_version": module_version,
                "tool_versions": tool_versions,
                "dependency_versions": {"python": [">=3.14,<3.15"]},
                "input_formats": {input_name: ["inline-json@1"]},
                "output_formats": {output_name: ["normalized-json@1"]},
                "platforms": ["any"],
                "regression_evidence_ids": [f"{module_id}-regression-v1"],
                "end_to_end_evidence_ids": [f"{module_id}-e2e-v1"],
                "verified_at": verified_at,
            }
        ],
        "access": "public_api",
        "mutability": "read_only",
        "credentials": [],
        "input_schema": {"type": "object", "additionalProperties": False, "properties": spec["input_properties"], "required": spec["input_required"]},
        "output_schema": {"type": "object", "additionalProperties": False, "properties": spec["output_properties"], "required": spec["output_required"]},
        "kernel_compatibility": [">=0.2.0,<0.3.0"],
        "provenance": {
            "license": "Apache-2.0",
            "concept_sources": [tool["version_source"] for tool in tools] + ["Project-owned clean-room implementation and scientific validation contract."],
        },
    }


def generate(*, check: bool = False) -> list[str]:
    base = json.loads((BUILTIN_ROOT / "gene-evidence" / "module.json").read_text(encoding="utf-8"))
    python_dependency = base["dependencies"][0]
    changed = []
    for module_id, spec in SPECS.items():
        payload = _manifest(module_id, spec, python_dependency)
        parse_manifest(payload)
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        path = BUILTIN_ROOT / module_id / "module.json"
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != text:
            changed.append(module_id)
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
        cases_text = json.dumps({"schema_version": 1, "cases": [CASES[module_id]]}, indent=2, sort_keys=True) + "\n"
        cases_path = BUILTIN_ROOT / module_id / "tests" / "cases.json"
        current_cases = cases_path.read_text(encoding="utf-8") if cases_path.exists() else None
        if current_cases != cases_text:
            if module_id not in changed:
                changed.append(module_id)
            if not check:
                cases_path.parent.mkdir(parents=True, exist_ok=True)
                cases_path.write_text(cases_text, encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    changed = generate(check=args.check)
    print(json.dumps({"changed_modules": changed, "count": len(changed)}, sort_keys=True))
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
