# Professional Capabilities

Languages: [English](README.md) · [中文](README.zh-CN.md) · Project home: [中文](../../README.md) · [English](../../README.en.md)

Biomed Workbench organises capabilities around research questions. Once a user provides the scientific goal and data, the workbench combines suitable methods from evidence gathering and study design through analysis, result review, hypothesis revision, and research delivery.

## Research Areas

| Area | Questions it can address | Detailed guide |
| --- | --- | --- |
| Evidence and literature | Determine what is established, disputed, missing, or outdated | [Evidence And Literature](evidence-and-literature.md) |
| Bulk sequencing | Analyse transcription, chromatin, protein binding, translation, nascent transcription, DNA methylation, and three-dimensional genome organisation in pooled samples | [Bulk Sequencing](bulk-sequencing-assays.md) |
| Single-cell | Perform quality control, sample integration, cell annotation, trajectory analysis, multi-omics, and cross-species comparison while preserving sample structure | [Universal And Single-Cell Analysis](omics-and-single-cell.md) · [Integration, Reference Mapping, And Cross-Species Analysis](single-cell-integration-reference-cross-species.md) |
| Spatial omics | Connect expression, physical location, tissue images, cell-type projection, spatial regions, communication, and multi-section structure | [Trajectory And Spatial Analysis](trajectory-spatial-complete-analysis.md) |
| General analysis methods | Apply study design, statistics, enrichment, network analysis, figure production, and scientific review at appropriate data scales | [Universal And Single-Cell Analysis](omics-and-single-cell.md) |
| Molecular and structural biology | Connect sequence, protein interaction, chemistry, structure prediction, and molecular docking to testable hypotheses | [Molecular And Structural Biology](molecular-and-structural.md) |
| Imaging and scientific visualisation | Quantify, segment, colocalise, and track image data and create figures that remain faithful to the measurements | [Imaging And Scientific Visualisation](imaging-and-visualization.md) |
| Clinical and experimental research | Analyse cohorts, experimental measurements, time courses, survival outcomes, pharmacology, and microbiology data | [Clinical And Experimental Research](clinical-and-experimental.md) |
| Academic writing and research delivery | Perform literature discovery and full-paper reading, manuscript and proposal writing, scholarly prose revision, statistics and data-availability review, journal positioning, citation verification, paper figures, peer-review response, presentations, and patent-related preparation | [Academic Writing, Publication, And Translation](publication-and-translation.md) · [Journal Standards](../journal-standards.md) |

## How Writing Connects To The Research

The workbench does not reduce writing to final-stage polishing. Publication identity, full-text locations, project facts, analysis results, figures, and citations first become a reviewable writing basis. Manuscript structure, paragraphs, and proposal arguments are built from that record. Revision then checks scholarly expression, content preservation, statistical reporting, data availability, and target-journal requirements separately. Peer review connects each editor or reviewer point to the response, real revision, and manuscript location. Figures, presentations, and patent-related material reuse reviewed project evidence while retaining their distinct delivery requirements.

Users may request one part of this process or ask the workbench to progress from literature and project data to a complete manuscript. See [Academic Writing, Publication, And Translation](publication-and-translation.md) for tasks, inputs, and deliverables, and [Using Biomed Workbench](../using-biomed-workbench.md) for natural-language examples.

## How Capabilities Are Combined

A focused question may need one database or one analysis. A complex project can connect several areas: study-design and data-quality checks, differential analysis, pathway and network interpretation, structural evidence, publication figures, and manuscript preparation.

Independent work can proceed in parallel, while analyses that depend on upstream results are performed in sequence. Each step records the data, method, quality review, and implications for what comes next, preserving the scientific logic as a project grows.

## Current Coverage

The registry currently contains **208 independently discoverable modules**. Registration means that a method's purpose, inputs, outputs, and conditions of use are defined; it does not mean that every module has completed real-world acceptance on every kind of data. See [Capability Maturity](../maturity.md) and [Public-Data Cases](../cases/README.md) for observed status.

Bulk coverage includes RNA-seq; ChIP-seq, CUT&RUN, and CUT&Tag; several R-loop assays; RIP-seq, CLIP-family methods, and LACE-seq; Ribo-seq; GRO-seq, PRO-seq, TT-seq, and NET-seq; ATAC-seq and DNase-seq; WGBS, RRBS, and EM-seq; several three-dimensional genome assays; and MeRIP-seq/m6A-seq.

The assay, target, antibody, control, specificity treatment, and normalisation strategy are recorded separately. For example, CUT&Tag is the assay, S9.6 describes the target or antibody, an exogenous reference is a normalisation option, and RNase H treatment provides specificity evidence. They are not presented as peer assay classes.

Single-cell and spatial capabilities retain platform- and method-specific requirements. General methods provide study design, statistics, enrichment, networks, figure production, and result review across appropriate data scales. Publication and translation capabilities connect reviewed evidence, figures, citations, and prose while preserving the relationship among manuscript revisions and reviewer responses. Journal-specific guidance records the version and review date of the requirements used and treats official journal and publisher pages as authoritative for scope, article types, and submission requirements.

## Interpreting Result Boundaries

The workbench distinguishes data availability from adequacy, technical replicates from independent biological samples, association from causation, a database record from biological interpretation, prediction confidence from experimental validation, and completed computation from a supported scientific conclusion.

When required inputs, compatible software, or quality evidence are missing, the affected conclusion remains unresolved. Method developers can continue to [Architecture And Extension](../architecture.md).
