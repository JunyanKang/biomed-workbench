# Single-Cell Fate Mapping

## Scientific role

The `single-cell-fate-mapping` module converts an admitted directional signal
into explicit cell-to-cell transitions, terminal-fate probabilities, and
candidate lineage-driver associations. It supports CellRank velocity,
pseudotime, and real-time optimal-transport kernels without treating them as
interchangeable evidence.

The unified router can compose it after scVelo, RegVelo, a validated
pseudotime workflow, or a replicated temporal study. The module does not infer
that a dataset contains a trajectory merely because one of these inputs is
available.

## Kernel selection

| Evidence available | Primary kernel | Required independent review |
| --- | --- | --- |
| Admitted scVelo or RegVelo state and velocity | VelocityKernel | Withheld time or independently derived pseudotime |
| Validated continuous ordering | PseudotimeKernel | Experimental time or another direction source not used to construct the ordering |
| Replicated observations at three or more times | moscot TemporalProblem and RealTimeKernel | Independently derived pseudotime or lineage evidence |

A velocity project may add a predeclared ConnectivityKernel weight as a
sensitivity analysis. The workbench preserves each kernel and its weights
separately; it never chooses or averages models because one yields the desired
fate.

## Input semantics

Expression is declared independently as integer counts or log-normalized
continuous abundance. Continuous values are never rounded or relabelled as
counts. Velocity mode additionally names the state matrix, signed velocity
matrix, and neighbourhood representation explicitly. Every matrix must align
to the same unique cells and features.

Terminal states require a documented biological source and minimum cell count.
Annotation-defined terminal states are allowed, but the resulting fate
probabilities are conditional on those definitions. Automatic state discovery,
manual state assignment, and perturbation comparisons are kept as distinct
analyses.

## Executable outputs

- Row-stochastic cell transition matrix.
- Cell-by-terminal-state fate probabilities that are finite, nonnegative, and
  sum to one.
- Gene-by-lineage driver statistics using the declared expression semantics.
- Reloadable H5AD with preserved source expression and identifiers.
- Cell fate table, driver table, detected runtime, complete parameters, source
  digests, and quality-gate report.
- Separate kernel-sensitivity evidence when multiple justified models are run.

## Scientific quality gates

- Block missing or guessed state, velocity, expression, representation,
  temporal, terminal-state, or sample semantics.
- Require a mode-appropriate direction source that was not used to construct
  the tested kernel.
- Verify transition and fate stochasticity, cell alignment, terminal-state
  coverage, source immutability, and output reload.
- Treat GPCCA-clamped terminal-cell consistency as an implementation check,
  never as independent biological validation.
- Preserve disagreement across velocity, connectivity, pseudotime, and
  real-time kernels.
- Do not convert fate probabilities into clonal ancestry, causal regulation,
  or condition-level inference without the necessary experimental design.

## Public-data evidence

The [zebrafish RegVelo-to-CellRank acceptance
case](../cases/zebrafish-cellrank-fate.md) validates the CellRank 2.3.2 velocity
path on 697 official neural-crest cells. Pure velocity and a 20% connectivity
sensitivity kernel both move forward in withheld developmental stage; two
independent pure-velocity runs are exactly reproducible; and fate sensitivity
passes the recorded bounds.

This acceptance is source-, velocity-, representation-, neighbourhood-,
terminal-state-, runtime-, and threshold-specific. The module remains
experimental until a user's project passes its own direction, sensitivity,
replication, and biological-validation gates.

## Failure recovery

When a transition fails direction, stochasticity, terminal coverage, or
sensitivity checks, the analysis remains blocked. Codex should inspect input
semantics and provenance, compare justified kernels and neighbourhoods, revisit
terminal-state evidence, and return upstream to velocity or trajectory
validation. It must not reverse time, relabel cells, or tune weights to force a
preferred conclusion.
