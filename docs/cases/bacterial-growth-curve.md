# Bacterial Growth-Curve Model Selection Case

This deterministic acceptance case exercises the bacterial growth-curve module
with two independently labelled synthetic cultures measured across seven
timepoints. It supplies an explicit OD blank, preserves every replicate-level
measurement, compares logistic and modified Gompertz curves, and retains both
candidate diagnostics rather than reporting only a fitted lag phase.

The acceptance condition requires a finite post-blank dynamic range, a
converged candidate curve, a selected empirical model, all timepoints to retain
both observations, and a residual-quality result that reaches the module's
declared fit threshold. The test does not select a universal preferred growth
model; it checks that model selection is reproducible for this declared
measurement series.

The case is deliberately not a strain-fitness, viability, contamination, or
treatment-effect result. Those claims require culture identity, blanks and
controls, plate or vessel layout review, independently cultured biological
replicates, and a design-aware between-condition analysis.
