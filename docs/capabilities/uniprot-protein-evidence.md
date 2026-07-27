# UniProtKB Protein Evidence

`uniprot-protein-evidence` retrieves the identity-critical public UniProtKB
record for one exact accession. It returns the primary accession, entry ID,
review status, recommended protein name, gene names, organism, sequence length,
mass, checksums, and response provenance.

The module accepts an accession, not a free-text query or arbitrary URL. This
keeps protein identity explicit and makes a later structure, sequence, or
annotation workflow reproducible.

A UniProtKB record is an annotation snapshot. It does not establish protein
abundance, activity, tissue expression, interaction, disease mechanism, or
causality. Keep its observed version and retrieval provenance with all
downstream evidence.
