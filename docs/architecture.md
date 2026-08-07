# Architecture And Extension

Languages: [English](architecture.md) · [中文](architecture.zh-CN.md)

This page is for readers who want to understand the project structure or add a scientific method. Routine research use does not require these implementation details; see [Using Biomed Workbench](using-biomed-workbench.md).

## Overall Structure

Biomed Workbench provides one research entry. After the user describes a scientific question, the workbench selects appropriate methods from independent versioned modules and orders them according to their data dependencies.

Its main parts are:

- **Research entry:** interprets the goal, checks project context, and selects methods;
- **Scientific modules:** define method purpose, inputs, outputs, parameters, conditions of use, and quality checks;
- **Project record:** preserves hypotheses, analysis plans, observed results, reviews, and decisions;
- **Execution and coordination:** checks software compatibility, runs analyses, and reopens outputs;
- **Public-data services:** access bounded database endpoints and manage credentials by service;
- **Scientific evidence map:** connects retained results to their sources, figures, citations, and subsequent decisions.

The capability list is generated from the modules and is not maintained separately in routing code or documentation. This prevents a method from appearing in prose but not in the registry, or different entry points from reporting different capability counts.

## What A Module Must Define

Each scientific module must state:

- its scientific purpose, preferred use, and unsupported conclusions;
- input data, required metadata, outputs, and file formats;
- adjustable parameters and their rationale;
- software, dependencies, platforms, and version range;
- technical, statistical, and biological quality checks;
- methods that may replace or complement it;
- representative success, boundary, and failure tests.

A bioinformatics module that performs computation must also provide an actual workflow that accepts project parameters directly. Users are not expected to edit analysis-template source code.

## How Project Results Move Through The System

A result normally passes through analysis preparation, observed execution, output reopening, scientific review, and a decision to retain or exclude it. Only then can it enter the scientific evidence map. Failed, low-quality, and hypothesis-conflicting results remain in the record but are not presented as successful conclusions.

Large files remain in project-owned result storage. Project records refer to them by relative identity and content fingerprint, preventing developer-machine paths from entering shareable research records.

## Adding Or Updating A Method

A new method is added as an independent module. It does not require a separate user-facing skill or a special case in the router. Changes require regeneration of the capability list and completion of module, integration, and release checks.

Not every version change requires recomputation. A rerun is required when the scientific implementation, parameter meaning, input handling, or result recognition changes. Documentation, catalogue, or unrelated-module changes do not automatically invalidate previous scientific results.

See [Development And Release](development.md) for directories, commands, and release requirements, and [File And Data Requirements](format-contracts.md) for shared input rules.
