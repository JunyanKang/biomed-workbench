# PBMC3k Atlas Annotation Acceptance

This public-data acceptance case executes the packaged
`single-cell-atlas-annotation` CellTypist template against the official 10x
Genomics PBMC3k count matrix with the official CellTypist
`Immune_All_Low.pkl` v2 model.

## Evidence identity

- Query: 10x Genomics 3k PBMC filtered count matrix, 2,700 cells by 32,738
  features, bound to its published archive SHA-256.
- Reference: CellTypist `Immune_All_Low.pkl` v2, 98 immune classes trained from
  20 tissues and 18 studies, bound to the official model URL and SHA-256.
- Workflow: the project-owned `annotate_celltypist.py` template, bound to its
  module manifest and template SHA-256.
- Runtime: exact CellTypist, Scanpy, AnnData, NumPy, SciPy, and pandas versions
  detected during execution.

## Admission gates

The case requires finite nonnegative integer-like source counts, sufficient
model-feature overlap, thresholds frozen before prediction, complete
cell-by-class probability evidence, exact low-confidence-to-Unknown behavior,
complete cell and raw-count preservation, output reload, and posthoc broad
marker coherence.

The marker review is deliberately downstream of the frozen predictions. It
tests whether each evaluable predicted broad family shows directional
enrichment for an independently declared marker set. Families without enough
cells, comparator cells, or represented marker genes are retained with explicit
not-evaluable reasons. The review neither tunes the model nor converts model
predictions into ground truth.

## Interpretation boundary

This is evidence that the packaged workflow can annotate one independently
published healthy-donor PBMC count matrix with one exact official immune model
while retaining uncertainty and source data. It is not validation of all 98
fine-grained classes, novel-state detection, other tissues or species,
cross-donor generalization, or final expert-reviewed cell identities. Updated
model artifacts require new digest-bound acceptance evidence.

The machine-readable checked result is
`reports/public-case-pbmc3k-atlas-annotation.json`.
