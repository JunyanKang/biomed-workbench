# NCBI TP53 Human-to-Mouse Ortholog Evidence

This acceptance case exercises `gene-ortholog-evidence` against the NCBI
Datasets Gene API for a declared source Gene ID and target taxon. It is a
bounded database-record retrieval, not a claim of conserved biology.

## Declared query

- Source: human `TP53`, NCBI Gene `7157`.
- Target taxon: mouse, NCBI taxonomy `10090`.
- Service: NCBI Datasets Gene API ortholog endpoint.

## Observed acceptance evidence

The checked response retained human `TP53` / `7157` / `ENSG00000141510` as
the source identity and returned one mouse record: `Trp53`, NCBI Gene `22059`,
and `ENSMUSG00000059552`. The response was not truncated and its retrieval
provenance, source identity, target taxon, and returned record were retained.

## Scientific boundary

This validates a current NCBI database mapping only. It does not establish
functional, regulatory, expression, phenotype, cell-state, isoform, or
experimental equivalence between TP53 and Trp53.

The machine-readable acceptance record is
[`reports/public-case-ncbi-gene-ortholog.json`](../../reports/public-case-ncbi-gene-ortholog.json).
