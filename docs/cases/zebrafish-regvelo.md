# Zebrafish Neural-Crest RegVelo Acceptance

This public-data acceptance case runs the project-owned regulatory-velocity
template on the official RegVelo zebrafish neural-crest Smart-seq3 dataset and
its companion multiome-derived prior network.

## Evidence identity

- Official H5AD: 697 cells by 8,012 source features, bound to its download URL
  and SHA-256.
- Official prior GRN: 4,508 by 4,508, bound to its download URL, axis
  orientation, and SHA-256.
- Official preprocessing profile: 30-neighbour graph, 50 principal components,
  scVelo moments, RegVelo 0.4.2 preprocessing and correlation filtering.
- Model space: 697 cells by 1,008 genes, 81 transcription-factor regulators,
  and 4,309 target-regulator edges.
- Execution: hard and soft RegVelo constraints, 20 epochs each, model
  persistence, output reload, finite velocity, gene-resolved latent time, and
  latent state.
- Reproducibility: two independent template executions must have identical
  parameters, training histories, hard-soft comparison, velocity, latent time,
  and latent state.

## Layer semantics

The official source and moment layers contain finite nonnegative fractional
values. They are therefore declared and validated as
`nonnegative-continuous`, never rounded or relabelled as molecule counts. The
same template separately retains its executed `integer-counts` path for raw
count-backed projects.

## Independent direction review

Developmental stage and cell type columns are removed before preprocessing and
model fitting, then restored by exact cell identity only after the derived
input is frozen. Median gene-resolved latent time is subsequently compared with
stage order. Stages require at least 20 cells, so the two-cell `3ss` stage is
retained but excluded from the directional gate. The 695 eligible cells show a
Spearman correlation above 0.7 between latent time and stage order.

Hard-versus-soft velocity agreement is recorded separately as a mode
sensitivity warning. The case therefore supports executable regulatory
velocity and independent direction, but not mode robustness, superiority over
scVelo or VeloVI, CellRank fate conclusions, perturbation causality, or
portability to another dataset.

The checked machine-readable result is
`reports/public-case-zebrafish-regvelo.json`.
