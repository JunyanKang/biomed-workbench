# Sample-Aware Cell Communication And Secreted-Signal Activity

Languages: [English](cell-communication.md) · [中文](cell-communication.zh-CN.md)

This capability starts from single-cell data with preserved raw counts and keeps three questions separate: ligand–receptor compatibility, ligand prioritisation against a receiver state, and relative activity of secreted proteins. Their outputs are never collapsed into one generic communication score.

## CellChat

- Accepts Matrix Market, Seurat 5 RDS, or SingleCellExperiment RDS with explicit cell-type, biological-sample, and condition fields.
- Builds one CellChat object per biological sample with a fixed species database, minimum cell count, averaging method, permutation count, seed, and sender→receiver scope.
- Delivers per-sample interaction and network-count tables, CellChat objects, and PDF/PNG exports of the official `netVisual_circle`, `netVisual_chord_gene`, and `netVisual_bubble` views.
- Can build condition-pooled objects for `rankNet` and `netAnalysis_signalingChanges_scatter`; those views are permanently labelled descriptive and do not replace a biological-sample-level condition test.

The CellChat 2.2.0 adapter has executed a controlled two-sample fixture. Interaction tables, RDS objects, and official plots were reopened and checked, giving this slice `EXECUTED_FIXTURE` status. That status is not presented as public biological-case validation.

## SecAct

SecAct is called through its official R API; the workbench does not simulate it with a custom response score.

- `sample-celltype-activity` calls `SecAct.activity.inference.scRNAseq` separately within each biological sample and exports beta, standard error, z score, p value, and the official activity heat map.
- `pooled-condition-communication-descriptive` calls `SecAct.CCC.scRNAseq` and exports secreted-protein expression, activity, sender–receiver relations, and official heat-map/circle views.
- Condition-pooled mode requires an explicit opt-in and remains descriptive because the official internal test treats cells as observations rather than independent biological samples.
- SecAct activity is a model-derived relative activity estimate, not measured protein secretion, receptor activation, or causal communication.

The official SecAct 1.1.0 API adapter is complete and requires no source editing. SecAct is not installed in the current acceptance environment, so this release does not claim an observed execution and retains `CONTRACT_ONLY` status for that slice.

## LIANA, CellPhoneDB And NicheNet

LIANA, direct CellPhoneDB and CellChat run independently within each eligible biological sample and preserve method-specific score and significance semantics. NicheNet runs only when donor-aware receiver differential expression, a background gene universe, sender expression and pinned ligand–target resources are available.

The [GSE96583 public case](../cases/gse96583-communication.md) validates the LIANA–CellPhoneDB slice: 16 donor-condition samples run independently and are summarised with a predeclared independent-sample support rule. It does not simultaneously validate direct CellPhoneDB, CellChat, NicheNet or SecAct.

## Interpretation boundary

Expression compatibility, database records, CellChat probabilities, NicheNet ligand priorities and SecAct activities are distinct evidence types. None alone establishes physical contact, in-vivo direction, protein secretion, receptor activation or causality. A formal condition-level conclusion must return to independent biological samples and an estimable contrast, with an orthogonal readout when mechanism is claimed.
