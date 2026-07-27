# GSE96583 Regulatory Programs

This public-data acceptance case tests label-withheld GRNBoost2 discovery and
AUCell scoring on paired control and interferon-stimulated PBMC donors.

## Frozen design

1. Thirty singlets per donor-condition sample are selected by stable hash
   without cell type or condition labels.
2. Eight hundred genes are selected by detected-cell and total-count ranking;
   a predeclared PBMC TF control list is retained without using outcomes.
3. Library-normalized log expression is supplied to GRNBoost2.
4. Activating coexpression modules require at least five targets and are
   scored in every cell with AUCell.
5. Treatment labels are joined only after fitting.
6. Program activity is summarized within each donor-condition and evaluated as
   paired stimulated-minus-control differences.

## Observed result

- The design retains 480 cells, eight donors, and 16 biological samples.
- GRNBoost2 returns 23,816 adjacencies and 179 candidate modules.
- Thirty-one TF programs pass the declared selection and AUCell gates.
- IRF1, IRF7, and STAT1 program activity increases in all eight donors.
- STAT2 program activity increases in seven of eight donors.
- Source files and all adjacency, program, AUC, parameter, version, and digest
  outputs are preserved and reloaded.

These are TF coexpression programs, not motif-pruned regulons. Full cisTarget
and SCENIC+ execution requires matched motif rankings and paired accessibility.

Machine-readable evidence:
[`reports/public-case-gse96583-regulatory-program.json`](../../reports/public-case-gse96583-regulatory-program.json).
