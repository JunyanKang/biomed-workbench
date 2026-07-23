# GSE96583 Paired Donor Pseudobulk Acceptance

This case runs the packaged donor-aware single-cell templates against the
official NCBI GEO GSE96583 batch-2 PBMC release. The published experiment
contains control and IFN-beta-stimulated cells from the same eight donors,
publisher-provided cell-type labels, and publisher-provided singlet, doublet,
and ambiguous assignments.

## What Is Executed

1. Download and SHA-256 validation of the GEO raw archive, gene table, and
   batch-2 metadata.
2. Matrix, barcode, metadata, donor, condition, cell-type, and count validation.
3. Exclusion of published doublet, ambiguous, and untyped records.
4. Raw-count aggregation by donor-condition biological sample and cell type.
5. Paired edgeR inference with donor fixed effects and a stimulation contrast.
6. Design-rank, replicate, count-conservation, output-schema, and reload checks.
7. Independent recovery check for canonical interferon-response genes across
   major PBMC cell types.

The checked machine-readable result is
[`reports/public-case-gse96583-donor-inference.json`](../../reports/public-case-gse96583-donor-inference.json).
It binds the source digests, module and template digests, observed runtime,
parameters, results, gates, and inferential boundaries.

## Interpretation Boundary

This is a real public-data acceptance test, not a universal validation of every
cohort or model. It relies on the publisher's annotations and multiplet calls,
tests one edgeR paired design, and uses the known interferon response as a
positive-control gate. Project use still requires inspection of the actual
design, annotation, covariates, sample quality, alternative models, and claim
scope.
