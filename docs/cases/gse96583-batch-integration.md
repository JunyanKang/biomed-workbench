# GSE96583 Crossed-Donor Batch Integration

This public-data acceptance case compares Harmony, Scanorama, and BBKNN on
published control and interferon-stimulated PBMCs from GEO GSE96583.

## Frozen design

1. Donor is the batch; donor-condition is the biological sample.
2. Up to 400 cells per donor-condition sample are selected by stable SHA-256
   order without cell-type information.
3. Publisher cell type crossed with condition is reserved for post hoc
   biological-conservation evaluation.
4. All methods share 2,500 batch-aware HVGs, 30 PCs, 20 evaluation neighbors,
   one seed, and the same unintegrated PCA baseline.
5. Eligibility requires at least 0.02 normalized batch-entropy gain, no more
   than 0.10 label-purity loss, and at least 0.70 mean label connectivity.
6. A counterfactual run permutes evaluation labels and requires identical PCA
   and Harmony coordinates under a controlled single-thread runtime.

## Observed result

- 6,400 cells, 35,635 genes, eight donors, two conditions, and 16 biological
  samples.
- BBKNN increases normalized batch-neighbor entropy by 0.1709 while label
  purity decreases by 0.0114.
- Harmony increases batch-neighbor entropy by 0.0498 while label purity
  decreases by 0.0140.
- Scanorama decreases batch-neighbor entropy by 0.0724 and loses 0.2269 label
  purity, so it is blocked.
- BBKNN is selected among eligible methods by maximum batch-entropy gain.
- Source digests, cell and feature identities, metadata, raw counts, and all
  reloaded outputs pass their gates.

The result is a dataset-specific adjudication, not a general ranking of
integration methods.

Machine-readable evidence:
[`reports/public-case-gse96583-batch-integration.json`](../../reports/public-case-gse96583-batch-integration.json).
