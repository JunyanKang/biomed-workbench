# GSE96583 Held-Out-Donor Reference Annotation

This public-data acceptance case evaluates the packaged SingleR, marker, and Cell
Ontology workflow on control-arm PBMCs from GEO GSE96583.

## Frozen design

1. Six donors form the reference and two disjoint donors form the query.
2. At most 120 cells per supported reference label are selected by stable
   SHA-256 order.
3. Megakaryocytes are excluded from the reference as a predeclared unsupported
   population.
4. Query clusters are built without publisher labels.
5. A PF4/PPBP rule assigns platelet-lineage ontology constraints before mapping.
6. Publisher query labels are absent from all method inputs and joined only after
   the annotated H5AD is frozen.

## Observed result

- 840 reference cells, 4,139 query cells, and 35,635 genes.
- 3,373 accepted annotations and 766 Unknown cells.
- 97.95% accuracy among accepted cells from supported classes.
- 81.79% supported-class coverage.
- Macro F1 of 0.643 when Unknown predictions are retained as penalties.
- 56.25% Unknown retention for the held-out Megakaryocyte class.
- Source identity, complete scores, counts, existing labels, cell accounting, and
  output reload gates all passed.

The conservative policy leaves many CD8 T and NK cells unresolved. This is
reported as a limitation rather than hidden by an overall accuracy statistic.

Machine-readable evidence:
[`reports/public-case-gse96583-reference-annotation.json`](../../reports/public-case-gse96583-reference-annotation.json).
