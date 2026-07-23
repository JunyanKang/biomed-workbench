# GSE96583 Doublet Detection Acceptance

This public-data case runs the packaged Scrublet and scDblFinder templates on both
pooled 10x capture libraries from GEO GSE96583. All 29,065 cells and 35,635 genes
are processed. Publisher genetic-demultiplexing labels are withheld until both
methods have frozen their scores and calls.

## Frozen design

1. Run each method by `ctrl` or `stim` capture library.
2. Use a predeclared expected doublet rate of 10%, without label-based tuning.
3. Retain ambiguous cells during execution and exclude them only from metrics.
4. Require overall AUROC of at least 0.55 and per-library AUROC of at least 0.52.
5. Require average precision above label prevalence and a higher median score in
   publisher doublets than publisher singlets.
6. Preserve method disagreement and perform no automatic cell removal.

## Observed result

| Method | Overall AUROC | Average precision | Precision | Recall |
| --- | ---: | ---: | ---: | ---: |
| Scrublet 0.2.3 | 0.869 | 0.551 | 0.661 | 0.494 |
| scDblFinder 1.16.0 | 0.930 | 0.689 | 0.652 | 0.823 |

Both methods passed in both capture libraries. Among 2,074 cells called by both
methods, 73.1% carried a publisher doublet label, compared with an 11.4% baseline
among non-ambiguous labels. All source, cell, output reload, and no-removal gates
passed.

## Boundary

The publisher labels detect cross-genotype multiplets but miss same-donor
doublets. These results therefore validate discrimination against independent,
incomplete labels for this dataset and runtime; they do not establish universal
performance or complete truth.

Machine-readable evidence:
[`reports/public-case-gse96583-doublet-detection.json`](../../reports/public-case-gse96583-doublet-detection.json).
