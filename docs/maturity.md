# Capability Maturity And Project Evidence

Languages: [English](maturity.md) · [中文](maturity.zh-CN.md)

A validated module is not automatically suitable for every organism, assay, study design, or data scale. Biomed Workbench reports separately how far a capability has been validated and what the evidence from the current project can support.

## Four Evidence Levels

| Level | What has been confirmed | What still requires confirmation |
| --- | --- | --- |
| Method definition complete | Inputs, outputs, parameters, quality checks, and conditions of use are defined | Whether external software ran and produced reliable results |
| Compatible setup tested | A named combination of software versions, dependencies, platform, and file formats works together | Untested versions, platforms, and study designs |
| Representative case passed | Public data or a stable service produced results that could be reopened under recorded conditions | Generalisation to other data and parameters |
| Current project validated | The user's data ran, the outputs were reopened, and scientific review was completed | Claims beyond the study design and observed evidence |

## How To Read Capability Labels

- **Validated:** the released implementation and recorded compatible setup passed representative checks. Project-specific quality control is still required for new data.
- **Experimental:** the workflow and parameter interface are usable, but coverage of public data, external software, or real projects is not yet broad enough for a default workflow.
- **Plannable:** the workbench can explain the method's role and prepare an analysis plan, but it cannot describe the analysis as completed.

Access method, browser interaction, or agent-managed execution does not determine scientific maturity.

## What Counts For A User Project

For a user project, the decisive evidence is the observed run, not the module name or release label. The workbench checks the actual inputs, software versions, parameters, output files, and quality results, then reopens the outputs for statistical and biological review.

A successful process exit shows only that computation ended. A result enters the project's [scientific evidence map](scientific-evidence-map.md) only after its relevant quality checks and scientific review pass. Failed, unrun, and indeterminate checks remain visible.

See [public-data cases](cases/README.md) for representative acceptance examples and [release notes](releases/README.md) for capability changes between versions.
