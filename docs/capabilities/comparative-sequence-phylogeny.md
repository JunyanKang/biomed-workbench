# Comparative Sequence Phylogeny

`comparative-sequence-phylogeny` is the sequence-level comparative analysis module. It accepts a reviewed set of homologous DNA, RNA, or protein records plus a record-level metadata table. It generates project-specific code from `templates/run_mafft_iqtree.py` and requires observed execution in an existing compatible scientific environment.

The workflow validates complete record accounting before and after MAFFT alignment, then requires IQ-TREE model, support, seed, tree-tip and output reload evidence. Failed tools block the run; the template never replaces a failed alignment with direct positional comparison or creates a synthetic tree.

This module does not establish homology or orthology from arbitrary sequences, call variants, phase haplotypes, infer recombination, estimate divergence times, prove selection, reconstruct species history, or establish function. Use `multi-sample-variant-concordance` for a separately normalized and phased multi-sample VCF state matrix.

See [the public UniProt cytochrome c case](../cases/uniprot-cytochrome-c-phylogeny.md) for the executable acceptance evidence.
