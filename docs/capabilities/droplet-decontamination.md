# Droplet Calling And Ambient RNA

The `single-cell-droplet-decontamination` module keeps cell calling, ambient
RNA correction, and method selection as separate decisions over immutable raw
and filtered count matrices.

## Executable workflow

- Reconciles ordered features, filtered barcodes, and every filtered count
  vector against the unfiltered droplet matrix.
- Runs emptyDrops on the full capture and retains totals, tested and untested
  states, Monte Carlo p values, limited flags, FDR, and calls for every barcode.
- Runs SoupX with either an explicit contamination fraction or automatic
  cluster-aware estimation.
- Saves the ambient profile, per-cell contamination fractions, corrected
  integer counts, method parameters, versions, source digests, and output
  digests.
- Rejects corrected matrices with changed identities, negative or non-integer
  values, any gene-cell count exceeding its source value, or failed reload.
- Executes CellBender as a separate alternative with explicit expected cells,
  included droplets, model, FPR, epochs, backend, latent fields, and HDF5
  reload checks.
- Preserves method disagreement and never removes cells or selects a corrected
  representation from desired marker or embedding appearance.

## Public evidence

The [PBMC3k droplet case](../cases/pbmc3k-droplet-decontamination.md) executes
emptyDrops and automatic SoupX on the official unfiltered and Cell Ranger
filtered 10x matrices. It accounts for all 737,280 droplets, preserves the
518-barcode disagreement between Cell Ranger and emptyDrops, estimates 5.7%
ambient contamination, and retains at least 86.7% of each predeclared broad
PBMC marker signal after correction.

CellBender 0.3.2 retains separate executable fixture evidence because one
public healthy-donor capture cannot establish general CellBender biological
accuracy.

## Interpretation boundary

Cell calling and ambient correction are not interchangeable. A barcode rejected
by one caller is not automatically an empty droplet, and lower counts after
correction are not automatically more accurate. Corrected matrices remain
alternatives until cell-type, rare-population, replicate, marker, and downstream
inference sensitivity checks pass.
