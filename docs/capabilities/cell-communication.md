# Sample-Aware Cell Communication

The `single-cell-communication` module turns count-backed single-cell data into
sample-resolved communication hypotheses while keeping cell-level expression,
biological replication, method semantics, and causal interpretation separate.

## Executable workflow

- Validates integer-like raw counts, gene identifiers, reviewed cell types,
  biological samples, conditions, species, and resource compatibility.
- Runs LIANA CellPhoneDB, direct CellPhoneDB, or CellChat independently within
  each eligible biological sample.
- Retains method-native scores and p values rather than treating unlike outputs
  as interchangeable.
- Controls multiplicity within each sample and requires a predeclared number of
  independently significant samples before an interaction is called
  replicated.
- Floors zero permutation p values at the finite permutation resolution before
  Fisher combination and applies BH correction within condition and method.
- Uses NicheNet only when donor-aware receiver differential expression,
  background genes, sender expression, and versioned ligand-target resources
  are available.
- Preserves blocked samples, Unknown populations, source counts, parameters,
  versions, resources, and reloadable output digests.

## Public evidence

The [GSE96583 sample-aware case](../cases/gse96583-communication.md) executes the
LIANA CellPhoneDB method separately on 16 donor-condition samples. It observes
185 interactions supported by within-sample FDR in at least six independent
samples and by a BH-controlled cross-sample combination. The public acceptance
case is complemented by executable fixture evidence for direct CellPhoneDB,
CellChat, and NicheNet.

## Interpretation boundary

Ligand and receptor coexpression plus database support defines a communication
hypothesis, not physical contact, in vivo direction, pathway activity, or
causality. Separate condition summaries are not a formal differential
interaction test. Condition-level conclusions require an estimable
sample-aware contrast and independent downstream evidence.
