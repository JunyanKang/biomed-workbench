# Demographic Simulation

`msprime-demographic-simulation` creates reproducible coalescent simulation
evidence from a demographic scenario declared before execution. It is intended
for method calibration, sensitivity analysis, and study-design questions such
as whether a downstream pipeline can recover signals under a stated population
history. It is not an empirical demographic inference engine.

## Supported Scenarios

The executable template supports one population with exactly one of the
following predeclared histories:

- `constant`: a single positive effective population size;
- `bottleneck`: baseline size, bottleneck size, and strictly ordered start and
  end times; or
- `expansion`: current size, ancestral size, and one change time.

The request also freezes the sample count, sequence length, recombination rate,
mutation rate, and random seed. It writes a tskit tree sequence, VCF, and a
normalized JSON report. The report records the source parameter digest,
observed `msprime` version, output hashes, tree count, site count, and
diversity. Output paths must be new and may not be symlinks.

## Scientific Use

Use this module before a consequential pipeline comparison or power-oriented
design decision. State the scientific purpose and decide scenarios before
looking at simulation results. The workbench can then use the generated VCF as
a clearly labelled simulated input to validate a compatible downstream method,
for example variant handling or GWAS fine-mapping assumptions.

The simulated data are conditional on all declared assumptions. A good result
does not show that the chosen history occurred in a real population, that its
parameters are correct, that selection or population structure is absent, or
that a downstream method is valid outside the simulated conditions.

## Compatibility

The observed execution evidence covers `msprime` 1.4.2 in an existing Python
3.14.3 runtime. The module accepts `msprime >=1.4,<1.5` and Python
`>=3.10,<3.15`; it checks the installed version before execution and records it
in the result. The workbench never installs or operates the runtime for a
project.

## Quality Gates

Execution stops when parameters do not exactly match the chosen model, a
bottleneck time order is invalid, values are nonpositive where prohibited, the
seed is missing, an output already exists, or output reload and provenance
checks fail. A major interpretation gate keeps all claims at the conditional
simulation level.
