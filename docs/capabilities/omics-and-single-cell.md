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
- EmptyDrops, SoupX, and CellBender droplet and ambient-RNA evidence with barcode reconciliation and immutable source counts.
- Scrublet and scDblFinder sample-aware doublet evidence with method disagreement retained for review.
- Transparent per-cell count, detected-gene, mitochondrial-fraction, and threshold flags.

The principal modules are `single-cell-foundation-workflow`, `single-cell-qc`, `single-cell-droplet-decontamination`, and `single-cell-doublet-detection`.

## Donor-Aware Inference And Integration

- Pseudobulk aggregation by biological sample and cell type with estimability, confounding, replication, outlier, and sensitivity checks.
- Project-specific edgeR, DESeq2, or limma-voom contrasts using independent biological replicates.
- Longitudinal dream models with subject random effects, linear and spline hypotheses, variance decomposition, repeated-measure composition models, propeller sensitivity, and multi-reference additive-log-ratio evidence.
- Harmony, Scanorama, and BBKNN benchmarking against an unchanged baseline, with batch mixing balanced against biological-label preservation.
- scVI and scANVI modelling with baseline comparison, held-out-label validation, unknown-label retention, and model reload checks.

These capabilities are implemented by `single-cell-donor-inference`, `single-cell-complex-inference`, `single-cell-batch-integration`, and `single-cell-generative-modeling`.

## Annotation, Communication, And Dynamics

- Count-backed marker discovery with detection fractions, effect sizes, cross-sample direction review, and no automatic conversion of markers into labels.
- CellTypist, Azimuth, popV, and SingleR annotation with feature-namespace alignment, method-specific confidence, score and pruning review, marker contracts, Cell Ontology constraints, expert disagreement, and unknown-state retention.
- LIANA, CellPhoneDB, CellChat, and NicheNet workflows that preserve biological samples and compare interaction support across replicates.
- scVelo dynamical modelling, CellRank GPCCA fate mapping, moscot optimal transport, Slingshot and Monocle3 topology, and tradeSeq lineage tests validated against independent time, root, branch, and terminal anchors.

These capabilities are implemented by `single-cell-marker-discovery`, `single-cell-atlas-annotation`, `single-cell-reference-annotation`, `single-cell-communication`, `single-cell-trajectory-velocity`, `single-cell-fate-mapping`, and `single-cell-trajectory-topology`.

## Multimodal, Regulatory, And Spatial Analysis

- RNA+ATAC and RNA+ADT/CITE-seq weighted-nearest-neighbour integration with cell-specific modality weights, weighted graphs, clusters, and source-count preservation.
- MOFA+ factors, view-specific feature loadings, and variance explained across two or more paired modalities.
- MACS3 peak calling from barcode-accounted fragments, sequence-backed motif matching, GC/accessibility-matched chromVAR, and Signac peak-to-gene links.
- pySCENIC GRNBoost2, cisTarget motif pruning, regulon construction, and AUCell activity; SCENIC+ gene- and region-based eRegulon scoring with explicit motif and region-gene evidence.
- H5AD and SpatialData Zarr input, image and shape provenance, sample-isolated spatial graphs, neighbourhood enrichment, per-sample co-occurrence, global and sample-level Moran tests, replicated spatial genes, and exploratory expression-spatial domains.

These capabilities are implemented by `single-cell-multimodal-integration`, `single-cell-atac-regulatory`, `single-cell-regulatory-network`, and `single-cell-spatial-analysis`.

## Quality Gates And Limits

Cells and spatial spots are never substituted for independent condition-level replicates. Integration is rejected when it erases biological structure or leaks labels. Annotation conflicts remain unknown. Communication and spatial-gene claims require sample-level support. Temporal interpretations are blocked when required layers, anchors, or independent time evidence are absent. Coexpression, motif support, peak-to-gene association, eRegulon concordance, and spatial autocorrelation are not reported as causal regulation without independent evidence.

The validated templates and planted-signal fixtures establish executable method coverage, compatibility, source preservation, and scientific gate behaviour. They do not replace project-specific checks of chemistry, tissue architecture, references, genome build, motif resources, experimental design, model sensitivity, biological replication, or external validation.

## Typical Deliverables

Validated input inventories, QC reports, donor-aware statistical tables, integrated and annotated objects, sensitivity analyses, interaction and trajectory evidence, figure specifications, methods, result narratives, unresolved-state logs, and manuscript-ready analysis packages.
