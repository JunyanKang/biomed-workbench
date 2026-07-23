# Zebrafish RegVelo-to-CellRank Fate Acceptance

This chained public-data case executes the project-owned CellRank fate template
on the admitted RegVelo output from the official zebrafish neural-crest
Smart-seq3 dataset. It tests whether regulatory velocity can pass through the
workbench contract into a separately reviewable fate analysis.

## Evidence identity

- Upstream evidence: the accepted official RegVelo H5AD and GRN case, bound by
  report digest.
- CellRank input: 697 cells by 1,008 genes with finite signed RegVelo velocity,
  continuous expression state, and a 10-dimensional RegVelo representation.
- Runtime: CellRank 2.3.2 with the exact companion versions recorded in the
  machine-readable report.
- Terminal states: `mNC_head_mesenchymal`, `mNC_arch2`, `mNC_hox34`, and
  `Pigment`, matching the official RegVelo tutorial.
- Execution: two independent pure-velocity runs and one
  80%-velocity/20%-connectivity sensitivity run.

## Direction and reproducibility

Developmental stage is not used to construct the RegVelo model, CellRank
neighbourhood, velocity kernel, or terminal-state assignments. After each
transition matrix is frozen, its expected stage change must be positive. The
observed expected changes are 0.2012 for the pure velocity kernel and 0.1615
for the connectivity-weighted sensitivity kernel.

The two independent pure-velocity executions produce exactly identical
697-by-697 transition matrices, 697-by-4 fate-probability matrices, and fate
tables.

## Kernel sensitivity

Across 467 non-terminal cells, pure and connectivity-weighted fate
probabilities have a flattened Pearson correlation of 0.9981. The maximum
absolute fate-probability difference is 0.1096, and the maximum-fate assignment
agrees for 97.43% of non-terminal cells. These values pass the frozen software
acceptance bounds but remain sensitivity evidence rather than proof of
biological robustness.

## Claim boundary

The four terminal states are annotation-defined and imposed on GPCCA.
Consequently, terminal cells receiving their own fate with probability one is
an implementation consistency check, not independent validation. The case does
not establish clonal ancestry, automatic terminal-state discovery,
hard-versus-soft RegVelo fate robustness, causal regulators, condition-level
inference, or portability to another dataset.

The checked machine-readable result is
`reports/public-case-zebrafish-cellrank.json`.
