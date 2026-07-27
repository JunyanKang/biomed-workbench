# Gated scVI And scANVI Modeling

The `single-cell-generative-modeling` module trains scVI or scANVI from
integer-count H5AD input and treats model admission, annotation suggestion, and
donor-aware inference as separate decisions.

## Executable workflow

- Validates raw counts, unique identities, biological samples, batches,
  reviewed labels, and an explicit Unknown state.
- Physically removes reviewed labels from metadata visible to the base scVI
  model.
- Uses deterministic stratified label holdout for scANVI and reports macro-F1
  and balanced accuracy before final training.
- Compares latent neighborhoods with an unintegrated PCA baseline for batch
  entropy, known-label purity, and label connectivity.
- Preserves reviewed and Unknown labels, exposes scANVI predictions only as
  suggestions, saves and reloads the model, and reloads the H5AD.
- Can emit a bounded optional scVI/scANVI Bayesian differential-expression
  table only after model admission, with a declared metadata contrast,
  `mode="change"`, explicit delta, required result fields, and a fixed result
  bound.
- Selects no model when any mixing, conservation, annotation, source, or reload
  gate fails.

Bayesian DE is exploratory cell-level model evidence. Raw counts and donor
identities remain authoritative for pseudobulk and other donor-aware inference;
this branch cannot establish a condition-level or population-level contrast.

## Public evidence

The [GSE96583 held-out-donor case](../cases/gse96583-generative-modeling.md)
removes publisher labels for two complete donors before scVI/scANVI execution.
scANVI suggestions reach 92.75% overall accuracy on 400 unseen-donor cells, but
both scVI and scANVI are blocked because donor-neighborhood mixing declines.
No model is selected.

## Interpretation boundary

High overall accuracy can conceal weak rare-class performance. Suggestions do
not overwrite Unknown cells and require independent marker, ontology, and expert
review. A generative latent space is not automatically preferable to no
integration or to a classical integration method.
