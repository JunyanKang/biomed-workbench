# Biomed Workbench v0.2 Clean-Room Rewrite Blueprint

## Product Definition

Biomed Workbench is one Codex plugin that acts as a biomedical research assistant. Codex owns scientific reasoning, planning, tool selection, interpretation, and communication. The package supplies validated scientific operations, evidence clients, reproducible compute plans, and auditable research records. It does not expose a collection of upstream skills and does not call a second general-purpose language model.

The user invokes only `biomed-workbench`. Internal operations may run alone, serially, in parallel, or as a dependency graph. User-facing output is a scientific answer or artifact with evidence and limitations, never a list of tool names.

## Evidence Base

The architecture is driven by an exact, live-verified understanding ledger rather than selected examples:

- 89,314 files read and assigned a concrete purpose;
- 5,975 public code symbols extracted;
- 425 assistant workflow files analyzed;
- 1,505 executable source files assigned to clean-room capability redesign;
- 390 workflow files assigned to the single Codex entrypoint;
- 625 verification files assigned to the new test system;
- 2,189 guidance files assigned to source-neutral synthesis;
- 82,081 generated dependency/runtime files individually hashed and grouped for readiness modeling only;
- 52 sensitive files structurally classified and excluded.

The private one-to-one evidence stays under `.source-audit/`. Publish-safe aggregates are in `reports/source-assimilation-summary.json`, `reports/source-learning-synthesis.json`, and `reports/rewrite-design-summary.json`.

## Clean-Room Rules

1. Upstream files contribute purpose, scientific assumptions, input/output contracts, failure cases, and workflow lessons only.
2. New operational code is written in the new package architecture. Existing source-derived `scripts/`, adapters, catalogs, prompts, and copied references are removed before release.
3. No operational ID, path, module, or catalog field names an upstream project.
4. The only permitted reuse modes are `concept_only`, `attribution_only`, and `none`.
5. A similarity audit compares the final code with all non-generated upstream text and rejects suspicious shared implementation blocks.
6. Attribution and license obligations live in `NOTICE.md` and `references/provenance.json`; they are not runtime dependencies.
7. Every advertised operation has a local entrypoint, input contract, safety classification, and end-to-end verification record.

## Final Project Shape

```text
biomed-workbench/
  .codex-plugin/plugin.json
  .agents/plugins/marketplace.json
  skills/biomed-workbench/SKILL.md
  biomed_workbench/
    assistant.py
    contracts.py
    registry.py
    router.py
    execution.py
    research.py
    provenance.py
    capabilities/
      evidence.py
      data.py
      omics.py
      statistics.py
      molecular.py
      structure.py
      imaging.py
      clinical.py
      experiment.py
      visualization.py
      publication.py
    services/
      http.py
      credentials.py
      eutils.py
      literature.py
      biomedical.py
      environments.py
      containers.py
      slurm.py
      local_models.py
    workflows/
      research.py
      publication.py
      compute.py
  tools/
    biomed.py
    assimilate_sources.py
    validate_workbench.py
  references/
    capabilities/
    provenance.json
  tests/
    unit/
    contract/
    e2e/
    live/
    release/
  reports/
```

There is no final `scripts/` hierarchy. Thin command entrypoints delegate to package functions; scientific behavior never lives in wrappers.

## Capability Model

Every operation declares:

- scientific objective and exclusions;
- JSON input and output contracts;
- access mode: offline, public API, optional API, or local runtime;
- mutability: read-only, writes output, changes environment, starts service, or submits work;
- requirements and readiness probes;
- evidence and artifact semantics;
- validation checks and known limitations.

Overlapping source functions are merged when they represent the same scientific operation. Large source functions are separated when they mix query interpretation, data access, analysis, and presentation. Nested LLM calls are replaced by Codex planning plus typed operation inputs.

## Redesigned Operation Families

### Research core

`research-frame`, `research-plan`, `research-run`, `research-interpret`, and `research-audit` implement the seven-state lifecycle: frame, plan, investigate, design, interpret, deliver, audit. These are Codex-native orchestration contracts, not a second agent runtime.

### Evidence and biomedical knowledge

`evidence-search`, `evidence-fetch`, `evidence-link`, `citation-verify`, `identifier-resolve`, `gene-evidence`, `variant-evidence`, `compound-evidence`, `trial-evidence`, and `protocol-find` replace natural-language-to-API model calls and disconnected database helpers.

The common evidence layer normalizes identifiers, provenance, timestamps, query parameters, pagination, rate limits, empty results, and database-specific records. NCBI Entrez uses one programmed E-utilities client across PubMed, PMC, Gene, Protein, Nuccore, SRA, GEO DataSets, BioSample, BioProject, ClinVar, Taxonomy, MeSH, PubChem Compound, and PubChem Assay. Public zero-key services remain available by default.

### Data and omics

`data-profile`, `data-validate`, `table-transform`, `sequence-inspect`, `sequence-qc`, `variant-summary`, `expression-qc`, `differential-expression`, `enrichment`, `network-analysis`, `single-cell-qc`, `ngs-plan`, and `phylogeny` replace scattered format checks, one-off scripts, and workflow generators.

Operations separate pure calculations from optional heavy backends. Small deterministic fixtures execute in CI. External tools use command plans and readiness probes before a real run.

### Molecular and systems design

`primer-design`, `crispr-design`, `cloning-plan`, `sequence-optimize`, `restriction-plan`, `glycosylation-screen`, `kinetic-simulation`, and `circuit-simulation` combine sequence utilities, design constraints, scoring, and explicit assumptions. Outputs include candidate ranking, rejected candidates, off-target or feasibility warnings, and reproducible parameters.

### Structure and local scientific models

`structure-lookup`, `structure-prepare`, `structure-predict`, `structure-evaluate`, `msa-build`, `docking-run`, `inverse-fold`, and `backbone-design` provide one local scientific model contract. Hosted inference endpoints and vendor model tokens are not retained.

Initial backends are limited to independently installable implementations that pass license and reproducibility checks, such as Boltz, local DiffDock, ProteinMPNN, RFdiffusion, OpenFold/ColabFold-compatible workflows, Foldseek, and MMseqs2. A backend definition validates inputs, constructs commands, records versions and weights, parses outputs, and runs scientific quality checks.

### Imaging and phenotyping

`image-profile`, `microscopy-segment`, `morphology-quantify`, `colocalization`, `cell-track`, and `dicom-deidentify` separate image I/O, measurement, model-assisted segmentation, quality control, and visualization. Tests use generated fixtures with known geometry and intensity values.

### Clinical and experimental research

`clinical-deidentify`, `cohort-summarize`, `survival-analyze`, `biomarker-evaluate`, `trial-audit`, `case-audit`, `protocol-design`, `dilution-plan`, `pcr-plan`, `dose-response`, `growth-curve`, `assay-quantify`, and `flow-gating` replace template-only scripts with validated calculations and explicit reporting standards.

Clinical operations are research support, not diagnosis or treatment. Protocol operations distinguish sourced protocol evidence from newly designed steps and surface biosafety or institutional review requirements.

### Publication and translation

`manuscript-plan`, `manuscript-draft`, `manuscript-polish`, `review-simulate`, `response-draft`, `citation-ground`, `figure-design`, `patent-draft`, `presentation-build`, and `availability-audit` consolidate the learned publication workflows behind one Codex skill. They consume evidence and analysis artifacts instead of operating as isolated slash commands.

### Managed compute

`runtime-status`, `environment-plan`, `container-plan`, `slurm-plan`, `job-submit`, `job-monitor`, `model-run`, and `workflow-run` define the plugin's infrastructure boundary.

The plugin owns read-only discovery, input validation, command construction, resource planning, explicit-intent gates, submission, monitoring, artifact collection, and execution manifests. It does not install GPU drivers, act as a container engine, administer a cluster, silently download model weights, or start work without user intent.

## Credential Policy

Core use requires no credential. The v0.2 allowlist contains only:

- `NCBI_API_KEY`, optional for higher E-utilities request limits;
- `ELSEVIER_API_KEY`, optional for authorized metadata access;
- `SYNAPSE_AUTH_TOKEN`, optional for user-authorized controlled resources.

`NCBI_EMAIL` is optional contact metadata, not a secret. One central credential service reads values only at invocation. Values never appear in errors, manifests, reports, tests, or repository files. No general-purpose model-provider credential is accepted.

## End-to-End Definition Of Done

An operation is releasable only when all applicable checks pass:

1. contract resolves and rejects malformed input before side effects;
2. pure unit fixture produces a scientifically checked result;
3. command or service contract is tested with an injected transport/process;
4. bounded live verification passes for public services;
5. optional dependency absence produces a useful guarded result;
6. local runtime command is built and parsed without unintended execution;
7. mutating or submitted work requires explicit permission;
8. output contains evidence, parameters, limitations, and artifact metadata;
9. unified CLI and Codex research flow both reach the operation;
10. verification evidence is recorded in the release matrix;
11. final code has no forbidden source path, bridge, credential, or suspicious source similarity.

## Legacy Removal Gate

Before v0.2.0 release, the following old surfaces are deleted after their replacement tests pass:

- `scripts/` and source-derived helper trees;
- `tools/adapters/`;
- the 415-row source-oriented `tools/catalog.json`;
- source-specific reference catalogs and audit reports;
- extra model-provider and hosted inference clients;
- copied workflow text superseded by the single skill and source-neutral capability references.

The release report will state the final number of newly written code files and lines, the number of learned source files, the number excluded by reason, and the end-to-end pass count. These numbers are computed from Git and the verified ledgers rather than estimated manually.
