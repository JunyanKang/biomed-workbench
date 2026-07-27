# 10x PBMC Multiome Integration

This public-data acceptance case executes paired RNA+ATAC WNN and MOFA+ from
the official 10x Genomics PBMC 10k Multiome filtered feature-barcode matrix.

## Frozen design

1. The source HDF5 identity and SHA-256 digest are checked before parsing.
2. Six hundred barcodes are selected by stable hash without cluster labels.
3. Eight hundred unique RNA genes and 1,000 ATAC peaks are selected by
   detected-cell count and total count without labels.
4. The exact cells and count matrices are preserved in a Seurat RNA plus
   ChromatinAssay object.
5. WNN uses RNA PCA dimensions 1-20 and ATAC LSI dimensions 2-21.
6. MOFA+ uses recorded log-normalized RNA and TF-IDF ATAC views, six factors,
   a fixed seed, and 100 training iterations.
7. Every object, graph, weight, factor, loading, variance table, parameter,
   version, and digest is reloaded and reconciled.

## Observed result

- The source contains 11,909 cells and 144,978 features.
- All 600 selected cells retain paired RNA and ATAC counts.
- WNN produces four exploratory clusters and nonempty weighted KNN and SNN
  graphs.
- Mean RNA and ATAC modality weights are 0.581 and 0.419.
- MOFA+ saves and reloads six factors, two view-level variance rows, and 240
  retained loading rows.
- All predeclared source, alignment, execution, and reload gates pass.

The case validates representation and execution, not cell annotation, causal
cross-modal regulation, or condition inference.

Machine-readable evidence:
[`reports/public-case-pbmc-multiome-integration.json`](../../reports/public-case-pbmc-multiome-integration.json).
