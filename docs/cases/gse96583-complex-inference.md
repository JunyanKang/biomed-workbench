# GSE96583 Paired-Donor Complex Inference

This public-data acceptance case tests count-backed sample-level expression and
composition inference in control and interferon-beta-stimulated PBMCs.

## Frozen design

1. Six common PBMC populations are retained across eight donors and sixteen
   paired donor-condition samples.
2. Features are ranked without condition labels by detected-cell count and then
   total count. The first 1,200 genes contain all ten predeclared IFN-response
   controls.
3. Raw counts are aggregated by biological sample and cell type; cells are
   never used as condition-level replicates.
4. Expression uses `condition + (1 | subject)` and a separately declared
   subject-level variance model.
5. Composition uses the same paired design, fixed-effect propeller as a
   sensitivity analysis, and three predeclared additive-log-ratio references.
6. Source files, aggregated counts, model outputs, and serialized tables must
   remain digest-bound and reload successfully.

## Acceptance meaning

The case passes only when the paired eight-subject design is estimable, every
cell and count is reconciled, the predeclared IFN controls recover a positive
stimulated direction in all six populations, composition closure is preserved,
reference sensitivity is reported without forcing concordance, and all outputs
reload.

This is a paired-condition experiment, not a multi-timepoint longitudinal
trajectory. The IFN controls are an external direction sanity check and do not
select features, formulas, coefficients, filters, or significance thresholds.

Machine-readable evidence:
[`reports/public-case-gse96583-complex-inference.json`](../../reports/public-case-gse96583-complex-inference.json).
