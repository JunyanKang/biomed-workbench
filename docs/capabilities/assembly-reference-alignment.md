# Assembly Reference Alignment

`assembly-reference-alignment` aligns declared DNA FASTA assembly records to a
declared reference with minimap2. It freezes the `asm5`, `asm10`, or `asm20`
preset before execution, validates every FASTA record, reloads the produced PAF,
and preserves query and target record accounting with input digests and tool
version provenance.

Alignment is evidence of sequence placement under the declared preset. It is
not a variant call, haplotype, synteny, structural-variation, gene-orthology,
or functional-conservation result. Those questions require their own data,
methods, and quality gates.
