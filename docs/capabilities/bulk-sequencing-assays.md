# Scientific taxonomy and executable capabilities for bulk sequencing

Bulk, single-cell, and spatial describe observational scale. They are not peers of labels such as epigenomics or transcriptomics. Biomed Workbench classifies capabilities along three orthogonal facets:

1. data scale: bulk, single-cell, spatial, or cross-scale universal;
2. measurement family and exact assay;
3. method role: assay-specific, reusable within a family, cross-scale statistical, or research infrastructure.

Antibody, target, spike-in/internal reference, RNase H treatment, peak recall, and normalization remain design or analysis parameters. They never become omics classes. For example:

`bulk → protein- or mark-associated chromatin enrichment → CUT&Tag → S9.6 target/antibody → optional internal-reference scaling → RNase H specificity evidence`

The current bulk families cover steady-state RNA expression; ChIP-seq, CUT&RUN and CUT&Tag; R-loop mapping by DRIP-seq/DRIPc-seq, sDRIP/ssDRIP-seq, qDRIP-seq, R-ChIP, MapR and sensor-declared CUT&Tag; ATAC-seq and DNase-seq; RIP-seq and CLIP/LACE variants; Ribo-seq; GRO-seq, PRO-seq, TT-seq and NET-seq; WGBS, RRBS and EM-seq; Hi-C and related chromosome-conformation assays; and MeRIP/m6A enrichment.

Ribo-seq retains Ribo-TISH and Ribotricer ORF calls separately after P-site and triplet-periodicity quality control; optional callers such as RiboCode are sensitivity branches, not votes that create a true ORF by union. LACE-seq binds the primary paper, GSE137925 metadata, and public analysis code at commit `b8d1193638190c50c8553847ad3a1653544dbe14`. Its released FASTQ path runs Cutadapt 1.15 and Bowtie 1.2.3 in immutable images, performs the paper's sequential adapter and poly(A) trimming, pre-rRNA depletion, mapping with two mismatches and at most ten multihits, strand-aware BED generation, matched IgG subtraction, and cluster calling. All consequential trimming, mapping, RPM, merging, and strand-support parameters are exposed through the request rather than source edits.

The RIP-seq path executes RIPSeeker 1.28.0 in a pinned Bioconductor 3.11 container on explicitly paired RIP and input/IgG BAM files. Binning, strand policy, multihit assignment, HMM models, significance thresholds, region tables, and native R model objects are preserved without requiring a legacy host R installation or template editing.

R-loop is registered as a measurement family and biological object, not an assay. The `bulk-r-loop-mapping` module therefore keeps sensor, ex vivo versus in situ context, fragmentation or cleavage, sequenced moiety, strandedness, internal reference and RNase H control distinct. Cross-method disagreement is expected evidence because DRIP-family, R-ChIP, MapR and CUT&Tag do not observe identical molecular or spatial contexts.

Public-data end-to-end acceptance covers nf-core/riboseq, nf-core/nascent, nf-core/clipseq, nf-core/methylseq, nf-core/hic, ENCODE ATAC-seq, RLPipes, exomePeak2, and assay-specific TT-seq, NET-seq, RIPSeeker, and LACE-seq executors. Every released path records actual versions, parameters, input and output fingerprints, and reloads its native objects, intervals, matrices, tracks, and quality reports. The generated taxonomy and `reports/public-case-*.json` records are the current release inventory.
