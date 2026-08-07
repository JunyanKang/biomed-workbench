# Evidence And Literature

Languages: [English](evidence-and-literature.md) · [中文](evidence-and-literature.zh-CN.md)

## Scientific Role

This capability area establishes the evidence landscape before, during, and after analysis. It combines retrieval, identifier checking, source-specific interpretation, contradiction tracking, citation-support checks, and freshness review. Retrieved records remain source evidence; they are not automatically promoted into biological conclusions.

For example, NCBI Gene can provide an ortholog record for named genes and organisms, but a database mapping does not prove functional equivalence. A gene symbol is converted to a stable Gene ID only when the organism and candidate are unambiguous; uncertainty remains visible and prevents an incorrect identifier from entering later analyses.

## Supported Capabilities

### Unified evidence and database program

For broad evidence requests, the workbench stages the plan so that identifier resolution and citation-record resolution happen before source-specific retrieval, derived evidence, freshness checks, and publication-facing citation audit. This prevents downstream modules from silently treating a symbol, title, DOI, rsID, pathway ID, study ID, or protein accession as already resolved.

The plan can combine NCBI Entrez and Gene records, UniProt and Ensembl, dbSNP, gnomAD, HPO, GO, Reactome, cBioPortal, Open Targets, Crossref, Europe PMC, bioRxiv or medRxiv, PubChem, ClinicalTrials.gov, RCSB PDB, AlphaFold, and protein-disorder evidence. Each source states the required input, returned information, conditions of use, optional credentials, and unresolved issues. Identifier misses, ambiguous candidates, service outages, incomplete retrieval, stale records, and cross-source disagreements remain visible.

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

### Public biomedical databases

- Search, summarize, fetch, and link NCBI Entrez records.
- Resolve exact gene symbols to stable NCBI Gene IDs, then build gene, ortholog, and variant evidence without erasing database identity or missing records.
- Retrieve chemical identity and descriptors from PubChem with ambiguity checks.
- Retrieve design-aware ClinicalTrials.gov studies with bounded pagination and explicit truncation.
- Search RCSB PDB and retrieve entry, polymer-entity, and bound-ligand evidence.
- Retrieve AlphaFold DB model coverage and confidence metadata while separating predictions from experiments.
- Retrieve IUPred2A accession-bound disorder tendency profiles while retaining residue alignment, threshold policy, and a strict prediction-versus-validation boundary.

### Evidence governance

- Evaluate whether a source is still inside its declared review window without pretending that age proves currentness.
- Audit temporal relationships, source versions, supersession chains, and causal ordering.
- Adjudicate supporting, refuting, negative, ineligible, and unresolved evidence.
- Evaluate classification gold sets with provenance, per-class metrics, support gates, and baseline regression checks.

## Interpretation Boundaries

The evidence workflow preserves original identifiers, source provenance, query boundaries, pagination state, dates, and unresolved disagreements. It blocks exhaustive claims when retrieval is truncated, currentness claims when upstream drift was not assessed, causal claims from associative evidence, and citation-support claims based only on the presence of a reference marker.

## Typical Deliverables

Evidence maps, source inventories, contradiction tables, target dossiers, trial landscapes, citation audits, claim-evidence matrices, unresolved-evidence queues, and literature sections linked to auditable records.
