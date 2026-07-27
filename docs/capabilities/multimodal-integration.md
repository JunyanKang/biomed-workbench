# Multimodal Single-Cell Integration

The `single-cell-multimodal-integration` module integrates exact paired cells
without replacing modality-specific measurements or treating a latent
representation as biological truth.

## Executable workflow

- Reads 10x RNA+ATAC HDF5, Seurat v5, or H5MU inputs with explicit feature
  types, immutable source counts, unique features, and exact paired-cell order.
- Builds RNA PCA plus ATAC LSI or ADT PCA and executes Seurat weighted nearest
  neighbours with cell-specific modality weights.
- Retains and reloads weighted KNN and SNN graphs, neighbours, embeddings,
  clusters, modality weights, preprocessing parameters, versions, and digests.
- Fits MOFA+ on two or more explicitly transformed views and retains factors,
  view-specific feature loadings, variance explained, and the saved model.
- Keeps WNN neighbourhood evidence and MOFA+ factor evidence separate.

## Public evidence

The [10x PBMC Multiome case](../cases/pbmc-multiome-integration.md) starts from
the official filtered feature-barcode HDF5 and selects cells and features
without cluster labels. It validates paired RNA+ATAC preparation, WNN, MOFA+,
source preservation, and output reload.

## Interpretation boundary

WNN weights describe local modality usefulness and MOFA+ factors describe
variance in the declared model matrices. Neither result proves a cell identity,
causal cross-modal regulation, missing-modality recovery, or donor-level
condition effect. CITE-seq RNA+ADT execution remains covered by the complete
executable fixture rather than the RNA+ATAC public case.
