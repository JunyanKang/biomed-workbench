# Mouse-Gastrulation Erythroid RNA Velocity

This public-data acceptance case runs the packaged scVelo dynamical workflow on
the erythroid subset of the Pijuan-Sala mouse gastrulation atlas distributed by
scVelo.

## Frozen design

1. Up to 60 cells per published sample are selected by stable SHA-256 order
   without stage or cell-type labels.
2. Integer spliced and unspliced counts are preserved from the official source.
3. Embryonic stage is absent from all backend-visible metadata and used only for
   postfit direction evaluation.
4. Published Blood progenitors 1 and Erythroid3 states define root and terminal
   anchors.
5. The model uses 500 HVGs, 30 PCs, 30 neighbors, 20 dynamical iterations, and a
   fixed seed.
6. Two independent executions must reproduce all trajectory outputs, including
   identical missing-value masks for unmodeled genes.

## Observed result

- 1,234 cells, 53,801 genes, 27 samples, and seven embryonic stages.
- 117 genes have finite dynamical fits and 104 are velocity genes.
- Latent time versus withheld embryonic stage Spearman correlation is 0.851.
- Velocity pseudotime versus stage Spearman correlation is 0.860.
- Root-to-terminal latent-time separation is 0.903.
- Median velocity confidence is 0.873.
- Source identity, count preservation, metadata identity, output reload, and
  exact-repeat gates all pass.

The case validates direction in this erythroid lineage. Cells are not treated as
independent condition-level replicates, and the result does not establish
causality.

Machine-readable evidence:
[`reports/public-case-gastrulation-erythroid-velocity.json`](../../reports/public-case-gastrulation-erythroid-velocity.json).
