# Professional Capabilities

Languages: [English](README.md) · [中文](README.zh-CN.md) · Project home: [中文](../../README.md) · [English](../../README.en.md)

Biomed Workbench organises capabilities around research questions. Once a user provides the scientific goal and data, the workbench combines suitable methods from evidence gathering and study design through analysis, result review, hypothesis revision, and research delivery.

## Data Scales And Research Objects

| Area | Questions it can address | Detailed guide |
| --- | --- | --- |
| Bulk sequencing | Inspect raw inputs, sample sheets, programs and references; analyse transcription, RNA processing, chromatin, protein binding, translation, nascent transcription, DNA methylation and three-dimensional genome organisation; and receive complete outputs from external workflows | [Bulk Sequencing](bulk-sequencing-assays.md) · [Sequencing Intake And Interoperability](sequencing-intake-and-interoperability.md) · [RNA Processing And Alternative Splicing](rna-processing-alternative-splicing.md) |
| Single-cell | Perform quality control, sample integration, cell annotation, trajectory analysis, multi-omics, bounded splicing-candidate analysis, sample-aware communication, secreted-signal activity, and cross-species comparison while preserving sample structure | [Universal And Single-Cell Analysis](omics-and-single-cell.md) · [Integration, Reference Mapping, And Cross-Species Analysis](single-cell-integration-reference-cross-species.md) · [Cell Communication And Secreted-Signal Activity](cell-communication.md) · [RNA Processing And Alternative Splicing](rna-processing-alternative-splicing.md) |
| Spatial omics | Connect expression, physical location, tissue images, cell-type projection, spatial regions, communication, and multi-section structure | [Trajectory And Spatial Analysis](trajectory-spatial-complete-analysis.md) |
| Molecular and structural biology | Connect sequence, protein interaction, chemistry, structure prediction, and molecular docking to testable hypotheses | [Molecular And Structural Biology](molecular-and-structural.md) |
| Quantitative image analysis | Obtain reviewable segmentation, colocalisation, trajectory, migration, and baseline-registration measurements from source or processed images | [Quantitative Image Analysis](quantitative-imaging.md) |
| Clinical and experimental research | Analyse cohorts, experimental measurements, time courses, survival outcomes, pharmacology, and microbiology data | [Clinical And Experimental Research](clinical-and-experimental.md) |

## Project-Wide Support

| Area | Questions it can address | Detailed guide |
| --- | --- | --- |
| Evidence and literature | Use literature and registered public databases to examine genetic association, expression, omics datasets, pharmacology, structure and mechanism, and determine what is established, disputed or missing | [Evidence And Literature](evidence-and-literature.md) · [Public Life-Science Evidence](public-research-evidence.md) |
| General analysis methods | Apply study design, statistics, enrichment, network analysis, and scientific review at appropriate data scales | [Universal And Single-Cell Analysis](omics-and-single-cell.md) |
| Scientific interpretation and research story | Correct biological interpretations from observed results, assign panels to discovery, context, mechanistic consistency, validation, boundary, or integration, and use the result to decide the next step | [Scientific Interpretation, Research Story, And Result Decisions](scientific-interpretation-and-storytelling.md) |
| Scientific figure standards and delivery | Apply common figure purpose, visual hierarchy, layout, source-data, export, and quality-review rules while retaining method-native plots | [Scientific Figure Standards And Delivery](scientific-figure-standards.md) |
| Academic writing and research delivery | Perform literature discovery and full-paper reading, manuscript and proposal writing, scholarly prose revision, statistics and data-availability review, journal positioning, citation verification, paper figures, peer-review response, presentations, and patent-related preparation | [Academic Writing, Publication, And Translation](publication-and-translation.md) · [NSFC Proposal Support](nsfc-proposal-writing.md) · [Journal Standards](../journal-standards.md) |

## How Writing Connects To The Research

The workbench does not reduce writing to final-stage polishing. Publication identity, full-text locations, project facts, analysis results, figures, and citations first become a reviewable writing basis. Evidence is reordered by the scientific question, declared dependencies and its role in the argument rather than upload or method order. Manuscript structure, paragraphs, and proposal arguments are built from that record. Revision separately checks biomedical expression, content preservation, statistical reporting, data availability, and target-journal requirements. Final writing produces an HTML reading page with direct evidence and literature links and reopens it before delivery. Peer review then connects each editor or reviewer point to the response, real revision, and manuscript location. Figures, presentations, and patent-related material reuse reviewed project evidence while retaining their distinct delivery requirements.

Users may request one part of this process or ask the workbench to progress from literature and project data to a complete manuscript. See [Academic Writing, Publication, And Translation](publication-and-translation.md) for tasks, inputs, and deliverables, and [Using Biomed Workbench](../using-biomed-workbench.md) for natural-language examples.

## How Capabilities Are Combined

A focused question may need one database or one analysis. A complex project can connect several areas: study-design and data-quality checks, differential analysis, pathway and network interpretation, structural evidence, publication figures, and manuscript preparation.

Independent work can proceed in parallel, while analyses that depend on upstream results are performed in sequence. Each step records the data, method, quality review, and implications for what comes next, preserving the scientific logic as a project grows.

Complex questions are not routed by word similarity alone. The workbench first resolves assay, measurement target, control, normalisation, and biological relation, then builds independent analysis branches followed by an integration decision. A “secondary transcriptional effect”, for example, is not treated as RNA secondary structure; multi-omics, R-loop, protein-interaction, and RNA-processing evidence can occupy distinct branches before addressing direct action versus downstream consequence together.

An established project can first receive a read-only inventory of figures, plot data, analysis scripts, renderers, and captions. Formal relations are created only after researcher confirmation. The routine view shows the scientific question, main observation, interpretation boundary, current progress, and next decision; complete environment, parameter, and file provenance appears when needed.

## Current Coverage

The registry currently contains **223 independently discoverable modules**. Each module is a versioned scientific contract, while the public maturity page separately distinguishes contract-only methods, controlled execution, exact public-case validation, and results formally included in a current project. See [Capability Maturity](../maturity.md) and [Public-Data Cases](../cases/README.md) for observed status.

Bulk coverage includes RNA-seq and RNA-processing/alternative-splicing analysis; ChIP-seq, CUT&RUN, and CUT&Tag; several R-loop assays; RIP-seq, CLIP-family methods, and LACE-seq; Ribo-seq; GRO-seq, PRO-seq, TT-seq, and NET-seq; ATAC-seq and DNase-seq; WGBS, RRBS, and EM-seq; several three-dimensional genome assays; and MeRIP-seq/m6A-seq.

The assay, target, antibody, control, specificity treatment, and normalisation strategy are recorded separately. For example, CUT&Tag is the assay, S9.6 describes the target or antibody, an exogenous reference is a normalisation option, and RNase H treatment provides specificity evidence. They are not presented as peer assay classes.

Sequencing inputs first undergo file, sample-pairing, program and reference-resource checks. After an external workflow returns, only a complete run package with reloadable outputs, matching file identities and a recorded analysis environment proceeds to result review. Single-cell and spatial capabilities retain platform- and method-specific requirements. General methods provide study design, statistics, enrichment, networks, and result review across appropriate data scales. Review leads with observations, effect magnitude, uncertainty and experimental unit, then tests whether the conclusion exceeds the design, omits negative findings or lacks a next step that can distinguish competing explanations. Scientific figures are governed as project-wide support: typography, strokes, colour, legends, annotations, layout, source data, and export checks apply across research areas without replacing method-native diagnostics or quantitative image analysis. Publication and translation capabilities connect reviewed evidence, figures, citations, and prose while preserving the relationship among manuscript revisions and reviewer responses. Journal-specific guidance records the version and review date of the requirements used and treats official journal and publisher pages as authoritative for scope, article types, and submission requirements.

## Interpreting Result Boundaries

The workbench distinguishes data availability from adequacy, technical replicates from independent biological samples, association from causation, a database record from biological interpretation, prediction confidence from experimental validation, and completed computation from a supported scientific conclusion.

When required inputs, compatible software, or quality evidence are missing, the affected conclusion remains unresolved. Method developers can continue to [Architecture And Extension](../architecture.md).
