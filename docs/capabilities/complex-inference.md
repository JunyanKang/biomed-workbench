# Donor-Aware Complex Single-Cell Inference

The `single-cell-complex-inference` module converts immutable cell-level counts
into sample-by-cell-type evidence and keeps expression, variance, and
composition questions statistically separate.

## Executable workflow

- Validates raw integer counts, cell identities, sample identities, subjects,
  cell types, conditions, time values, and declared covariates.
- Aggregates counts into sample-by-cell-type pseudobulks while retaining a
  complete sample-by-cell-type composition table.
- Rejects underpowered pseudobulks, incomplete subject pairing, rank-deficient
  fixed designs, missing random-effect levels, and unidentifiable coefficients.
- Fits dream models with declared subject random effects for expression and a
  separately declared model for variance decomposition.
- Fits repeated-measure composition models, retains fixed-effect propeller only
  as sensitivity evidence, and evaluates additive-log-ratio results across
  multiple predeclared reference cell types.
- Reloads every serialized table, reconciles all cells and counts, records
  detected runtime versions, and preserves the source artifact digest.

Linear, nonlinear, spline, and interaction terms are generated from the
project's design and scientific hypothesis. They are not inferred from desired
genes or favorable results.

## Public evidence

The [GSE96583 paired-donor case](../cases/gse96583-complex-inference.md)
tests six PBMC populations from eight donors under matched control and
stimulated conditions. It validates sample-level expression and composition
inference, donor random effects, multi-reference composition sensitivity,
source immutability, and output reload.

The public dataset has two paired conditions rather than a multi-timepoint
trajectory. Longitudinal spline and condition-by-time behavior therefore remain
covered by the executable deterministic fixture, not by this public case.

## Interpretation boundary

Cells are observations within a biological sample, not independent treatment
replicates. A random subject effect accounts for pairing but does not repair
confounding, missing conditions, insufficient donors, or weak cell-type
coverage. Expression, variance, and composition estimates are design-specific
associations and do not establish causal effects.
