# NCBI TP53 Identifier Resolution

The public acceptance case resolves the human symbol `TP53` through NCBI
Entrez Gene. It checks that the returned exact current record has NCBI Gene ID
`7157` and taxon `9606`, records the query and candidate set, and preserves the
rule that ambiguity yields no reusable identifier.

The case validates a database identifier at the time of retrieval. It does not
establish a biological conclusion about TP53.
