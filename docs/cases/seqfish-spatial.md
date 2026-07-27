# SeqFISH Embryo Spatial Analysis

This public-data acceptance case executes count-backed Squidpy spatial
statistics and expression-spatial domain discovery on the public mouse embryo
SeqFISH dataset.

## Frozen design

1. The source H5AD is bound to its expected SHA-256 digest and validated as
   19,416 observations by 351 integer-count genes.
2. Two thousand observations nearest the coordinate median are selected with
   stable-hash tie breaking and no cell-type labels.
3. Rare reviewed labels are grouped only after selection for descriptive
   neighborhood analysis.
4. Six-neighbor spatial graphs, 99 permutations, ten co-occurrence intervals,
   20 label-blind Moran candidates, and a one-sample support boundary are
   fixed before execution.
5. Domains use 250 HVGs, 25 PCs, 15 neighbors, coordinate weight 2.0, Leiden
   resolution 0.5, and a fixed seed.

## Observed result

- The subset retains 2,000 observations, 351 genes, and 12 reviewed label
  groups.
- The spatial graph contains 5,968 undirected edges and zero cross-sample
  edges.
- Neighborhood enrichment, co-occurrence, and 20 global plus sample-level
  Moran tests execute and reload.
- Seventeen genes pass the within-embryo Moran candidate gate.
- The joint expression-spatial model produces nine exploratory domains.
- Source counts, cells, genes, coordinates, outputs, versions, and digests are
  preserved.

Because the source has one embryo, none of the candidates is presented as a
replicated spatial gene or condition-level result.

Machine-readable evidence:
[`reports/public-case-seqfish-spatial.json`](../../reports/public-case-seqfish-spatial.json).
