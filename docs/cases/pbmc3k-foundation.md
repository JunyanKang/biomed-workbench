# PBMC3k Public-Data Foundation Case

This case executes the packaged `single-cell-foundation-workflow` Scanpy template
against the official 10x Genomics PBMC3k filtered gene-barcode matrix. It is a
release acceptance case for public-source identity, matrix validation, complete
cell accounting, immutable raw counts, normalization, highly variable genes,
PCA, neighbor graph, UMAP, Leiden sensitivity, serialization, and reload checks.

The source archive is bound to the SHA-256 published in the official Scanpy
PBMC3k tutorial. The checked release report records the exact module, template,
source, runtime, parameters, quality gates, cell and feature accounting, cluster
sensitivity, and output reload checks without retaining downloaded data or
machine-local paths.

## Scientific Scope

PBMC3k contains one filtered matrix from one healthy donor. The case therefore
does not claim that empty droplets, ambient RNA, or doublets are absent. It does
not perform donor-aware condition inference, differential abundance, population
generalization, causal interpretation, or final cell-type annotation.

The QC thresholds are a bounded reproducibility baseline for this acceptance
case. Codex must inspect and justify parameters again for every user project.

## Reproduce

Run the verifier in an isolated environment satisfying the module compatibility
row for Scanpy 1.10 or 1.11:

```bash
python tools/verify_public_pbmc3k_case.py
```

The command downloads and verifies the official archive, runs the packaged
template in a temporary directory, deletes temporary data on completion, and
updates `reports/public-case-pbmc3k-foundation.json`.
