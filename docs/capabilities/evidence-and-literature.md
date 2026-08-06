# Evidence And Literature

Languages: [English](evidence-and-literature.md) · [中文](evidence-and-literature.zh-CN.md)

## Scientific Role

- NCBI Gene ortholog records can provide a bounded source-to-target mapping for declared Gene IDs and taxa; they remain database evidence rather than functional-equivalence evidence.
- Stable Gene IDs are resolved only after exact symbol-and-organism matching; ambiguous candidates remain unresolved and cannot silently feed downstream database calls.

This capability area establishes the evidence landscape before, during, and after analysis. It combines retrieval with identifier reconciliation, source-specific interpretation, contradiction tracking, citation support checks, and freshness review. Retrieved records remain source evidence; they are not automatically promoted into biological conclusions.

## Supported Capabilities

### Unified evidence and database program

For broad evidence requests, the workbench stages the plan so that identifier resolution and citation-record resolution happen before source-specific retrieval, derived evidence, freshness checks, and publication-facing citation audit. This prevents downstream modules from silently treating a symbol, title, DOI, rsID, pathway ID, study ID, or protein accession as already resolved.

The unified plan can combine NCBI Entrez and Gene records, UniProt and Ensembl identity, dbSNP, gnomAD, HPO, GO, Reactome, cBioPortal, Open Targets, Crossref, Europe PMC, bioRxiv or medRxiv, PubChem, ClinicalTrials.gov, RCSB PDB, AlphaFold, and protein-disorder evidence. Each selected module reports its own input contract, output fields, compatibility row, quality gates, optional credentials, and unresolved states. The workbench keeps identifier misses, ambiguous candidates, upstream outages, truncated retrieval, stale records, and cross-source disagreements visible.

### Literature and citation evidence

- Search and retrieve biomedical literature with explicit query and date context.
- Resolve DOI-centred citation records across Crossref and Europe PMC while preserving disagreements.
- Retrieve version-aware bioRxiv and medRxiv histories without collapsing preprint revisions.
- Audit citation metadata, citation resolution, assertion coverage, and claim-evidence fit.
- Retrieve bounded dbSNP reference-variant identity evidence for a canonical rs identifier, while keeping clinical, population, and genome-build interpretation outside the identity record.
- Retrieve fixed-field gnomAD GRCh38 aggregate gene-constraint context, preserving the distinction between population depletion metrics and clinical or causal interpretation.
- Retrieve an exact public cBioPortal cancer-genomics study record, preserving study identity, cancer type, reference genome and assay-specific cohort counts without treating those metadata as patient-level results or clinical evidence.
- Retrieve bounded cBioPortal mutation records for one declared gene and public study, resolving the mutation profile and sample list explicitly, preserving coordinate/build context, and marking capped results as non-exhaustive.
- Retrieve bounded cBioPortal discrete copy-number events through the required POST gene filter, preserving categorical event meaning and marking locally capped records as non-exhaustive.
- Audit discrete copy-number cohort coverage against a declared eligible denominator; only complete, non-truncated source evidence can enter the serial adaptation-to-audit path, and the result remains descriptive rather than purity, ploidy, focality, or clinical inference.
- Separate an identifier-keyed miss, a title-only coverage gap, an upstream outage, and a genuinely unresolved record.

Representative modules include `literature-evidence`, `citation-record-resolution`, `preprint-evidence`, `citation-audit`, `citation-resolution-adjudication`, and `assertion-citation-coverage-audit`.

### Public biomedical databases

- Search, summarize, fetch, and link NCBI Entrez records.
- Resolve exact gene symbols to stable NCBI Gene IDs, then build gene, ortholog, and variant evidence without erasing database identity or missing records.
- Retrieve chemical identity and descriptors from PubChem with ambiguity checks.
- Retrieve design-aware ClinicalTrials.gov studies with bounded pagination and explicit truncation.
- Search RCSB PDB and retrieve entry, polymer-entity, and bound-ligand evidence.
- Retrieve AlphaFold DB model coverage and confidence metadata while separating predictions from experiments.
- Retrieve IUPred2A accession-bound disorder tendency profiles while retaining residue alignment, threshold policy, and a strict prediction-versus-validation boundary.

Representative modules include `ncbi-search`, `ncbi-fetch`, `ncbi-link`, `gene-identifier-resolution`, `gene-evidence`, `gene-ortholog-evidence`, `variant-evidence`, `chemical-evidence`, `clinical-trial-evidence`, `structure-search`, `structure-evidence`, `alphafold-structure-evidence`, and `protein-disorder-evidence`.

### Evidence governance

- Evaluate whether a source is still inside its declared review window without pretending that age proves currentness.
- Audit temporal relationships, source versions, supersession chains, and causal ordering.
- Adjudicate supporting, refuting, negative, ineligible, and unresolved evidence.
- Evaluate classification gold sets with provenance, per-class metrics, support gates, and baseline regression checks.

Representative modules include `source-freshness-audit`, `temporal-integrity-audit`, `claim-evidence-integrity-audit`, and `classification-gold-set-evaluation`.

## Quality Gates

The evidence workflow preserves original identifiers, source provenance, query boundaries, pagination state, dates, and unresolved disagreements. It blocks exhaustive claims when retrieval is truncated, currentness claims when upstream drift was not assessed, causal claims from associative evidence, and citation-support claims based only on the presence of a reference marker.

## Typical Deliverables

Evidence maps, source inventories, contradiction tables, target dossiers, trial landscapes, citation audits, claim-evidence matrices, unresolved-evidence queues, and literature sections linked to auditable records.
