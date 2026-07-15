# Omics And Single-Cell Analysis

## Scientific Role

This capability area coordinates sequencing data from input and design validation through statistical analysis, biological interpretation, hypothesis revision, and publication delivery. The workbench treats biological replication, immutable raw measurements, reference identity, and observed output checks as first-class requirements.

## Sequencing And Genomic Foundations

- Read-level quality assessment with FastQC and fastp, cross-sample aggregation with MultiQC, and declared-reference contamination screening.
- BWA-MEM alignment, samtools alignment qualification, coordinate sorting and indexing.
- Genomic interval overlap with build-matched BED contracts.
- BGZF and tabix VCF handling, explicit variant filtering, multi-sample concordance, and callable-territory-aware tumour mutation burden.

These steps are represented by independently routable modules such as `read-quality-fastqc`, `read-quality-fastp`, `quality-report-multiqc`, `read-contamination-screen`, `dna-align-bwa-mem-single`, `alignment-quality-samtools`, `interval-overlap-bedtools`, `variant-filter-vcf`, and `tumor-mutation-burden-vcf`.

## Bulk Expression And Systems Analysis

- Expression-matrix validation and sample-level quality assessment.
- Differential expression with explicit design and statistical outputs.
- Gene-set overrepresentation, biological network summaries, FDR-controlled coexpression hypotheses, and stable multi-start NMF metagene programs.
- Separation of exploratory patterns from inferential claims and preservation of the biological sampling unit.

Representative modules include `expression-qc`, `differential-expression`, `enrichment-analysis`, `network-analysis`, `ddr-coexpression-hypothesis-network`, and `metagene-factorization-nmf`.

## Single-Cell Foundations

- Strict project-specific handling of H5AD, 10x HDF5, Matrix Market, and Seurat v5 inputs.
- Raw-count preservation, QC, normalization, feature selection, scaling, dimensionality reduction, neighbourhood graphs, clustering, and stability review in Scanpy or Seurat workflows.
- Transparent per-cell count, detected-gene, mitochondrial-fraction, and threshold flags.

The principal modules are `single-cell-foundation-workflow` and `single-cell-qc`.

## Donor-Aware Inference And Integration

- Pseudobulk aggregation by biological sample and cell type with estimability, confounding, replication, outlier, and sensitivity checks.
- Project-specific edgeR, DESeq2, or limma-voom contrasts using independent biological replicates.
- Harmony, Scanorama, and BBKNN benchmarking against an unchanged baseline, with batch mixing balanced against biological-label preservation.
- scVI and scANVI modelling with baseline comparison, held-out-label validation, unknown-label retention, and model reload checks.

These capabilities are implemented by `single-cell-donor-inference`, `single-cell-batch-integration`, and `single-cell-generative-modeling`.

## Annotation, Communication, And Dynamics

- SingleR-based reference annotation with feature-namespace alignment, score and pruning review, cluster consensus, positive and negative marker contracts, Cell Ontology constraints, and unknown-state retention.
- LIANA, CellPhoneDB, CellChat, and NicheNet workflows that preserve biological samples and compare interaction support across replicates.
- scVelo dynamical modelling, velocity graphs, pseudotime, and latent time validated against independent time, root, and terminal anchors.

These capabilities are implemented by `single-cell-reference-annotation`, `single-cell-communication`, and `single-cell-trajectory-velocity`.

## Quality Gates And Limits

Cells are never substituted for independent condition-level replicates. Integration is rejected when it erases biological structure or leaks labels. Annotation conflicts remain unknown. Communication claims require sample-level support. Temporal interpretations are blocked when the required layers, anchors, or independent time evidence are absent.

The current registry does not yet expose dedicated modules for RNA+ATAC WNN, CITE-seq, MOFA+, peak calling, chromVAR, SCENIC/SCENIC+, or spatial transcriptomics. Such methods can be added through the same module contract, but they should not be presented as implemented until executable templates, compatibility evidence, and scientific quality gates are present.

## Typical Deliverables

Validated input inventories, QC reports, donor-aware statistical tables, integrated and annotated objects, sensitivity analyses, interaction and trajectory evidence, figure specifications, methods, result narratives, unresolved-state logs, and manuscript-ready analysis packages.
