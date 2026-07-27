# GSE96583 Held-Out-Donor Generative Modeling

This public-data acceptance case tests whether scVI or scANVI should be admitted
for representation and annotation support on control and stimulated PBMCs.

## Frozen design

1. Up to 100 cells per donor-condition sample are selected by stable SHA-256
   order without labels.
2. The 2,500 most detected genes are selected without labels.
3. Donors 1256 and 1488 are converted entirely to Unknown in the input H5AD.
4. Their publisher labels are retained only in an external evaluation table.
5. The base scVI model cannot see reviewed labels; scANVI uses six-donor labels
   plus a deterministic 20% internal holdout.
6. Model admission requires nonnegative donor-neighborhood entropy gain,
   preserved label structure, successful annotation holdout, source
   preservation, and model and H5AD reload.

## Observed result

- 1,600 cells, 2,500 genes, eight donors, and 16 donor-condition samples.
- scANVI internal holdout macro-F1 is 0.784.
- On 400 cells from two entirely unseen donors, scANVI suggestion accuracy is
  92.75%, balanced accuracy is 0.722, and macro-F1 is 0.737.
- scVI donor-neighborhood entropy changes by -0.0176.
- scANVI donor-neighborhood entropy changes by -0.0258.
- Both models are blocked on the predeclared mixing gate and no model is
  selected.
- Raw counts, source metadata, reviewed and Unknown labels, source digests,
  saved models, and output reloads pass.

The suggestions remain exploratory review material. The public case succeeds
because the workflow detects and preserves a scientifically meaningful
no-selection decision.

Machine-readable evidence:
[`reports/public-case-gse96583-generative-modeling.json`](../../reports/public-case-gse96583-generative-modeling.json).
