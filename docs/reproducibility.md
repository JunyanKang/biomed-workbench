# Reproducibility And Compatibility

Languages: [English](reproducibility.md) · [中文](reproducibility.zh-CN.md)

## How Software And Analysis Environments Are Handled

Scientific software versions, dependency resolution, reference resources, and runtime environments can change accepted inputs, defaults, output fields, and numerical results. Biomed Workbench records more than individual tool versions. Every observed execution carries an analysis-environment identity covering the environment manager (such as Conda, Mamba, a virtual environment, or a container), environment name, interpreter version, operating system and architecture, project lock-file digests, resolved package-inventory digest, and container-image digest. Local environment coordinates are represented by digests so private machine paths do not enter shareable research state.

Specific versions in the documentation are **reproducibility baselines**: they show the conditions under which representative cases passed. They are **not installation pins** for every project. The workbench records the **actual detected versions** during each run. Other versions within a declared compatibility range may be used, but their inputs, outputs, and quality results must still pass the relevant checks.

When required software is missing or incompatible, guidance and routing remain available so that the workbench can still plan the analysis and prepare inputs, but it does not describe the analysis as executed. Environment changes are made only within user-authorised scope and available resources.

## Preventing Drift Before A Repeat Analysis

Before the same module and compatibility profile run again in a project, the workbench compares the active environment with prior execution receipts:

- an identical environment is reused without another installation;
- an environment relocated without content changes is recognised as content-equivalent and can be reused;
- a change in packages, lock files, interpreter, platform, or container image stops execution before computation and cannot overwrite the earlier analysis chain;
- a legacy receipt without environment provenance requires recovery and verification of the original runtime before re-execution.

An intentional dependency upgrade or platform change belongs to an explicit new analysis branch with a stated rationale and renewed compatibility, output-reload, and scientific review. Packaged analysis templates never install dependencies during analysis. An isolated environment is prepared only after no reusable environment is found, the installation scope is authorised, and resources are sufficient.

Private project environment records are stored under `.biomed-workbench/environments/` and are also bound to execution receipts. An agent can inspect them before running, or `tools/workbench environment --project-root PROJECT` can report the current reuse decision; optional module and compatibility-row filters narrow the comparison.

## What Makes A Result Traceable

Each observed analysis should retain:

1. its scientific purpose, conditions of use, and input requirements;
2. the software, versions, analysis environment, parameters, random seeds, and references used;
3. input files, output files, and quality results;
4. statistical and biological review;
5. the reason for retaining, qualifying, excluding, or reanalysing the result.

This supports both computational repetition and reconstruction of the scientific decision. A successful process exit cannot replace review of the result.

## Files And Reference Versions

Sequencing data, alignments, genomic intervals, expression matrices, single-cell objects, tables, and images have different format requirements. The workbench checks compression and indices, sorting, coordinate systems, genome builds, annotations, gene identifiers, orientation, and required metadata. See [File And Data Requirements](format-contracts.md).

## Where To Review Validation Status

- [Capability Maturity](maturity.md) explains the validation levels;
- [Public-Data Cases](cases/README.md) lists representative acceptance examples;
- [Release Notes](releases/README.md) records capability and compatibility changes;
- [`reports/`](../reports/) contains release-check and representative-case summaries.

## Credentials And External Services

API keys and website accounts are used only to access the relevant service. They are not written to analysis outputs, reports, examples, or the repository. See [Data Access And Credentials](data-access-and-credentials.md) for service requirements and safe configuration.
