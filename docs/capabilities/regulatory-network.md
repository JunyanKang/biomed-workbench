# Single-Cell Regulatory Networks

The `single-cell-regulatory-network` module separates TF coexpression,
motif-pruned regulons, cell-level activity, and paired RNA-ATAC eRegulon
evidence.

## Executable workflow

- Runs GRNBoost2 and AUCell as a pre-motif stage when only expression and a
  declared TF list are available; these outputs remain coexpression programs.
- Runs full pySCENIC with an exact species-matched ranking universe, motif
  annotations, cisTarget pruning, regulon construction, and AUCell.
- Scores SCENIC+ gene and region signatures only from explicit TF, motif,
  region, region-gene, and TF-gene evidence with exact paired cells.
- Retains adjacency, module, motif-enrichment, target-weight, gene-AUC,
  region-AUC, and gene-region concordance layers separately.
- Reloads all sources and outputs and records the exact dual-runtime
  compatibility profiles.

## Public evidence

The [GSE96583 regulatory-program case](../cases/gse96583-regulatory-program.md)
runs GRNBoost2 and AUCell without treatment or cell-type labels, then evaluates
programs against the paired donor design. The complete executable fixture
separately validates cisTarget motif pruning and SCENIC+ because a production
ranking database and paired accessibility are not part of GSE96583.

## Interpretation boundary

Coexpression programs are not regulons until motif pruning succeeds against a
matched production resource. Motif support, AUCell activity, and eRegulon
concordance remain association evidence. Direct binding, enhancer causality,
and condition-level regulation require independent experiments or replicated
temporal evidence.
