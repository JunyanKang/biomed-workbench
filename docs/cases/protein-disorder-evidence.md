# TP53 Protein Disorder Tendency Case

This compact public-service acceptance case checks the protein-disorder
evidence surface with the reviewed human TP53 UniProt accession `P04637`.
It uses the IUPred2A accession JSON contract in `long` mode, a declared score
threshold of `0.5`, and a minimum reported span length of twenty residues.

The observed request returned one found record with a 393-residue sequence and
a 393-value score profile. The module checks that prediction type, valid amino
acid sequence, score range, and residue count reconcile before it exposes any
threshold spans. The same execution preserves the exact HTTPS transport and
service-contract identifier for later reuse.

This case is an interface and provenance acceptance check. It does **not**
establish that TP53 is disordered in a particular cell state, that a reported
span is a protein domain or binding site, or that it explains a phenotype. For
a structural comparison, use the returned profile alongside an independent
structure-evidence record, inspect coverage and confidence separately, and
then define an orthogonal experimental test.

The public method and REST contract are documented by
[IUPred2A](https://iupred2a.elte.hu/help_new).
