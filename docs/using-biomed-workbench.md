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
3. confirms method scope, software compatibility, and key parameters;
4. runs the packaged workflow with the project's real data;
5. reopens the outputs and reviews technical quality, statistical design, and biological plausibility;
6. decides whether to retain, qualify, reanalyse, replace, or extend the result;
7. assembles traceable figures, tables, methods, conclusions, and bilingual reports.

The end of a computation is not automatically the end of an analysis. A result supports a project conclusion only after the relevant checks and scientific review. Failed analyses, negative findings, and conflicting evidence remain part of the record.

## Project Checkpoints

- **Data intake:** study design, files, metadata, references, and formats agree.
- **Analysis readiness:** statistical units, confounders, method choice, and expected outputs are clear.
- **Result review:** technical quality, effect size, robustness, negative findings, and competing explanations are considered.
- **Scientific conclusion:** the support, counter-evidence, and limits of each important claim are explicit.
- **Delivery:** figures, tables, methods, citations, and prose agree with one another.

Important results enter the [scientific evidence map](scientific-evidence-map.md), which connects preceding evidence, analysis code, plot data, final files, captions, sources, and research decisions. Chinese and English reports use the same evidence version.

## Example Requests

> Analyse this bulk RNA-seq project with donor- and batch-aware statistics, pathway and network interpretation, sensitivity checks, and publication figures. Reassess the hypothesis if the main comparison is not supported.

> Design and run a single-cell analysis for these H5AD files, compare integration and annotation methods, preserve unknown cell states, and turn reviewed results into a manuscript-ready Results section.

> Summarise evidence for this target across PubMed, UniProt, ClinVar, clinical trials, PDB, and AlphaFold DB. Reconcile identifiers and separate established findings from testable hypotheses.

> Review these protein-structure and molecular-docking results, assess structural quality, interface confidence, and docking poses, and propose experiments that could test the model.

## Possible Deliverables

Depending on the task, outputs may include a data inventory, analysis plan, quality report, statistical tables, figures, methods, interpretation, manuscript text, reviewer responses, patent material, or a presentation. Each deliverable distinguishes observed results, evidence-based inference, failed checks, and unresolved questions.
