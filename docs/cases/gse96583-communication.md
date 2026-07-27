# GSE96583 Sample-Aware Cell Communication

This public-data acceptance case tests whether replicated ligand-receptor
hypotheses can be recovered without treating cells as biological replicates.

## Frozen design

1. Published singlet calls and cell-type annotations are retained from
   GSE96583.
2. B cells, CD4 T cells, CD14+ monocytes, and NK cells are represented in every
   donor-condition sample.
3. At most 100 cells per sample and cell type are selected by stable SHA-256
   order.
4. Genes detected in at least 20 selected cells are retained without
   condition-based ranking.
5. The LIANA CellPhoneDB method runs independently in each sample with 100
   permutations and fixed seed.
6. Each interaction must pass sample-level FDR in at least six independent
   samples and BH-controlled Fisher combination within condition.
7. Zero permutation p values are floored at `1 / 101` before combination.

## Observed result

- 5,857 cells, 9,471 genes, eight donors, two conditions, and 16 biological
  samples.
- All 16 sample analyses completed.
- 3,870 sample-level interaction rows and 867 replicate summaries were
  retained.
- 185 interactions passed the replication contract: 87 in control and 98 in
  stimulated samples.
- Every accepted interaction has at least six independently significant
  samples.
- Stimulated `CXCL10-CXCR3` and `CCL2-CCR1/CCR5` communication patterns were
  observed as posthoc biological sanity checks; they were not used to select
  thresholds or pass the case.
- Source files, raw counts, sample identities, output tables, and report
  reloads passed.

The case validates the LIANA CellPhoneDB route under this source, runtime,
parameter set, and replication rule. It does not establish physical signaling,
causality, or a formal control-versus-stimulation interaction effect.

Machine-readable evidence:
[`reports/public-case-gse96583-communication.json`](../../reports/public-case-gse96583-communication.json).
