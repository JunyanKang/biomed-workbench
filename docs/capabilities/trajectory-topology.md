# Lineage Topology And Gene Programs

The `single-cell-trajectory-topology` module infers one or more lineages with
Slingshot and Monocle3, validates orientation against independent time, and
tests lineage-associated expression with tradeSeq.

## Executable workflow

- Requires immutable integer counts, exact cell identifiers, a reviewed
  embedding, biological samples, external time, clusters, root cells, and one
  or more terminal clusters.
- Fits Slingshot curves and lineage weights from declared start and end
  clusters.
- Learns and orders an independent Monocle3 graph from declared root cells.
- Checks both methods against external time and against each other.
- Fits tradeSeq association and start-versus-end tests for every lineage.
- Runs pattern and differential-end tests only when at least two lineages make
  those comparisons mathematically defined.
- Preserves unassigned cells and method-specific pseudotimes, reloads gene and
  cell tables, and reloads the native Monocle3 object and indexes.

## Complementary evidence

The [public mouse-gastrulation erythroid case](../cases/gastrulation-erythroid-topology.md)
validates one lineage across 27 published samples and seven external stages.
The deterministic bifurcation fixture independently validates two lineages,
branch weights, all four tradeSeq test families, and planted branch programs.

Together these cases cover linear and branching execution without presenting a
linear trajectory as branch evidence.

## Interpretation boundary

Topology depends on the supplied embedding, reviewed clusters, and independent
orientation anchors. Correlation with time supports direction but does not
prove ancestry. tradeSeq cell-level trends characterize trajectories; they are
not donor-level treatment inference.
