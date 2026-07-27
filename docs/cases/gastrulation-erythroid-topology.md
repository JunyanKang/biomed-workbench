# Mouse-Gastrulation Erythroid Topology

This public-data acceptance case tests a single developmental lineage with
Slingshot, Monocle3, and the applicable tradeSeq hypotheses.

## Frozen design

1. Up to 12 cells per published sample are selected by stable SHA-256 order,
   without stage or cell-type labels.
2. The 160 most detected features are selected without stage or cell-type
   labels.
3. Published Blood progenitors 1 and Erythroid3 annotations define the
   predeclared start and end orientation.
4. Seven embryonic stages are used only for postfit direction validation.
5. Association and start-versus-end tests are required. Pattern and
   differential-end tests are explicitly not applicable to one lineage.

## Observed result

- 297 cells from all 27 samples and all seven stages.
- One Slingshot lineage with all 297 cells supported.
- Slingshot versus external-time Spearman correlation: 0.8276.
- Monocle3 versus external-time Spearman correlation: 0.8171.
- Slingshot versus Monocle3 Spearman correlation: 0.9796.
- 160 association and 160 start-versus-end results.
- Counts, source identity, output tables, and native Monocle3 serialization
  passed the declared gates.

The public case validates a linear erythroid trajectory. The separate
deterministic bifurcation evidence validates branch-specific pattern and
differential-end behavior.

Machine-readable evidence:
[`reports/public-case-gastrulation-erythroid-topology.json`](../../reports/public-case-gastrulation-erythroid-topology.json).
