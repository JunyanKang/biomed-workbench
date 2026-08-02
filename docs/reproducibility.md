# Reproducibility And Compatibility

Languages: [English](reproducibility.md) · [中文](reproducibility.zh-CN.md)

## Version Policy

Scientific software versions affect accepted inputs, defaults, output fields, and numerical behaviour. Biomed Workbench therefore treats versions as provenance and compatibility evidence rather than universal installation pins.

Each scientific module declares:

- accepted input and output contracts;
- a conservative compatibility policy;
- one or more reproducibility baselines observed in verification;
- known scientific and format boundaries;
- the checks required before an output can enter project evidence.

The published numeric versions are **reproducibility baselines**, **not installation pins** for every user project. At execution time, the workbench records the **actual detected versions** and whether each one matches an exact tested baseline. Versions inside the declared policy may execute if their outputs pass the module's contract and representative checks.

When a scientific backend is absent or incompatible, guidance and routing remain available. Execution evidence is withheld until a compatible environment or validated alternative is available. The plugin does not silently change the user's execution environment.

## Evidence Layers

Reproducibility is represented by several linked layers:

1. **Module contract:** scientific purpose, inputs, outputs, compatibility rules, and quality gates.
2. **Packaged implementation:** immutable released code with a declared input, configuration, or command surface; routine project execution binds parameters without editing source.
3. **Execution provenance:** actual tools, versions, parameters, inputs, output digests, and observed checks.
4. **Scientific evidence:** interpreted results that passed the relevant technical and scientific gates.
5. **Decision record:** why a hypothesis, workflow, or claim was accepted, revised, rejected, or left unresolved.

A completed process is not automatically scientific evidence. Outputs enter the evidence ledger only after the module contract and project-specific quality checks succeed.

## Format Contracts

Shared profiles cover foundational sequencing, alignment, variant, interval, expression, single-cell, tabular, and image formats. Modules inherit exact format-version rules for compression, indices, sorting, coordinate systems, references, annotations, identifiers, manifests, orientation, metadata, and payload role. See [format contracts](format-contracts.md).

## Published Verification

The [`reports/`](../reports/) directory contains release-safe summaries for compatibility execution, bioinformatics template coverage, public database checks, structural and single-cell verification, deterministic evidence, plugin installation, and public-data acceptance cases. Reports preserve concrete verification results without exposing private source paths or credentials.

Project analysis uses the [scientific evidence map](scientific-evidence-map.md)
to pre-admit analyses, review every result and figure panel, retain or exclude
artifacts without deleting history, and render separate Chinese and English
interpretation reports from one validated evidence graph.

The detailed baseline table is generated from the module registry and compatibility reports rather than duplicated in this guide. This keeps user documentation readable while preserving machine-verifiable evidence at the source of truth.

## Credentials And External Services

Public clients use bounded schemas, host allow-lists, response limits, identifier preservation, and explicit truncation or disagreement states. Optional API keys are supplied through the user's environment or an approved secret surface and must never be hard-coded. Credentials are not included in execution artifacts, reports, examples, or commits.
