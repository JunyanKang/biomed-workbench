<h1 align="center">Biomed Workbench</h1>

<p align="center"><strong>Biomedical research that begins with a question and resolves into reviewable evidence</strong></p>

<p align="center">
  Study design · Data analysis · Scientific review · Evidence traceability · Publication delivery
</p>

<p align="center">
  <a href="README.md">中文</a> · <a href="README.en.md">English</a>
</p>

<p align="center">
  <a href="LICENSE"><img alt="Apache-2.0 license" src="https://img.shields.io/badge/license-Apache--2.0-365B73"></a>
  <img alt="215 registered scientific modules" src="https://img.shields.io/badge/registered%20modules-215-4E8B86">
</p>

<p align="center">
  <a href="#start-a-project">Start a project</a> ·
  <a href="docs/capabilities/README.md">Capability map</a> ·
  <a href="#academic-writing-and-research-delivery">Academic writing and research delivery</a> ·
  <a href="docs/scientific-evidence-map.md">Evidence map</a> ·
  <a href="docs/releases/README.md">Release notes</a>
</p>

<p align="center">
  <img src="assets/readme/biomed-workbench-editorial-hero.png" width="100%" alt="Conceptual path from biomedical research inputs through analysis and scientific review to evidence, figures and manuscripts">
</p>

<p align="center"><sub>Conceptual illustration: relationships among research inputs, analysis, review, evidence organization and delivery. The data and plots are schematic, not experimental results.</sub></p>

Biomed Workbench connects biomedical study design, data analysis, and research delivery. It keeps research questions, real data, method choices, analysis results, scientific review, and downstream decisions in one traceable record, so that an analysis can become a dependable basis for the next research decision.

Its central role is supervised method selection and evidence organisation for complex projects: interpret the assay, target, controls, normalisation, and biological relation first; choose the smallest analysis set that can answer the question; then advance genuinely reviewed results into figures and prose.

Researchers describe the objective, study design, and available data in natural language. The workbench checks inputs and method fit, selects suitable capabilities, runs available workflows, reopens the result files, and limits conclusions to what the observed evidence can support.

| Study design | Evidence traceability | Research delivery |
| --- | --- | --- |
| Define the question, experimental unit, hypothesis and decision criterion before selecting methods. | Connect data, parameters, programs, figures, captions, references and review. | Extend analysis tables and figures into bilingual reports, manuscripts, responses and presentations. |

## How a project moves forward

| 01 · Define | 02 · Analyze | 03 · Review | 04 · Decide |
| --- | --- | --- | --- |
| State the biological question, experimental unit, available evidence, competing hypotheses, and success criteria. | Select one primary analysis and one necessary orthogonal validation per question; record versions, parameters, environment, and outputs. | Examine technical quality, statistical robustness, biological interpretation, and claim boundaries separately. | Classify results as formal, candidate, sensitivity, or deprecated, then choose the next step. |

The end of a computation is not the end of an analysis. A result becomes current project evidence only after quality checks, output review, and scientific assessment. Conflicting, failed, and excluded routes remain in project history so later decisions can be reconstructed.

Long-running projects also freeze the sample sheet, reference releases, cell annotation, replicate unit, thresholds, colours, formal directories, and figure registry so result identity, captions, and file locations do not drift across analysis rounds. See [Project Locks, Analysis Selection, And Result Status](docs/project-governance.md).

## The scientific evidence map

The evidence map uses two readable levels instead of compressing every file relationship into one dense diagram:

1. the **project story** shows only consequential support, weakening, conflict and dependencies among data results and figures;
2. an **individual evidence record** expands preceding conclusions, current data, plot-ready data, analysis code, figure layout, final files, captions, interpretive sources, and DOI records.

File identity, version relationships, and content fingerprints travel with the map. Bilingual interpretation reports read the same checked source, keeping figures, tables, prose, and citations aligned instead of reconstructing their origins during writing. Read the full [Scientific Evidence Map](docs/scientific-evidence-map.md).

## Research and analysis coverage

The workbench currently contains **215 independently discoverable scientific modules**. This means that their purpose, inputs, outputs, and conditions of use are recorded; it does not mean that every module has been accepted across every dataset, species, or runtime. Exact execution scope and representative cases are recorded in the versioned [release notes](docs/releases/README.md), [maturity guide](docs/maturity.md), and [`reports/`](reports/).

The workbench uses a multidimensional classification: data analysis is organised by research object and scale, while general methods, evidence management, scientific figures, and academic writing are listed separately as project-wide support.

### Data scales and research objects

| Area | Representative capabilities |
| --- | --- |
| [Bulk sequencing](docs/capabilities/bulk-sequencing-assays.md) | bulk RNA-seq and [RNA processing/alternative splicing](docs/capabilities/rna-processing-alternative-splicing.md); ChIP-seq, CUT&RUN and CUT&Tag; R-loop mapping; RIP/eCLIP/LACE-seq; Ribo-seq; GRO/PRO/TT/NET-seq; ATAC-seq; methylation and 3D genome analysis |
| [Single-cell](docs/capabilities/single-cell-integration-reference-cross-species.md) | Quality control and annotation, batch and reference integration, multimodal integration, trajectories, velocity, regulatory analysis, [sample-aware splicing candidate analysis](docs/capabilities/rna-processing-alternative-splicing.md), cross-species mapping and evaluation |
| [Spatial](docs/capabilities/trajectory-spatial-complete-analysis.md) | Platform-aware structures and QC, tissue imaging and segmentation, domains, deconvolution and reference mapping, slice alignment, 3D coordinates and spatial communication |
| [Molecular and structural biology](docs/capabilities/molecular-and-structural.md) | Protein interaction networks, AlphaFold result intake and quality review, HADDOCK3 docking, structure comparison, binding assessment and network delivery |
| [Clinical and experimental research](docs/capabilities/clinical-and-experimental.md) | Cohorts, survival, biomarkers and quantitative assays; flow cytometry, qPCR, dose response, protein quantification, microbiology and animal studies |
| [Quantitative image analysis](docs/capabilities/quantitative-imaging.md) | Image inspection, segmentation, colocalisation, object tracking, migration measurements, and baseline registration with masks, object-level data, and measurement QC |

### Project-wide support

| Area | Representative capabilities |
| --- | --- |
| [Evidence and public databases](docs/capabilities/evidence-and-literature.md) | Literature and citation review; gene, variant, pathway, structure and clinical-trial evidence; source freshness and claim review |
| [Cross-scale methods](docs/capabilities/omics-and-single-cell.md) | Study and format validation, differential testing, DEqMS, GO/KEGG, GSEA, WGCNA, motifs, networks, and result review |
| [Scientific figure standards and delivery](docs/capabilities/scientific-figure-standards.md) | Project-wide rules for figure purpose, typography, strokes, colour, legends, statistical annotations, layout, source data, export formats, and rendered-output review |
| [Academic writing, publication, and translation](docs/capabilities/publication-and-translation.md) | Full-paper bilingual reading, academic and proposal writing, statistics and data-availability review, journal positioning, citation verification, peer-review response, patents, figures and presentations |

Explore the complete capability index: [中文](docs/capabilities/README.zh-CN.md) · [English](docs/capabilities/README.md)

## Academic Writing And Research Delivery

Writing is part of the research process, not a separate polishing step after analysis. The workbench first checks the research record, data, figures, and citations, then organises material for a manuscript, funding proposal, peer-review response, presentation, or patent-related technical package. Unsupported content remains an explicit gap, limitation, or hypothesis. NSFC applications use separate current-year profiles for Young C, Young B, Young A, General, Regional, Key and Major programmes, develop actual prose from the central question, hypothesis and section argument, and then complete nomenclature, mechanism-claim, citation and Word-delivery review.

| Stage | Supported work | Typical deliverables |
| --- | --- | --- |
| Literature and reading | Multi-source discovery, publication and citation-context verification, full-paper bilingual reading, terminology and figure location | Literature landscape, full-paper reader, source map, terminology ledger |
| Argument and first draft | Establish the research canon and claim–evidence relationships, plan the manuscript and section roles, draft papers or proposals | Manuscript sections, proposal rationale, Methods and Results text, author-input list |
| Language and content revision | Improve scholarly prose while checking preservation of numbers, results, equations, citations, terminology, structure, and claim strength | Revised text, change report, content-preservation review |
| Statistics and submission requirements | Review experimental units, replication, statistical reporting, data and code availability, journal fit, and article-type requirements | Statistical review, availability statement, journal recommendation, manuscript compliance review |
| Figures and peer review | Plan paper figures and captions, simulate review, and organise point-by-point responses and traceable revisions | Figure plan, reviewer report, response letter, response matrix, revision record |
| Presentations and translational delivery | Build and reopen real presentation files, and prepare source-grounded technical disclosures and patent-drafting materials | Presentation and QA report, technical disclosure, patent evidence and drafting package |

These capabilities can revise one passage in an existing manuscript or organise a full paper from literature and project evidence. NSFC work begins with multi-source discovery, full-text review of central papers, citation verification and project-relevant public-database evidence, then applies distinct Young C, Young B, Young A, General, Regional, Key or Major programme structures. Rationale, hypothesis, workflow, technical-route and preliminary-foundation figures have position-specific evidence and visual contracts and are delivered in editable form. See [Academic Writing, Publication, And Translation](docs/capabilities/publication-and-translation.md) for scope, inputs, and delivery boundaries, [NSFC proposal support](docs/capabilities/nsfc-proposal-writing.md) for programme-specific proposal checks, and [Journal Positioning And Manuscript Requirements](docs/journal-standards.md) for journal-specific guidance.

## How rigor enters the workflow

- **Experimental units come first.** Condition-level inference returns to donors, samples, animals, organoids or independently prepared specimens rather than treating cells or technical replicates as biological replication.
- **Analysis is limited by decision value.** Each scientific question defaults to one primary analysis and one orthogonal validation; a new method must state what it replaces or which new decision information it contributes.
- **Methods have conditions of use.** Inputs, applicable designs, adjustable parameters, compatible software, quality checks, and alternatives are stated explicitly.
- **Raw evidence stays separate from integrated representations.** Integration supports representation, mapping and visualization; differential inference returns to counts and statistical units appropriate to the design.
- **Results must be reopened.** Runtime versions, parameters, programs, and file checks travel with results; formal delivery reopens and checks the actual files.
- **Claim strength follows evidence strength.** Exploratory results remain exploratory, while public cases, real-service results and completion in the current user project are recorded separately.
- **Figures and prose share a source.** Plot-ready data, figures, captions, results text and DOI records derive from the same evidence-map version.

## Start a project

In Codex, say:

> Install the current release of [JunyanKang/biomed-workbench](https://github.com/JunyanKang/biomed-workbench). Verify the plugin identity, unified research entry, scientific-module registry and installed revision; preserve existing local changes; run the release-integrity checks; then reload the plugin.

After installation, open a new task and describe the research objective, study design, available data and expected deliverables. For example:

> Build a donor-aware single-cell and spatial research program from the raw data and sample design. Compare integration, annotation, deconvolution, trajectory and communication strategies, with method rationale, quality criteria, figure plans and downstream decision rules at every stage.

> Build a complete CUT&Tag workflow that treats target, antibody, internal reference, specificity treatment and normalization as design parameters. Complete peak, differential, enrichment, network and transcriptional-linkage analysis while preserving a reviewable evidence chain.

> Integrate literature, public databases, omics, protein-interaction and structural evidence around a candidate mechanism. Separate direct evidence, association, conflict and knowledge gaps, then propose the experiment most likely to change the current judgment.

> Use the project data, figures, analysis records, and references to establish claim–evidence relationships, then draft the manuscript structure, Results, and Discussion. Review the statistical reporting, citations, data availability, and target-journal requirements, and deliver a change report with unresolved author questions.

See [Using Biomed Workbench](docs/using-biomed-workbench.md) and [Installation](docs/installation.md).

## Using Biomed Workbench with other agents

Codex is currently the environment covered by the complete release-validation path. Other agents that support Agent Skills or local stdio MCP can read the same scientific entry and module registry, but each agent still needs its own verified support for file access, runtime management, external tools, result reloading and evidence delivery. See [Using Biomed Workbench with other agents](docs/agent-integration.md).

Another agent should not copy the Codex plugin-install request verbatim. Codex release information may remain present but unloaded in a full checkout. Each agent should connect through the skills or MCP mechanism it supports and state which parts of the workflow it can actually complete.

## Documentation

| Topic | 中文 | English |
| --- | --- | --- |
| Use and installation | [使用指南](docs/using-biomed-workbench.zh-CN.md) · [安装](docs/installation.zh-CN.md) | [Using the workbench](docs/using-biomed-workbench.md) · [Installation](docs/installation.md) |
| Scientific capabilities | [能力地图](docs/capabilities/README.zh-CN.md) · [公共案例](docs/cases/README.zh-CN.md) | [Capability map](docs/capabilities/README.md) · [Public cases](docs/cases/README.md) |
| Evidence and reproducibility | [项目锁定与结果状态](docs/project-governance.zh-CN.md) · [证据地图](docs/scientific-evidence-map.zh-CN.md) · [成熟度](docs/maturity.zh-CN.md) · [可复现性](docs/reproducibility.zh-CN.md) | [Project locks and result status](docs/project-governance.md) · [Evidence map](docs/scientific-evidence-map.md) · [Maturity](docs/maturity.md) · [Reproducibility](docs/reproducibility.md) |
| Data access | [公共数据库与凭据](docs/data-access-and-credentials.zh-CN.md) | [Data access and credentials](docs/data-access-and-credentials.md) |
| Writing and journals | [科研写作、发表与转化交付](docs/capabilities/publication-and-translation.zh-CN.md) · [国家自然科学基金申请书研究与写作](docs/capabilities/nsfc-proposal-writing.zh-CN.md) · [期刊定位与稿件规范](docs/journal-standards.zh-CN.md) | [Academic writing, publication, and translation](docs/capabilities/publication-and-translation.md) · [NSFC proposal support](docs/capabilities/nsfc-proposal-writing.md) · [Journal positioning and manuscript requirements](docs/journal-standards.md) |
| Project structure and extension | [架构](docs/architecture.zh-CN.md) · [格式与数据要求](docs/format-contracts.zh-CN.md) · [开发](docs/development.zh-CN.md) | [Architecture](docs/architecture.md) · [File and data requirements](docs/format-contracts.md) · [Development](docs/development.md) |
| Versions | [发布记录](docs/releases/README.zh-CN.md) | [Release notes](docs/releases/README.md) |

Biomed Workbench is licensed under [Apache-2.0](LICENSE); acknowledgements appear in [Third-Party Notices](THIRD_PARTY_NOTICES.md). Scientific modules, the evidence model, and release records evolve together; a new capability enters the public list only when its method definition, implementation, validation evidence, and documentation remain aligned.
