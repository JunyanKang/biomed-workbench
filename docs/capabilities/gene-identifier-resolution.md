# Stable Gene Identifier Resolution

`gene-identifier-resolution` converts a declared gene symbol and organism into
a reusable NCBI Gene ID only when current NCBI Gene records contain exactly one
exact symbol or nomenclature-symbol match. It retains every candidate, the
search context, selection policy, and any unresolved state.

This is a prerequisite module for workflows that require a stable source Gene
ID, including NCBI ortholog retrieval. It never selects the top-ranked search
record merely because it is first. When no exact candidate or more than one
exact candidate exists, no identifier is emitted for downstream use.

Resolution establishes database identity only. It is not evidence of
orthology, conserved function, regulation, expression, phenotype, isoform
equivalence, or experimental suitability.
