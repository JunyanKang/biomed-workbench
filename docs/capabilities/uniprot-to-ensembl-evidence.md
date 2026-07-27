# UniProt-to-Ensembl Mapping

`uniprot-to-ensembl-evidence` reconciles a bounded list of exact UniProtKB
accessions with the Ensembl gene identifiers currently returned by UniProt.
It is an identifier bridge with explicit loss states, not an orthology or
functional-analysis operation.

## What it returns

- Every requested accession, exactly once.
- Current Ensembl gene IDs returned for each accession.
- Explicit unmapped accessions rather than silent loss.
- The bounded asynchronous job ID, poll count, and retrieval provenance.

## Use it for

- Joining reviewed protein-accession evidence to Ensembl-coordinate or gene
  annotation workflows.
- Auditing identifier loss before an enrichment, pathway, or multi-database
  evidence workflow.
- Preserving a reproducible cross-database reconciliation event in a research
  record.

## It does not do

- Infer orthology, select transcripts or isoforms, or equate annotation
  releases.
- Prove protein-to-gene uniqueness, expression, function, disease relevance,
  or causality.

The module accepts up to 500 unique exact UniProt accessions and only performs
the declared UniProtKB accession-to-Ensembl gene mapping pair. Unmapped inputs
must remain visible in downstream interpretation.
