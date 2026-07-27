# Using Biomed Workbench

Languages: [English](using-biomed-workbench.md) · [中文](using-biomed-workbench.zh-CN.md)

## Start With A Scientific Goal

Invoke `biomed-workbench` and describe the biological question, the available data, the experimental units, and the intended decision or deliverable. Natural-language requests are preferred; users do not need to know module names or manually chain skills.

A useful request identifies:

- the scientific question or competing hypotheses;
- the samples, cohorts, organisms, assays, or molecular targets;
- available files and important metadata;
- known controls, batches, donors, conditions, and time points;
- the expected decision, figure, manuscript section, or translational output;
- constraints such as species, genome build, review date, or reporting standard.

When essential context can be recovered from the project files, the workbench inspects it directly. It asks the user only for information that cannot be inferred safely and materially changes the analysis.

## What The Agent Does

The unified skill selects a single, serial, parallel, or mixed workflow. It should then:

1. validate the project context and input contracts;
2. state the working hypotheses and decision criteria;
3. identify the scientific modules and artifact dependencies;
4. check tool compatibility and available evidence before execution;
5. run or adapt module templates in the project environment;
6. inspect outputs against module-specific quality gates;
7. revise the plan when results contradict the hypothesis or fail quality checks;
8. assemble interpretable artifacts and a claim-evidence trail;
9. review the result from statistical, biological, and publication perspectives;
10. deliver the requested research package with unresolved limitations visible.

## Project Checkpoints

For broad projects, the workbench maintains explicit checkpoints rather than treating the first successful run as completion:

- **Intake:** data inventory, sample design, metadata completeness, format and reference compatibility.
- **Analysis readiness:** executable plan, module contracts, confounders, statistical unit, and expected artifacts.
- **Result validity:** technical QC, biological plausibility, sensitivity analyses, negative findings, and competing explanations.
- **Interpretation:** support and refutation for each consequential claim, with causal limits preserved.
- **Delivery:** figures, methods, tables, citations, review findings, and reproducibility records agree with one another.

## Example Requests

> Build an evidence map for this target across PubMed, UniProt, ClinVar, clinical trials, PDB, and AlphaFold DB. Reconcile conflicting identifiers and separate established findings from hypotheses.

> Analyze this bulk RNA-seq project with donor-aware statistics, pathway and network interpretation, sensitivity checks, and a figure-to-claim plan. Revise the hypothesis if the main contrast is not supported.

> Design and audit a single-cell workflow for these H5AD files, preserve unknown cell states, compare integration and annotation evidence, and carry validated conclusions into a manuscript-ready results section.

> Review this molecular design package from sequence and structure quality through docking-pose checks and experimental validation planning. Do not treat prediction confidence as binding evidence.

## Deliverables

Depending on the task, outputs may include validated data inventories, workflow plans, analysis artifacts, quality reports, evidence tables, figures, methods, manuscripts, reviewer reports, response matrices, patent disclosures, or presentation plans. Every deliverable should state what was executed, what was inferred, what failed, and what remains unresolved.
