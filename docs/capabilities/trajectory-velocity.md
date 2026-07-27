# Direction-Validated RNA Velocity

The `single-cell-trajectory-velocity` module fits scVelo dynamical RNA velocity
from integer spliced and unspliced counts and admits temporal interpretation only
when an external order and independent anchors support the inferred direction.

## Executable workflow

- Validates immutable H5AD input, aligned integer count layers, unique
  identifiers, samples, external time, and non-overlapping root and terminal
  anchors.
- Physically removes experimental time from backend-visible metadata before
  normalization, HVG selection, PCA, moments, kinetic fitting, velocity graph,
  pseudotime, and latent time.
- Fits dynamical parameters, retains failed and unmodeled genes, and records
  finite-fit and velocity-gene coverage.
- Tests latent time and velocity pseudotime against withheld time, root-terminal
  separation against external anchors, and median velocity confidence.
- Preserves source layers and metadata, writes a new H5AD, reloads all required
  trajectory fields, and verifies source SHA-256 identity.

Arrow fields and UMAP appearance are descriptive and cannot replace these
direction and source-preservation gates.

## Public evidence

The [mouse-gastrulation erythroid case](../cases/gastrulation-erythroid-velocity.md)
uses 1,234 label-blind sampled cells from 27 published samples and seven
embryonic stages. Two independent template runs produce identical latent time,
velocity pseudotime, velocity finite values, and missing-value masks.

## Interpretation boundary

The workflow supports a recorded connected lineage and does not prove lineage
causality, condition effects, branch topology, or terminal fate probabilities.
RegVelo regulatory constraints and CellRank fate mapping are separate modules;
Slingshot, Monocle3, and tradeSeq are handled by trajectory topology.
