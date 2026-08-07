# Cross-Scale And Single-Cell Analysis

Languages: [English](omics-and-single-cell.md) · [中文](omics-and-single-cell.zh-CN.md)

## Scientific Role

This capability area coordinates sequencing data from input and design validation through statistical analysis, biological interpretation, hypothesis revision, and publication delivery. The workbench treats biological replication, immutable raw measurements, reference identity, and observed output checks as first-class requirements.

## Research Scale And Method Classification

The workbench first assigns a primary research scale—bulk, single-cell, spatial,
or universal—and then records measurement family, assay, biological target,
controls and normalization as separate dimensions. These are not one flat
taxonomy. Bulk assay coverage is maintained in the dedicated
[bulk sequencing assay guide](bulk-sequencing-assays.md); this document focuses
on universal foundations and the single-cell program.

## Universal Sequencing And Statistical Program

For broad sequencing, expression, variant, motif, NMF, or multi-measurement requests, the workbench stages reusable work from data profiling and read-level QC to alignment, sorting, alignment qualification, variant or interval handling, secondary synthesis, and publication-facing interpretation. Assay-specific inference remains in its assay module. Independent branches can run in parallel, but downstream modules receive explicit dependencies when they rely on QC, aligned records, filtered intervals, peak calls, expression matrices, or admitted statistical outputs.

This keeps FASTQ, BAM/CRAM, VCF, BED, count matrices, peak sets, motif resources, NMF programs, and gene-set outputs under one interface without pretending that their formats or tools are interchangeable. Each method states its accepted files, version range, required metadata, quality checks, and unresolved project inputs.

## Unified Single-Cell Research Program

For broad single-cell or single-cell multi-omics questions, Biomed Workbench does not require users to select from a menu of tools. It turns the objective into a staged research plan that states the inputs, outputs, software conditions, quality checks, unresolved questions, and the boundary between planning and observed evidence.

The staged plan is organized as a scientific program rather than a flat script list:

1. Droplet and ambient-RNA evidence from raw and filtered counts.
2. Foundation object construction, input-format validation, raw-count preservation, QC, normalization, HVG selection, PCA, neighbourhood graphs, embeddings, and clustering.
3. Doublet detection and barcode/cell-accounting review.
4. Batch integration, generative modelling, paired multi-omics integration, and single-cell ATAC regulatory preparation when requested.
5. Marker discovery, reference or atlas annotation, ontology constraints, confidence review, and unknown-state retention.
6. Donor-aware pseudobulk, mixed-model, longitudinal, composition, and complex experimental-design inference.
7. Communication, trajectory, RNA velocity, topology, regulatory-network, and spatial evidence with sample-level and directionality gates.
8. Fate mapping, RegVelo regulatory velocity, hypothesis revision, and manuscript or response-oriented delivery modules when publication work is part of the objective.

A plan becomes project evidence only after the workbench inspects the user's real files, records the software and parameters used, runs the analysis, reopens the outputs, and completes quality review.

## Sequencing And Genomic Foundations

- Read-level quality assessment with FastQC and fastp, cross-sample aggregation with MultiQC, and declared-reference contamination screening.
- BWA-MEM alignment, samtools alignment qualification, coordinate sorting and indexing.
- Genomic coordinate conversion with declared source and target assemblies and explicit accounting of mapped, split, and unmapped records; followed by build-matched BED interval overlap where appropriate.
- Assembly-to-reference alignment with a declared minimap2 preset, FASTA and PAF reload, and record-level coverage accounting; alignment is kept separate from variant, haplotype, synteny, or orthology inference.
- BGZF and tabix VCF handling, explicit variant filtering, multi-sample concordance, and callable-territory-aware tumour mutation burden.
- Bulk ChIP-seq, CUT&RUN, and CUT&Tag MACS3 peak calling with assay-specific control policy, peak-shape declaration, output reload, and no fallback peak set; independent known-PWM enrichment with a declared background and FDR adjustment.
- Strict single-resolution `.cool` contact-map extraction for explicitly typed enhancer and promoter intervals, preserving raw cis counts and descriptive distance-stratified baselines without calling loops or assigning regulation.
- SuSiE-RSS fine-mapping for independently selected GWAS loci with pre-harmonized summary statistics, exact ordered ancestry-compatible LD, fixed model complexity, convergence checks, credible-set reload, and explicit non-causal interpretation boundaries.
- Group-held-out RR-BLUP genomic prediction with frozen biological folds, training-test isolation, fold-level reload, and no causal or breeding-value claim beyond observed held-out performance.
- `msprime` coalescent simulation of a predeclared one-population constant, bottleneck, or expansion scenario for calibration and design, with parameter, seed, tree-sequence, VCF, and version provenance; simulation remains separate from empirical demographic inference.
- ARCHS4 public tissue or cell-line expression context with field-level CSV validation, hierarchy-row accounting, ordering by median, and explicit separation from project-specific differential expression or specificity claims.

Detailed guidance is available for [coordinate conversion](genome-coordinate-liftover.md), [bulk chromatin peak calling](bulk-chromatin-peak-calling.md), [known motif enrichment](sequence-motif-enrichment.md), [chromatin contact evidence](cool-contact-evidence.md), [GWAS fine-mapping](gwas-susie-fine-mapping.md), [genomic prediction](rrblup-genomic-prediction.md), [demographic simulation](msprime-demographic-simulation.md), and [ARCHS4 expression context](archs4-expression-evidence.md).

## Bulk Expression And Systems Analysis

- Expression-matrix validation and sample-level quality assessment.
- Differential expression with explicit design and statistical outputs.
- Gene-set overrepresentation, biological network summaries, FDR-controlled coexpression hypotheses, and stable multi-start NMF metagene programs.
- Separation of exploratory patterns from inferential claims and preservation of the biological sampling unit.

## Single-Cell Foundations

- Strict project-specific handling of H5AD, 10x HDF5, Matrix Market, and Seurat v5 inputs.
- Raw-count preservation, QC, normalization, feature selection, scaling, dimensionality reduction, neighbourhood graphs, clustering, and stability review in Scanpy or Seurat workflows.
- EmptyDrops, SoupX, and CellBender droplet and ambient-RNA evidence with barcode reconciliation and immutable source counts.
- [Scrublet and scDblFinder doublet detection](doublet-detection.md) by capture
  library, with source-preserving execution, withheld-label evaluation, and method
  disagreement retained for review.
- Transparent per-cell count, detected-gene, mitochondrial-fraction, and threshold flags.

See the [droplet calling and ambient-RNA guide](droplet-decontamination.md) for the use of emptyDrops, SoupX, and CellBender and for handling disagreement among methods.

## Donor-Aware Inference And Integration

- Pseudobulk aggregation by biological sample and cell type with estimability, confounding, replication, outlier, and sensitivity checks.
- Project-specific edgeR, DESeq2, or limma-voom contrasts using independent biological replicates.
- Longitudinal dream models with subject random effects, linear and spline hypotheses, variance decomposition, repeated-measure composition models, propeller sensitivity, and multi-reference additive-log-ratio evidence.
- Harmony, Scanorama, and BBKNN benchmarking against an unchanged baseline, with batch mixing balanced against biological-label preservation.
- scVI and scANVI modelling with baseline comparison, held-out-label validation, unknown-label retention, and model reload checks.

See [donor-aware complex inference](complex-inference.md), [classical batch integration](batch-integration.md), and [scVI/scANVI generative modelling](generative-modeling.md) for method comparison, label isolation, and cases where no method should be selected.

## Annotation, Communication, And Dynamics

- Count-backed marker discovery with predeclared discovery and held-out sample roles, partition-specific detection fractions, effect sizes, independent direction validation, descriptive cell-level significance boundaries, and no automatic conversion of markers into labels.
- CellTypist, Azimuth, popV, SingleR, and scANVI annotation with feature-namespace alignment, method-specific confidence, score and pruning review, explicit canonical-label and Cell Ontology mapping, cross-method weighted consensus, expert disagreement, and unknown-state retention.
- LIANA, CellPhoneDB, CellChat, and NicheNet workflows that analyze samples independently, retain method-native significance, and require predeclared independently significant sample support before replication.
- scVelo dynamical modelling; RegVelo 0.4.2 GRN-informed velocity, gene-resolved latent time, regulatory-constraint comparison, and perturbation hypotheses; CellRank 2.3.2 velocity, connectivity-weight, pseudotime, and real-time GPCCA fate mapping; moscot optimal transport; Slingshot and Monocle3 topology; and tradeSeq lineage tests validated against independent time, root, branch, and terminal anchors.

See [marker discovery](marker-discovery.md), [conservative reference annotation](reference-annotation.md), [sample-aware communication](cell-communication.md), [direction-validated RNA velocity](trajectory-velocity.md), [RegVelo](regulatory-velocity.md), [fate mapping](fate-mapping.md), and [lineage topology](trajectory-topology.md).

## Multimodal, Regulatory, And Spatial Analysis

- RNA+ATAC and RNA+ADT/CITE-seq weighted-nearest-neighbour integration with cell-specific modality weights, weighted graphs, clusters, and source-count preservation.
- MOFA+ factors, view-specific feature loadings, and variance explained across two or more paired modalities.
- MACS3 peak calling from barcode-accounted fragments, sequence-backed motif matching, GC/accessibility-matched chromVAR, and Signac peak-to-gene links.
- pySCENIC GRNBoost2, cisTarget motif pruning, regulon construction, and AUCell activity; SCENIC+ gene- and region-based eRegulon scoring with explicit motif and region-gene evidence.
- H5AD and SpatialData Zarr input, image and shape provenance, sample-isolated spatial graphs, neighbourhood enrichment, per-sample co-occurrence, global and sample-level Moran tests, replicated spatial genes, and exploratory expression-spatial domains.

See the [multimodal integration guide](multimodal-integration.md) for paired-cell requirements, method-specific evidence, and the public 10x PBMC Multiome case.
See the [single-cell ATAC regulatory guide](atac-regulatory.md) for fragment
accounting, MACS3, motifmatchr, chromVAR, LinkPeaks, and their separate evidence
boundaries.
See the [regulatory-network guide](regulatory-network.md) for GRNBoost2,
cisTarget, AUCell, SCENIC+, and the distinction between coexpression programs
and motif-pruned regulons.
See the [spatial-analysis guide](spatial-analysis.md) for sample-isolated
graphs, Squidpy statistics, Moran evidence, exploratory domains, and
single-sample versus replicated claim boundaries.

## Quality Gates And Limits

Cells and spatial spots are never substituted for independent condition-level replicates. Integration is rejected when it erases biological structure or leaks labels. Annotation conflicts remain unknown. Communication and spatial-gene claims require sample-level support. Temporal interpretations are blocked when required layers, anchors, prior-network provenance, baseline comparisons, or independent time evidence are absent. Coexpression, motif support, peak-to-gene association, eRegulon concordance, and spatial autocorrelation are not reported as causal regulation without independent evidence.

The validated templates and planted-signal fixtures establish executable method coverage, compatibility, source preservation, and scientific gate behaviour. They do not replace project-specific checks of chemistry, tissue architecture, references, genome build, motif resources, experimental design, model sensitivity, biological replication, or external validation.

## Typical Deliverables

Validated input inventories, QC reports, donor-aware statistical tables, integrated and annotated objects, sensitivity analyses, interaction and trajectory evidence, figure specifications, methods, result narratives, unresolved-state logs, and manuscript-ready analysis packages.
