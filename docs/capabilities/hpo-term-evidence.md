# HPO Terminology Evidence

`hpo-term-evidence` resolves one or more declared Human Phenotype Ontology
identifiers through the public HPO service. It records the exact identifier,
preferred name, definition, bounded synonyms, hierarchy count, transport
provenance, and explicit not-found state for every requested term.

It is useful for making phenotype terminology unambiguous before a clinical or
genetic analysis. It does not infer HPO terms from notes, diagnose a person,
show that a phenotype is present, rank diseases or genes, or establish causal
evidence for a variant or intervention.

The module requires canonical `HP:0000000` identifiers. A missing identifier is
preserved in `not_found_ids`; it is never silently turned into a label. Clinical
interpretation still requires source records, timing, negated findings,
ascertainment, and qualified review.
