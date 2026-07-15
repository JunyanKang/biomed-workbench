# Evidence And Literature

## Scientific Role

This capability area establishes the evidence landscape before, during, and after analysis. It combines retrieval with identifier reconciliation, source-specific interpretation, contradiction tracking, citation support checks, and freshness review. Retrieved records remain source evidence; they are not automatically promoted into biological conclusions.

## Supported Capabilities

### Literature and citation evidence

- Search and retrieve biomedical literature with explicit query and date context.
- Resolve DOI-centred citation records across Crossref and Europe PMC while preserving disagreements.
- Retrieve version-aware bioRxiv and medRxiv histories without collapsing preprint revisions.
- Audit citation metadata, citation resolution, assertion coverage, and claim-evidence fit.
- Separate an identifier-keyed miss, a title-only coverage gap, an upstream outage, and a genuinely unresolved record.

Representative modules include `literature-evidence`, `citation-record-resolution`, `preprint-evidence`, `citation-audit`, `citation-resolution-adjudication`, and `assertion-citation-coverage-audit`.

### Public biomedical databases

- Search, summarize, fetch, and link NCBI Entrez records.
- Build gene and variant evidence bundles without erasing database identity or missing records.
- Retrieve chemical identity and descriptors from PubChem with ambiguity checks.
- Retrieve design-aware ClinicalTrials.gov studies with bounded pagination and explicit truncation.
- Search RCSB PDB and retrieve entry, polymer-entity, and bound-ligand evidence.
- Retrieve AlphaFold DB model coverage and confidence metadata while separating predictions from experiments.

Representative modules include `ncbi-search`, `ncbi-fetch`, `ncbi-link`, `gene-evidence`, `variant-evidence`, `chemical-evidence`, `clinical-trial-evidence`, `structure-search`, `structure-evidence`, and `alphafold-structure-evidence`.

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
