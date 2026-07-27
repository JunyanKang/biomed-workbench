# Classical Single-Cell Batch Integration

The `single-cell-batch-integration` module compares Harmony, Scanorama, and
BBKNN from one frozen, batch-aware preprocessing foundation. It treats
integration as a testable project decision, including the valid decision to use
no correction, rather than an automatic preprocessing step.

## Executable workflow

- Validates immutable H5AD input, integer-like raw counts, unique cell and
  feature identities, biological samples, batches, and post hoc labels.
- Blocks designs in which biological samples span ambiguous batches or an
  evaluation population occurs in only one batch.
- Physically removes evaluation labels before HVG selection, PCA, Harmony,
  Scanorama, BBKNN, neighbors, and UMAP.
- Handles Scanorama's contiguous-batch requirement internally and restores the
  original cell order before output.
- Compares every method with the same unintegrated PCA baseline using normalized
  batch-neighbor entropy, label-neighbor purity, label-graph connectivity, and
  batch and label silhouettes.
- Preserves raw counts and all source metadata, reloads every H5AD, and records
  blocked methods instead of forcing a winner.

BBKNN produces a corrected graph, whereas Harmony and Scanorama produce
corrected embeddings. None of these outputs replaces raw counts for
differential expression.

## Public evidence

The [GSE96583 crossed-donor case](../cases/gse96583-batch-integration.md)
compares all three methods on 6,400 public PBMCs spanning eight donors and two
conditions. Publisher cell type crossed with condition is withheld from fitting
and used only for conservation metrics.

BBKNN and Harmony pass the frozen gates. Scanorama is retained as a blocked
candidate because its batch-neighbor entropy declines and its label-purity loss
exceeds the declared limit. This observed result is specific to the recorded
dataset, runtime, and parameters.

## Interpretation boundary

Integration cannot repair confounding or missing biological replication.
Condition must not be mislabeled as batch, visual UMAP mixing is not a selection
criterion, and downstream inference remains donor aware. scVI and scANVI are
handled by the generative-modeling module; paired-modality WNN and MOFA+ are
handled by the multimodal module.
