# Single-Cell Doublet Detection

The `single-cell-doublet-detection` module provides executable, capture-library-aware
Scrublet and scDblFinder workflows. It is designed to produce reviewable evidence,
not a destructive cell filter.

## What the module executes

- Validates integer-like sparse counts, unique cell and feature identities, capture
  membership, loading rationale, and a predeclared expected doublet rate.
- Runs Scrublet on count-backed H5AD and scDblFinder on 10x Matrix Market inputs.
- Preserves per-cell scores, calls, thresholds, seeds, method status, direct
  dependency versions, and source-file SHA-256 identities.
- Reloads outputs and verifies sparse counts, cells, features, and capture labels.
- Compares method agreement while retaining every discordant cell for review.
- Prohibits automatic cell deletion and requires downstream sensitivity analysis
  for consequential exclusion decisions.

## Independent-label evaluation

Independent labels may be inspected only after scores, calls, and thresholds are
frozen. Ambiguous labels remain in method execution but are excluded from
discrimination metrics. Genetic demultiplexing detects cross-genotype multiplets
but cannot identify same-donor doublets, so it is incomplete evidence rather than
ground truth.

The [GSE96583 acceptance case](../cases/gse96583-doublet-detection.md) exercises
both templates on 29,065 public PBMC profiles and evaluates them against withheld
publisher demultiplexing labels.

## Scientific boundary

Scores and calls are method- and dataset-specific. Neither method establishes a
true label on its own, and agreement is stronger review evidence rather than a
license for automatic removal. Ambient RNA, empty droplets, and cell-state
annotation require their own modules and quality gates.
