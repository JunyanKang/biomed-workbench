# Genome Coordinate Liftover

`genome-coordinate-liftover` converts declared BED intervals between declared
reference assemblies with CrossMap and an immutable UCSC chain artifact. It is
for coordinate translation, not biological interpretation.

The module requires zero-based half-open BED semantics, a stable column-four
record identifier, declared source and target assemblies, a chain URL and
SHA256, and explicit policies for split and unmapped records. Its result always
contains mapped, split-mapped, and unmapped accounting plus commands, versions,
input and chain digests.

It must not be used to claim allele normalization, gene or peak equivalence,
orthology, regulatory conservation, or functional conservation. Those require
separate reference, annotation, and biological evidence.
