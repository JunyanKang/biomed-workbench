# Ensembl Gene Identity

`ensembl-gene-evidence` resolves one explicitly declared human or mouse gene
symbol through Ensembl REST. It is the assembly-aware identity step before
coordinate-dependent analyses, not a substitute for an analysis workflow.

## What it returns

- Current Ensembl stable gene ID and display name.
- Assembly, chromosome or contig, start, end, and strand.
- Biotype, canonical transcript when supplied, annotation version, and
  retrieval provenance.
- An explicit `found: false` outcome for a current endpoint 404.

## Use it for

- Anchoring an unambiguous human or mouse symbol to an Ensembl gene record.
- Capturing the genome assembly and interval that downstream coordinate work
  must respect.
- Reconciling an already-declared gene identity with NCBI Gene or an ortholog
  record while retaining each service's provenance.

## It does not do

- Alias search, release-to-release identifier migration, or transcript/isoform
  selection for an experiment.
- Regulatory-feature retrieval, expression analysis, variant interpretation,
  functional annotation, disease assessment, or causal inference.

The module accepts only `human` or `mouse` and one bounded gene symbol. A
not-found result is a service outcome, not evidence that a gene or biology is
absent. Coordinate-consuming modules must still validate their genome build,
annotation release, and interval conventions against the project inputs.
