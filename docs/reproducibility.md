# Reproducibility And Compatibility

Languages: [English](reproducibility.md) · [中文](reproducibility.zh-CN.md)

## How Software Versions Are Handled

Scientific software versions can change accepted inputs, defaults, output fields, and numerical results. Biomed Workbench records the software and version actually used and compares them with versions observed during testing.

Specific versions in the documentation are **reproducibility baselines**: they show the conditions under which representative cases passed. They are **not installation pins** for every project. The workbench records the **actual detected versions** during each run. Other versions within a declared compatibility range may be used, but their inputs, outputs, and quality results must still pass the relevant checks.

When required software is missing or incompatible, guidance and routing remain available so that the workbench can still plan the analysis and prepare inputs, but it does not describe the analysis as executed. Environment changes are made only within user-authorised scope and available resources.

## What Makes A Result Traceable

Each observed analysis should retain:

1. its scientific purpose, conditions of use, and input requirements;
2. the software, versions, parameters, and references used;
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
