# UniProt Cytochrome c Phylogeny Case

The public acceptance case uses four reviewed UniProt cytochrome c sequences: human `P99999`, mouse `P62897`, horse `P00004`, and yeast `P00044`. The repository fixture preserves the record-level source URLs and the verifier records SHA-256 digests for both sequence and metadata inputs.

The case runs a validated MAFFT 7.x build (`>=7.505,<8`) and IQ-TREE `3.1.2` with model `LG+G4`, one thousand ultrafast bootstrap replicates, fixed seed `17`, and the declared yeast record as an outgroup-presence check. The execution report records the exact observed tool versions. The acceptance gates require all four records in the alignment and tree, exact tip accounting, and a reloadable Newick tree.

The case is a method acceptance test. It does not claim that the observed topology proves orthology, species history, divergence time, selection, recombination, or functional conservation.
