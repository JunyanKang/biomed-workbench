# Single-Cell Marker Discovery

## Scientific role

The `single-cell-marker-discovery` module generates marker evidence for
reviewed clusters without converting marker ranks directly into cell-type
labels. The unified router can compose it after single-cell quality control and
clustering, then pass admitted evidence to reference annotation, ontology
review, donor-aware inference, and manuscript delivery.

## Discovery and validation design

Biological samples are assigned to discovery or held-out validation roles
before ranking. Only discovery cells enter normalization, log transformation,
and Scanpy cluster-versus-rest ranking. Candidate ranks and thresholds are
frozen before validation samples are inspected.

For every candidate, the module recomputes raw-count detection fractions within
and outside the cluster separately in each evaluable biological sample. It
records positive, discordant, tied, and unevaluable samples in both partitions.
An independently validated marker must pass the predeclared discovery evidence
and show the expected direction without discordance in enough held-out samples.

## Executable evidence

- Rank, score, log fold change, cell-level p-value, and adjusted p-value.
- Discovery and validation detection fractions from integer raw counts.
- Discovery and validation sample support, discordance, and median detection
  difference.
- Separate discovery-admitted and independently validated marker fields.
- Exact sample split, parameters, package versions, source and output digests.
- Reloaded TSV evidence and immutable-source checks.

Cell-level p-values are explicitly labelled as descriptive ranking evidence.
Condition-level inference still requires pseudobulk or an appropriate
sample-level model.

## Quality gates

- Block missing, fractional, negative, or nonfinite raw counts and guessed
  cluster, sample, or feature identities.
- Require every cluster to have adequate discovery and validation cells.
- Freeze sample roles and all thresholds before marker outcomes are observed.
- Exclude validation cells from ranking and threshold selection.
- Preserve discordant and unevaluable candidates rather than hiding them.
- Require reference, ontology, positive-marker, negative-marker, and unknown
  state review before assigning cell identities.
- Reload outputs and verify source digests before admitting evidence.

## Public-data evidence

The [GSE96583 held-out-donor case](../cases/gse96583-marker-discovery.md)
executes the module on 11,990 control PBMC singlets from eight donors. Six
donors are used for discovery and two are held out. Across six major PBMC
classes, 606 of 612 discovery candidates reproduce in both held-out donors,
and all six predeclared canonical marker families are recovered.

This result is specific to the recorded source, labels, donor split, filtering,
runtime, and thresholds. It does not establish specificity in another tissue,
cohort, chemistry, disease, or annotation granularity.

## Failure recovery

When a cluster lacks stable markers, Codex should inspect cluster stability,
sample representation, count semantics, ambient RNA, doublets, batch effects,
and annotation granularity. It should preserve the failed evidence and return
upstream to quality control or clustering. It must not change donor roles,
thresholds, or labels to force a preferred marker set.
