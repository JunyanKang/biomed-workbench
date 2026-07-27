# Conservative Reference Annotation

The `single-cell-reference-annotation` module maps a count-backed query to a
reviewed, project-declared reference with SingleR. It then treats the reference
label as a candidate and requires independent cluster, marker, ontology, pruning,
and confidence evidence before accepting it.

## Executable workflow

- Validates immutable query and reference H5AD objects, integer-like raw counts,
  exact feature identifiers, source labels, and annotation contracts.
- Aligns common genes and runs SingleR with complete per-label scores, forced and
  pruned labels, `delta.next`, and deterministic serial execution.
- Requires group consensus, positive-marker support, bounded negative-marker
  conflict, and transitive Cell Ontology compatibility.
- Retains pruned, low-confidence, discordant, marker-conflicting,
  ontology-conflicting, and absent-reference cells as `Unknown` with reason codes.
- Preserves source counts and existing labels, verifies all source SHA-256
  identities, and reloads the annotated H5AD before admission.

This module complements atlas annotation. Atlas backends such as CellTypist,
Azimuth, and popV use packaged or externally versioned models; conservative
reference annotation is for a reference set the project can inspect and defend.

## Public evidence

The [GSE96583 held-out-donor case](../cases/gse96583-reference-annotation.md)
uses six donors as the reference and two disjoint donors as the query.
Megakaryocytes are removed from the reference before execution to test whether an
unsupported population is retained as Unknown.

## Interpretation boundary

High accepted-cell accuracy can coexist with uneven class coverage. In the
current public case, CD8 T and NK populations are frequently retained as Unknown.
The module therefore provides conservative evidence, not a claim of complete
automatic annotation. Unknown and discordant populations should proceed to atlas
consensus, marker review, trajectory context, or expert adjudication.
