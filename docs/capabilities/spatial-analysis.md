# Single-Cell Spatial Analysis

The `single-cell-spatial-analysis` module analyzes count-backed spatial
observations while keeping geometry, biological samples, reviewed annotations,
and exploratory domains distinct.

## Executable workflow

- Reads H5AD or SpatialData Zarr tables with integer counts, unique
  observations and genes, finite two-dimensional coordinates, declared units,
  sample identity, and spatial-element provenance.
- Builds spatial graphs independently within each biological sample and proves
  that no cross-sample edges exist.
- Runs neighborhood enrichment, per-sample co-occurrence, and global plus
  sample-level Moran permutation tests with multiplicity control.
- Builds exploratory expression-spatial domains from HVGs, PCA, within-sample
  standardized coordinates, and explicit igraph Leiden parameters without
  reviewed-label leakage.
- Reloads counts, coordinates, graphs, domains, tables, parameters, versions,
  and digests.

## Public evidence

The [SeqFISH embryo case](../cases/seqfish-spatial.md) uses integer counts and
coordinates from the public Squidpy dataset. A spatially coherent subset is
selected without cell-type labels and executes the complete statistical and
domain workflow.

## Interpretation boundary

The public source contains one embryo. Its Moran-positive genes are
single-embryo spatial candidates, not replicated spatial genes, and it cannot
support condition inference. Replicated status requires at least two
independent biological samples. Neighborhood, co-occurrence, autocorrelation,
and exploratory domains do not establish interaction, lineage, or causality.
