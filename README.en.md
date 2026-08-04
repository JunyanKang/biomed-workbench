<p align="center">
  <img src="assets/biomed-workbench-mark.svg" width="104" alt="Biomed Workbench mark">
</p>

<h1 align="center">Biomed Workbench</h1>

<p align="center"><strong>Compile biomedical questions into executable, reviewable, evolving chains of scientific evidence</strong></p>

<p align="center">
  An agent-driven biomedical research workbench<br>
  Evidence · Analysis · Scientific Review · Publication
</p>

<p align="center">
  <a href="README.md">中文</a> · <a href="README.en.md">English</a>
</p>

<p align="center">
  <a href="https://github.com/JunyanKang/biomed-workbench/actions"><img alt="Quality" src="https://img.shields.io/github/actions/workflow/status/JunyanKang/biomed-workbench/quality.yml?branch=main&amp;label=quality"></a>
  <a href="LICENSE"><img alt="Apache-2.0 license" src="https://img.shields.io/badge/license-Apache--2.0-4388C7"></a>
  <img alt="198 scientific modules" src="https://img.shields.io/badge/scientific%20modules-198-36A58B">
  <img alt="Codex first" src="https://img.shields.io/badge/Codex-first-E05A47">
  <img alt="Versioned evidence maps" src="https://img.shields.io/badge/evidence%20maps-versioned-C7953E">
</p>

<p align="center">
  <img src="assets/readme/biomed-workbench-hero.png" width="100%" alt="Conceptual path from multimodal biomedical inputs to evidence networks and publication">
</p>

<p align="center"><sub>Conceptual illustration: multimodal inputs move through scientific orchestration, quality review, and provenance tracking into research deliverables. Visual elements are illustrative, not experimental observations.</sub></p>

What ambitious research lacks is rarely one more isolated tool. The harder problem is scientific continuity: how a question is decomposed, why a method is admitted, whether data support inference, how results survive technical and biological review, and which next step can genuinely change the state of knowledge.

Biomed Workbench brings that continuity into agent-assisted research. Researchers describe an objective in natural language; the workbench coordinates evidence retrieval, omics, single-cell and spatial analysis, molecular design, quantitative experiments, scientific figures, and publication—while maintaining explicit dependencies, quality gates, and a versioned scientific evidence map. Codex is the primary reference host and the only host currently covered by the complete release path. Other agents that support a skills-directory convention or MCP can reuse the same scientific registry, but execution, permissions, runtime management, and evidence delivery still require independent implementation and validation in that host.

The result is a research system built to answer four durable questions:

- **Why this analysis:** rationale, competing hypotheses, experimental unit, and decision criterion.
- **How it was performed:** official method sources, input/output contracts, parameter rationale, applicable designs, and verified compatibility combinations.
- **What the result supports:** technical, statistical, biological, and robustness review.
- **What happens next:** retain, retain with caveat, rerun, switch method, acquire data, revise the hypothesis, or stop the branch.

## A project, not a command sequence

One entry point interprets the complete research objective and selects the smallest scientifically sufficient set of registered capabilities. Independent questions may be tested in parallel, dependent analyses execute in order, and every reviewed route remains available to guide the next decision.

<p align="center">
  <img src="assets/readme/research-decision-loop.png" width="100%" alt="Scientific decision cycle from question admission through review, evidence retention, revision and delivery">
</p>

<p align="center"><sub>Conceptual illustration: every branch moves through admission, execution, four-part scientific review and an explicit decision. Retained evidence supports downstream work; revision and new data re-enter the cycle.</sub></p>

Every analysis node defines method fit, adjustable parameters, alternatives, and falsification criteria before execution. Every artifact receives scientific review before it supports a conclusion. Computational success is a process state; evidentiary strength still depends on design, quality, and interpretive scope.

## The scientific evidence map

Research changes as new data, methods, and judgments arrive. Biomed Workbench preserves that evolution at two readable levels:

1. a **project story map** showing only the consequential dependencies among figures and data results;
2. a **result-level evidence map** expanding prior conclusions, registered data, plot-ready data, analysis scripts, figure composition, final PDF/PNG files, captions, narrative sources, and DOI records.

Each file carries a clickable workspace-relative path, media type, and a verification fingerprint. A project snapshot may truthfully show pending, failed, and excluded branches. Before formal rendering or delivery, the workbench freezes the exact upstream results, reviews, decisions, and plan bindings and authorizes only the named delivery task. After that output is reloaded and reviewed, a terminal map archives the completed plan. Bilingual reports read the same validated map, while version numbers, parent-version fingerprints, a recoverable publication transaction, and immutable version directories preserve the lineage of scientific interpretation.

<p align="center">
  <img src="assets/readme/scientific-evidence-map.png" width="100%" alt="Conceptual two-layer scientific evidence map with result-level file provenance">
</p>

<p align="center"><sub>Conceptual illustration: the upper layer carries the project story; the lower layer traces one result through its complete artifact lineage. Formal relationships live in the validated evidence map and its structured relationship record.</sub></p>

Read the complete design in [Scientific Evidence Map](docs/scientific-evidence-map.md).

## From molecules to tissue, from data to argument

The current registry contains **198 scientific modules** spanning the major layers of research from knowledge building to scientific delivery. Evidence, databases, and literature establish what is known, contested, or missing; data analysis connects bulk, single-cell, spatial, and cross-scale studies; molecular and structural biology, clinical and experimental research, and imaging and visualization support mechanistic reasoning, experimental measurement, and morphological or spatial evidence; publication and translation turn reviewed results into narratives suited to particular audiences, journals, and applications.

Within the data-analysis layer, capabilities are further organized by data scale, measurement family, and tool role. Targets, antibodies, internal references, specificity treatments, and normalization strategies remain properties of an experimental or analytical design rather than being promoted to separate omics categories. Module registration establishes the scientific contract; the capability that can actually be claimed is defined by the backend, version, study design, and reloaded artifacts recorded in each public-data case.

| Research layer | Representative released capabilities |
| --- | --- |
| [Evidence, databases, and literature](docs/capabilities/evidence-and-literature.md) | NCBI, UniProt, Ensembl, gnomAD, HPO, GO, Reactome, Open Targets, Europe PMC, Crossref, bioRxiv, ClinicalTrials.gov, source freshness, citation and claim review |
| [Bulk measurements](docs/capabilities/bulk-sequencing-assays.md) | bulk RNA-seq; ChIP-seq, CUT&RUN and CUT&Tag; R-loop mapping by DRIP-seq/DRIPc-seq, qDRIP-seq, R-ChIP or MapR; RIP-seq, eCLIP and LACE-seq; Ribo-seq with multiple ORF callers; GRO-seq, PRO-seq, TT-seq and NET-seq; ATAC-seq, DNA methylation, 3D genome and RNA-modification enrichment |
| [Single-cell measurements, trajectories, and integration](docs/capabilities/single-cell-integration-reference-cross-species.md) | Scanpy/Seurat, scVI/scANVI, Harmony, CCA/RPCA, FastMNN, scIB, WNN and MOFA+; MultiVI accepted on public PBMC multiome data; SAMap accepted on the public Hydra–planarian case |
| [Spatial measurements](docs/capabilities/trajectory-spatial-complete-analysis.md) | Visium and Xenium data structures; Xenium–SpatialData–Squidpy image/segmentation analysis; RCTD accepted on Slide-seq and Tangram on public data; PASTE slice alignment and three-dimensional coordinates |
| [Universal analysis and project methods](docs/capabilities/omics-and-single-cell.md) | format validation, sample design, differential testing, DEqMS, GO/KEGG, GSEA, WGCNA, motifs, networks, evidence review and visualization specifications that can serve several measurement scales |
| [Molecular and structural biology](docs/capabilities/molecular-and-structural.md) | STRING functional and physical interaction networks; HADDOCK3 complex docking with DockQ reference evaluation and PRODIGY affinity estimates; manual AlphaFold Server submission packages, multi-job/multi-model reload from real result archives, confidence and cross-chain-contact review, and replot-ready publication figures; resource- and permission-gated local official AlphaFold 3 entry; MSBio2/Metascape and Cytoscape network delivery; sequence, ORF, PCR, CRISPR, cloning, structure quality, comparison and validation design |
| [Clinical and experimental research](docs/capabilities/clinical-and-experimental.md) | Cohort and survival analysis, biomarkers, flow cytometry, qPCR, dose response, western blot, biodistribution, xenograft, stability and quantitative assays |
| [Imaging and scientific visualization](docs/capabilities/imaging-and-visualization.md) | Image profiling, segmentation, colocalization, tracking, tissue-image registration, unified figure specifications, multi-part figure composition and visual QA |
| [Publication and translation](docs/capabilities/publication-and-translation.md) | Versioned standards for 100 journals, tiered JIF/JCR provenance, project-to-journal fit, article-structure and limit review, figure specifications, manuscript review, citation audit, reviewer simulation, response matrices, revision lineage, patent preparation and presentations |

<p align="center">
  <img src="assets/readme/multiscale-omics.png" width="100%" alt="Conceptual overview of multiscale omics, spatial analysis, trajectories and publication figures">
</p>

<p align="center"><sub>Conceptual illustration: sample-aware modalities are coordinated across cellular and tissue scales. Distributions, structures, and tissue morphology are schematic.</sub></p>

Explore the full capability map: [中文](docs/capabilities/README.zh-CN.md) · [English](docs/capabilities/README.md).

## Rigor as a runtime property

- **Experimental units first.** Condition-level inference returns to donors, samples, animals, organoids, or independently prepared specimens.
- **Raw evidence preserved.** Single-cell and multimodal integration retains raw counts; differential inference uses the statistical level appropriate to the design.
- **Parameters justified.** Defaults are candidates. Consequential settings are selected from observed data, official APIs, method papers, and sensitivity results.
- **Quality gates govern delivery.** Results enter formal conclusions and downstream analyses only after satisfying declared input, execution, statistical, and biological criteria.
- **The full research trajectory remains visible.** Supporting, weakening, conflicting, and pending evidence stays in the event ledger so every method revision has a reviewable rationale.
- **Artifacts are re-verifiable.** Actual software versions, seeds, parameters, code, and checksums accompany results; serialized objects are reloaded before delivery.
- **Figures and prose share a source.** Figure elements, captions, results text, and DOI records derive from the same validated evidence map.

## Start a research project

After installation, describe the project objective directly to the agent. Researchers do not need to memorize module IDs or assemble internal skills. The examples below use the fully validated Codex path. Another host can complete an equivalent node only when it supplies the same file access, permission handling, scientific execution, artifact reload, and evidence-registration responsibilities.

> Build a donor-aware single-cell and spatial research program from the raw data and sample design. Compare integration, annotation, deconvolution, trajectory, and communication strategies; define method rationale, quality gates, figure plans, and decision criteria at every stage.

> Design a CUT&Tag study in which S9.6 is the declared target. Evaluate whether an internal reference is justified for normalization and use RNase H-treated material as specificity evidence. Then perform peak analysis, differential testing, GO/KEGG, GSEA, WGCNA, and transcriptional linkage.

> Design a Ribo-seq study with explicit periodicity and P-site quality gates. Compare Ribo-TISH and Ribotricer for translated-ORF discovery, register caller agreement and disagreement, and keep RNA-seq-based expression analysis separate from translation evidence.

> Build an evidence map for TP53 across literature, genes, variants, pathways, structures, and clinical trials. Separate direct evidence, association, conflict, and knowledge gaps, then propose the experiment most likely to change the current judgment.

The workbench inspects real project files and experimental design before compiling a plan, executing applicable modules, reviewing artifacts, and recommending the next decision. See [Using Biomed Workbench](docs/using-biomed-workbench.md).

## Installation

In Codex, say:

> Install the current release of [JunyanKang/biomed-workbench](https://github.com/JunyanKang/biomed-workbench). Verify the unified research entry, scientific-module registry, exact revision, and dependency state; preserve existing local changes; run the release-integrity checks; then reload the plugin.

After installation, open a new task and describe the scientific objective directly. Use the same natural-language request for updates, including preservation of local changes and release-integrity verification.

Biomed Workbench follows a **Codex-first, interoperable** host strategy. Codex is the complete validated reference implementation. Agents that support the Agent Skills convention may read the unified research entry, while hosts with local stdio MCP support may use bounded discovery, routing, contract-inspection, and read-only execution interfaces. These entries share the scientific registry but do not automatically supply Codex file operations, permission interaction, runtime management, browser authentication, native image generation, or project evidence delivery. “Usable by other agents” therefore means that a defined interoperability path exists, not that every host has received equivalent end-to-end certification. Details: [中文](docs/installation.zh-CN.md) · [English](docs/installation.md); interoperability boundaries: [中文](docs/agent-integration.zh-CN.md) · [English](docs/agent-integration.md).

Another agent should not copy the Codex plugin-install request verbatim. Use:

> Obtain the current release of [JunyanKang/biomed-workbench](https://github.com/JunyanKang/biomed-workbench) as a local research-capability package. If this host supports Agent Skills, load the unified research entry; if it supports local stdio MCP, configure the bounded interoperability interface. Do not treat the repository's Codex plugin metadata as proof that this host has installed or validated the complete product path. Report which file-access, permission, runtime, artifact-reload, and evidence-delivery responsibilities this host can actually satisfy.

A full repository checkout still includes `.codex-plugin` and `.agents/plugins`. They are small Codex release metadata and may remain present but unloaded in another host. Keep them with the repository because the scientific modules, registry, and validation records must remain version-aligned; do not manually prune them from a checkout.

## Data access and credentials

Credential requirements are audited at the endpoint level. The implemented public database APIs can be used anonymously; `NCBI_API_KEY` is optional for NCBI E-utilities and Datasets and raises request capacity. AlphaFold Server is different: it uses an interactive Google sign-in on the official website and user-reviewed manual submission. The workbench records only an access state, never a password, token, cookie, or browser session, and applies downstream restrictions according to result origin.

A researcher may ask Codex to configure an optional NCBI key or check AlphaFold Server access. Sensitive values remain outside project artifacts, Git, logs, reports, and evidence maps; Google authentication must occur on the official page. See [中文](docs/data-access-and-credentials.zh-CN.md) · [English](docs/data-access-and-credentials.md).

## Documentation

- Release notes and version acceptance: [中文](docs/releases/README.zh-CN.md) · [English](docs/releases/README.md)
- Scientific evidence maps and bilingual reports: [中文](docs/scientific-evidence-map.zh-CN.md) · [English](docs/scientific-evidence-map.md)
- Capability map: [中文](docs/capabilities/README.zh-CN.md) · [English](docs/capabilities/README.md)
- Usage: [中文](docs/using-biomed-workbench.zh-CN.md) · [English](docs/using-biomed-workbench.md)
- Installation: [中文](docs/installation.zh-CN.md) · [English](docs/installation.md)
- Optional interoperability adapters: [中文](docs/agent-integration.zh-CN.md) · [English](docs/agent-integration.md)
- Data access and credentials: [中文](docs/data-access-and-credentials.zh-CN.md) · [English](docs/data-access-and-credentials.md)
- Journal standards and manuscript review: [中文](docs/journal-standards.zh-CN.md) · [English](docs/journal-standards.md)
- Reproducibility: [中文](docs/reproducibility.zh-CN.md) · [English](docs/reproducibility.md)
- Public-data validation cases: [中文](docs/cases/README.zh-CN.md) · [English](docs/cases/README.md)
- Maturity and evidence levels: [中文](docs/maturity.zh-CN.md) · [English](docs/maturity.md)
- Architecture and extension: [中文](docs/architecture.zh-CN.md) · [English](docs/architecture.md)
- Format contracts: [中文](docs/format-contracts.zh-CN.md) · [English](docs/format-contracts.md)
- Development and release: [中文](docs/development.zh-CN.md) · [English](docs/development.md)

## Research integrity

Biomed Workbench calibrates conclusion strength to evidence level, preserves scientific context in replayable project state, and records interpretive change through version lineage. Exploratory findings retain their exploratory status; clinical, ethical, patent, and regulatory decisions enter the appropriate professional review; public deliverables carry the scientific information needed for reproducibility and suitable for release.

New methods join the system as independent modules with declared artifact contracts, tool and format compatibility, parameter surfaces, quality gates, validation evidence, and maturity. The entry point remains stable while the research capability graph continues to evolve.

Release-safe compatibility evidence, execution-readiness audits, and public-data cases are available in [`reports/`](reports/).

License: [Apache-2.0](LICENSE).
