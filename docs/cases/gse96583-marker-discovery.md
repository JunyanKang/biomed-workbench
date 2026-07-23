# GSE96583 Held-Out-Donor Marker Discovery Acceptance

This case runs the packaged marker-discovery template against the official NCBI
GEO GSE96583 batch-2 PBMC release. It uses publisher-provided control-arm
singlet and cell-type labels from eight donors.

## What is executed

1. SHA-256 validation of the GEO raw archive, gene table, and metadata.
2. Matrix, barcode, donor, cell-type, integer-count, and source-identity checks.
3. Selection of six major PBMC classes in the untreated control arm.
4. Label-independent filtering to genes detected in at least 20 cells with at
   least 20 total counts.
5. A sample split frozen before ranking: six discovery donors and two held-out
   validation donors.
6. Scanpy Wilcoxon cluster-versus-rest ranking in discovery cells only.
7. Per-donor raw-count detection-direction review in both partitions.
8. Exact repeat execution, output reload, source immutability, and posthoc
   recovery of predeclared canonical marker families.

## Observed evidence

- 11,990 control-arm singlets and 10,859 retained genes.
- Six major PBMC classes represented in every donor.
- 900 ranked rows, 612 discovery-admitted candidates, and 606 independently
  validated candidates.
- At least 60 independently validated candidates per cell class.
- Canonical B-cell, CD14-monocyte, CD4-T, CD8-T, FCGR3A-monocyte, and NK-cell
  marker families recovered.
- Two independent executions produced byte-identical marker tables.

The checked machine-readable result is
[`reports/public-case-gse96583-marker-discovery.json`](../../reports/public-case-gse96583-marker-discovery.json).

## Interpretation boundary

Publisher labels define the contrasts, so this case does not independently
prove cell identities. Held-out donors do not enter ranking or threshold
selection. Cell-level p-values are descriptive rather than donor-level
inference. Canonical markers are a bounded posthoc positive control and are not
used to tune the analysis. Project use still requires tissue-specific negative
markers, reference and ontology review, unknown-state retention, and validation
of the actual biological design.
