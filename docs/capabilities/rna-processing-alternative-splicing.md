# RNA Processing And Alternative-Splicing Analysis

Languages: [English](rna-processing-alternative-splicing.md) · [中文](rna-processing-alternative-splicing.zh-CN.md)

RNA processing is not one statistical problem. Local splice events, exon usage, transcript usage, full-length isoforms, 3′ single-cell junction signal, and spliced/unspliced kinetics measure different objects. The workbench first determines which question the data can answer, then selects one primary analysis and one orthogonal validation that could change the scientific decision.

## Choosing The Analysis Branch

| Data and question | Default primary analysis | Intended use | Boundary |
| --- | --- | --- | --- |
| Replicated short-read bulk RNA-seq; classical local events | [rMATS-turbo](https://github.com/Xinglab/rmats-turbo) | Sample-level changes in SE, A5SS, A3SS, MXE and RI with counts, PSI, delta PSI, P values and FDR | A local event is not a full-length isoform switch |
| Novel junctions, incomplete annotation, or complex local splicing | [MAJIQ/VOILA](https://majiq.biociphers.org/) or [LeafCutter](https://github.com/davidaknowles/leafcutter) | Complex splice graphs, unannotated junctions, or intron-excision clusters | These replace the primary method only when novel or complex events matter; they are not added simply to increase method count |
| Relative transcript usage | Salmon/tximport → [DRIMSeq](https://bioconductor.org/packages/release/bioc/html/DRIMSeq.html) → [stageR](https://bioconductor.org/packages/release/bioc/html/stageR.html) | Gene-level screening followed by transcript-level confirmation, with design covariates where justified | DTU is neither differential gene expression nor automatically a classical splice event |
| Exon usage | [DEXSeq](https://bioconductor.org/packages/release/bioc/html/DEXSeq.html) | Changes in counting bins relative to other bins from the same gene | A named splicing mechanism requires junction or transcript evidence |
| Full-length single-cell RNA | [BRIE2](https://brie.readthedocs.io/en/latest/quick_start.html), SpliZ, or scQuint | Cell-state-associated event or splice-site usage while retaining sample structure | Cells are not biological replicates for a condition contrast |
| 10x 3′ single-cell or single-nucleus RNA | Sample-level junction candidate screen | Determine whether existing BAMs contain recurrent junction evidence worth validating | Position bias, nuclear pre-mRNA, and sparse coverage limit formal AS claims; intronic/exonic signal and velocity layers are insufficient |
| Nanopore or PacBio long-read RNA | [FLAIR](https://flair.readthedocs.io/en/latest/) | Alignment, splice-site correction, shared transcriptome collapse, sample-wise quantification and isoform comparison | Novel isoforms still require read support, replicate consistency, short-read junction evidence or targeted validation |

## Design And Parameter Selection

The biological sample, condition, pairing, batch, library layout, strandedness, read length, reference genome and annotation release are frozen before execution.

- rMATS `--readLength` is measured from the admitted libraries; `--variable-read-length` is explicit, `--libType` records strandedness, `--paired-stats` is limited to a correctly ordered paired design, `--novelSS` is used only for an unannotated splice-site question, and `--cstat` defines the effect-size null rather than a post hoc significance filter.
- DRIMSeq gene, transcript, sample-prevalence and usage-proportion filters are declared before result review. stageR controls the two-stage gene-screening and transcript-confirmation family.
- A 3′ droplet screen requires per-sample event and junction coverage, within-condition PSI consistency, state matching, and threshold sensitivity. It remains a candidate branch until replicated bulk RNA-seq or junction-specific RT-PCR supports the event.
- Long-read analyses build a shared cross-sample isoform reference before sample-wise quantification; separately collapsed sample references are not compared as if they were identical feature universes.

## Standard Outputs

The short-read event branch retains native rMATS JC and JCEC files and creates a normalized event table, execution/version report, parameter and file digests, and a three-part vector overview:

1. tested and threshold-passing events by event class;
2. the joint distribution of delta PSI and multiplicity-adjusted evidence;
3. replicate unit, direction, counting convention, and claim boundary.

Consequential events additionally require a gene model or splice graph, biological-sample PSI, junction coverage, a representative sashimi or VOILA view, and a validation design. Plot-ready data are retained and group direction is written into the caption.

## Cross-Assay Integration

Each event enters the scientific evidence map with a stable event ID, gene ID, coordinates, direction, sample-level usage and source artifact. Differential expression, RBP binding, IP–MS, chromatin occupancy, R-loop, ATAC and conservation can link to the same gene or event while retaining distinct evidentiary roles. Co-occurrence creates a multi-assay candidate, not a direct RNA-processing mechanism. Direct causality remains unresolved until event-specific perturbation, direct binding, concordant functional validation, and competing explanations have been addressed.

## Current Acceptance Scope

The packaged rMATS branch has executed the official rMATS-turbo 4.4.0 skipped-exon test in an isolated local environment, then independently re-executed, reloaded and rendered the result through the workbench adapter. The sample-level junction and evidence-integration branches pass a controlled four-biological-sample case. Long-read, BRIE2, MAJIQ, LeafCutter, DEXSeq, and DRIMSeq–stageR are included in method selection, input requirements and claim boundaries, but are not executable branches of this module yet. They are not counted as executable capability before their parameterized implementations and representative runs exist.

Primary references include the rMATS [official parameter and output contract](https://github.com/Xinglab/rmats-turbo/blob/master/README.md), the [MAJIQ v2 paper](https://www.nature.com/articles/s41467-023-36585-y), the LeafCutter [Nature Genetics paper](https://doi.org/10.1038/s41588-017-0004-9), the DEXSeq [Genome Research paper](https://doi.org/10.1101/gr.133744.111), the SUPPA2 [Genome Biology paper](https://doi.org/10.1186/s13059-018-1417-1), the [BRIE2 paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC8393734/), the FLAIR [Nature Communications paper](https://doi.org/10.1038/s41467-020-15171-6), and the 10x Genomics [intronic/antisense-read technical note](https://www.10xgenomics.com/support/universal-three-prime-gene-expression/documentation/steps/sequencing/interpreting-intronic-and-antisense-reads-in-10-x-genomics-single-cell-gene-expression-data).
