# RegVelo Regulatory Velocity

## Scientific Role

The `single-cell-regulatory-velocity` module adds RegVelo as an internal analysis capability of the unified workbench. Users describe the biological question and available data through the same `biomed-workbench` entry; the router composes this module with RNA-velocity, regulatory-network, ATAC-regulatory, trajectory, and fate-mapping modules when the project requires them.

RegVelo contributes a gene-regulatory-network prior to RNA-velocity modelling. The implemented workflow can estimate velocity, gene-resolved latent time, and a latent dynamic state; compare hard and soft regulatory constraints or repeated seeds; persist and reload fitted models; and prepare admitted dynamics for CellRank fate analysis and regulator-perturbation hypothesis generation.

## Required Evidence

- An H5AD object with aligned spliced and unspliced layers declared as either
  integer counts or finite nonnegative continuous abundances with complete
  quantification and preprocessing provenance.
- Unique cell and feature identifiers with declared quantification and feature-namespace provenance.
- An independently constructed, versioned target-by-regulator network with a stable digest.
- A declared dense-memory budget because RegVelo 0.4.2 requires dense working layers in the validated path.
- Independent time, root, terminal, lineage, or perturbation evidence when directional or mechanistic claims are planned.

The prior network may come from reviewed literature, curated resources, perturbation data, SCENIC+, paired RNA and ATAC evidence, or another justified source. A network selected to reproduce the desired trajectory is circular evidence and is rejected.

## Executable Scope

The project-owned template validates layers under their declared semantics and
never rounds continuous abundance into counts. It validates network identities,
converts only a bounded working copy to dense arrays, expands the declared
target-by-regulator matrix into the square gene-aligned tensor required by
RegVelo 0.4.2, executes all declared constraint modes or seeds, records training
histories, computes velocity and latent outputs, saves every model, reloads the
models, writes a new derived H5AD object, and verifies that source artifacts
remain unchanged.

The observed verification fixture executed:

| Component | Verified result |
| --- | --- |
| RegVelo | 0.4.2 |
| Constraint modes | Hard and soft |
| Fixture | 96 cells, 24 genes, 6 regulators |
| Core outputs | Velocity, gene-resolved latent time, 10-dimensional latent state |
| Persistence | Every model saved and reloaded |
| Source handling | H5AD, count layers, identifiers, and GRN remained immutable |

The [public zebrafish neural-crest acceptance
case](../cases/zebrafish-regvelo.md) additionally executes the continuous-layer
path on the exact official H5AD and GRN. It retains 697 cells, derives the
documented 1,008-gene and 81-TF model space, executes 20-epoch hard and soft
models, and evaluates frozen latent time against withheld developmental stage.
The resulting stage association passes the directional gate, while modest
hard-versus-soft velocity agreement remains an explicit sensitivity warning.

## Compatibility Boundary

The validated profile uses Python 3.11, NumPy 1.26, SciPy 1.15, scVelo 0.3.4, scvi-tools 1.2.0, CellRank 2.0.7, torch 2.4.1, JAX and jaxlib 0.4.35, and the companion versions recorded in the module manifest and live report. These versions are provenance for the passing execution, not a general instruction to freeze every future project.

Observed RegVelo 0.4.2 behaviour requires explicit safeguards:

- sparse spliced and unspliced arrays cannot be passed directly through the validated initializer;
- official RegVelo preprocessed and moment layers can be fractional and must be
  declared as nonnegative continuous abundance rather than rejected or
  misrepresented as integer molecule counts;
- a rectangular model tensor fails, so the original network is retained while a square gene-aligned working matrix is built explicitly;
- NumPy 2 produced compiled-extension ABI failures in the tested dependency stack;
- newer JAX profiles failed on the removed `jaxlib.xla_extension` interface;
- explicitly passing custom `n_latent` or `n_hidden` values triggers duplicate-keyword failure, so the validated 0.4.2 path uses its default 10-dimensional latent and 256-unit hidden architecture.

A future RegVelo release is accepted only after a new compatibility experiment updates these observations.

## Scientific Quality Gates

- Preserve the original sparse count layers and block silent dense conversion above the declared budget.
- Require exact GRN namespace and orientation reconciliation; do not guess symbols, homologs, targets, or regulators.
- Retain failed runs, histories, mode differences, seed instability, and baseline disagreement.
- Compare against scVelo or VeloVI when a conclusion depends on RegVelo-specific improvement.
- Validate direction with evidence withheld from model fitting.
- Test CellRank terminal states, kernel weights, and neighbourhood choices before interpreting fate probabilities.
- Treat regulator perturbation results as model-dependent hypotheses, not causal or experimentally validated effects.

## Typical Composition

A regulatory-dynamics project can route in parallel to conventional scVelo and RegVelo, use SCENIC+ or paired RNA and ATAC analysis to establish the prior network, compare the two dynamics branches, pass admitted velocity fields to CellRank, and rank perturbation hypotheses for experimental follow-up. The workbench preserves each branch and revises the hypothesis when the GRN prior, direction, stability, or fate sensitivity gates fail.
