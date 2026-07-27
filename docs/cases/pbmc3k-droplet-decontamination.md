# PBMC3k Droplet Calling And Ambient RNA

This public-data acceptance case evaluates emptyDrops and automatic SoupX on
the official unfiltered and Cell Ranger filtered PBMC3k matrices.

## Frozen design

1. Both 10x archives are bound to fixed SHA-256 digests.
2. The 32,738 ordered features and every filtered barcode and count vector must
   reconcile exactly to the unfiltered capture.
3. Filtered cells are clustered by a frozen Scanpy
   PCA-neighbours-Leiden workflow before SoupX.
4. emptyDrops uses lower count 100, 1,000 Monte Carlo iterations, FDR 0.001,
   serial execution, and seed 719.
5. SoupX uses automatic estimation with `tfidfMin=1` and
   `soupQuantile=0.9`.
6. Corrected counts must be integer, nonnegative, identifier-stable,
   element-wise no greater than source counts, and reloadable.
7. Ten predeclared broad PBMC markers provide a subtraction sanity check, not a
   cell-type accuracy claim.

## Observed result

- 737,280 raw droplets, 2,700 Cell Ranger filtered cells, and 32,738 features.
- emptyDrops tested 2,962 barcodes and called 2,182 at FDR 0.001.
- All 2,182 emptyDrops calls are in the Cell Ranger filtered set.
- 518 Cell Ranger filtered barcodes are not supported by emptyDrops at this
  threshold; they remain retained as an explicit method disagreement.
- SoupX estimates 5.7% contamination and removes 364,355 of 6,390,631 filtered
  UMI counts.
- MALAT1, B2M, TMSB4X, ribosomal, mitochondrial, ferritin, and ACTB transcripts
  dominate the estimated ambient profile.
- Minimum retained signal among CD3D, IL7R, LST1, S100A8, MS4A1, CD79A, NKG7,
  GNLY, FCGR3A, and PPBP is 86.7%.
- Source archives, identifiers, corrected counts, ambient profile, per-cell
  contamination table, and serialized outputs pass integrity and reload gates.

The result does not authorize automatic removal of the 518 discordant
barcodes, establish rare-population preservation, or select SoupX over raw
counts or CellBender for another capture.

Machine-readable evidence:
[`reports/public-case-pbmc3k-droplet-decontamination.json`](../../reports/public-case-pbmc3k-droplet-decontamination.json).
