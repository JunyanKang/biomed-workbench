# Using Biomed Workbench

Languages: [English](using-biomed-workbench.md) · [中文](using-biomed-workbench.zh-CN.md)

## Start With The Research Question

Describe the biological question, available data, study design, and intended outcome. Users do not need to know module names or assemble a chain of tools themselves.

A clear request usually includes:

- the scientific question or hypotheses to compare;
- the samples, organisms, experimental system, platform, or molecular target;
- available files and essential metadata;
- controls, batches, donors, conditions, time points, and reference versions;
- the figures, tables, conclusions, manuscript content, or decision required.

When essential information can be established safely from project files, the workbench inspects those files first. It asks for clarification only when missing information would materially change the analysis.

## What A Complete Analysis Includes

The workbench selects methods that fit the question and then:

1. checks the study design, experimental units, input files, and metadata;
2. states the working hypothesis, alternative explanations, and decision criteria;
3. resolves assay, target, controls, normalisation, and the biological relation being tested, then selects one primary analysis and one necessary orthogonal validation for each question;
4. runs the packaged workflow with the project's real data;
5. reopens the outputs and reviews technical quality, statistical design, and biological plausibility;
6. decides whether to retain, qualify, reanalyse, replace, or extend the result;
7. classifies results as formal, candidate, sensitivity, or deprecated, then assembles traceable figures, tables, methods, conclusions, and bilingual reports.

The end of a computation is not automatically the end of an analysis. A result supports a project conclusion only after the relevant checks and scientific review. Failed analyses, negative findings, and conflicting evidence remain part of the record.

Long-running projects use a [project lock](project-governance.md) to freeze sample sheets, reference releases, cell annotation, replicate units, analysis environments, thresholds, colours, formal directories, and figure identities. Every observed execution records the content identity of its Conda environment, virtual environment, or container. A repeat analysis first reuses a verified environment and stops before computation if that environment has drifted. The routine result view prioritises scientific conclusions, key results, evidence boundaries, and the next decision; complete execution and provenance records remain available in the background when needed.

## Project Checkpoints

- **Data intake:** study design, files, metadata, references, and formats agree.
- **Analysis readiness:** statistical units, confounders, method choice, and expected outputs are clear.
- **Environment identity:** an existing compatible environment is reused where possible, and packages, lock files, interpreter, platform, and container identity agree with the relevant prior execution.
- **Result review:** technical quality, effect size, robustness, negative findings, and competing explanations are considered.
- **Scientific conclusion:** the support, counter-evidence, and limits of each important claim are explicit.
- **Delivery:** figures, tables, methods, citations, and prose agree with one another.

Important results enter the [scientific evidence map](scientific-evidence-map.md), which connects preceding evidence, analysis code, plot data, final files, captions, sources, and research decisions. Each version provides an HTML reading entry, Chinese and English reports, and Chinese and English evidence maps. Their tables of contents and direct links open registered data, scripts, figures, captions, and original studies; Markdown, JSON, and relationship tables remain stored with the version. Chinese and English reports use the same evidence version.

## How To Request Manuscript, Proposal, And Submission Work

A writing task may begin with one passage, an existing manuscript, or a complete project. Provide the available data and figures, study design, established findings, references, intended audience, and requested article type or section whenever possible. For an existing manuscript, also state what may be rewritten, what structure must remain, and whether a target journal or reviewer comments already exist.

The workbench combines the following work as the task requires:

1. verify literature, project facts, figures, and citations, and define which claims may enter the text;
2. plan the central argument, section roles, and figure placement for a paper or proposal before drafting or revision;
3. check that numbers, results, equations, technical terms, and citations remain consistent through revision;
4. review experimental units, statistical reporting, data and code availability, and target-journal and article-type requirements;
5. organise point-by-point responses, revision locations, and author input from the actual editor and reviewer comments;
6. reopen the final manuscript, figures, or presentation rather than delivering only an outline.

When only manuscript prose is supplied, the workbench reviews and revises that content but does not turn absent data, experiments, citations, contributions, or journal requirements into facts. An NSFC request should also provide the programme type and the current official form. The workbench treats Young C, Young B, Young A, General, Regional, Key and Major programmes separately and, once the scientific foundation is ready, continues to the requested proposal prose rather than stopping at an audit report. See [Academic Writing, Publication, And Translation](capabilities/publication-and-translation.md) and [NSFC proposal support](capabilities/nsfc-proposal-writing.md).

## Example Requests

> Analyse this bulk RNA-seq project with donor- and batch-aware statistics, pathway and network interpretation, sensitivity checks, and publication figures. Reassess the hypothesis if the main comparison is not supported.

> Design and run a single-cell analysis for these H5AD files, compare integration and annotation methods, preserve unknown cell states, and turn reviewed results into a manuscript-ready Results section.

> Summarise evidence for this target across PubMed, UniProt, ClinVar, clinical trials, PDB, and AlphaFold DB. Reconcile identifiers and separate established findings from testable hypotheses.

> Review these protein-structure and molecular-docking results, assess structural quality, interface confidence, and docking poses, and propose experiments that could test the model.

> Use these result tables, paper figures, method records, and verified references to establish the manuscript's central argument and section structure. Draft the Results and Discussion while linking each claim to its figure, citation, and evidence boundary.

> Review this funding proposal's scientific question, aims, feasibility evidence, and fallback strategy, then improve the scholarly prose without inventing preliminary results, collaborations, or funding requirements.

> Build a point-by-point response from the editor and reviewer text, linking each answer to the real analysis, experiment, figure, citation, and manuscript location. Retain unfinished work as author actions.

## Possible Deliverables

Depending on the task, outputs may include a data inventory, analysis plan, quality report, statistical tables, figures, methods, interpretation, manuscript text, reviewer responses, patent material, or a presentation. Each deliverable distinguishes observed results, evidence-based inference, failed checks, and unresolved questions.
