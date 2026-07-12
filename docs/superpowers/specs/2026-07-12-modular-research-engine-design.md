# Modular Research Engine Design

## Purpose

Biomed Workbench is a general Codex-native scientific research assistant. It
must absorb the useful scientific capabilities represented across the audited
sources, expose one user-facing entry, and dynamically combine modules around
the user's project. It is not a fixed pipeline for one assay, disease, data
type, or publication task.

A paired single-cell RNA and ATAC project is one demanding acceptance case. It
is not the organizing principle of the product. The same engine must compose
literature, databases, omics, molecular design, imaging, clinical research,
wet-lab planning, statistics, figures, writing, review, patent translation,
and future tools that do not exist today.

## Product Boundary

The plugin owns:

- scientific problem framing and falsifiable hypothesis management;
- capability discovery, compatibility checks, and dynamic workflow planning;
- execution through validated scientific modules;
- quality control, evidence normalization, result interpretation, and revision;
- claim, figure, manuscript, review, and final-delivery traceability;
- module contracts, tests, documentation, and release compatibility.

The plugin does not own CPU allocation, GPU allocation, container management,
Slurm, remote compute, or local model hosting. A module may call scientific
software available to Codex, but infrastructure provisioning is outside the
module contract.

## Design Principles

1. **One entry, many modules.** Users invoke Biomed Workbench, not individual
   slash skills. The engine selects one module or a serial, parallel, or mixed
   graph.
2. **Scientific intent before tool name.** Planning starts from the question,
   hypotheses, data, evidence gaps, and quality requirements. Tool selection is
   a later constrained decision.
3. **Modules are self-describing.** Adding a module must not require editing a
   central keyword table, workflow list, or monolithic router.
4. **Established engines remain engines.** The plugin coordinates established
   analysis libraries and databases instead of replacing them with toy
   algorithms.
5. **Results change the plan.** Every completed action can support, weaken,
   refute, or leave a hypothesis unresolved and can create corrective actions.
6. **Biological samples define inference.** Cells, reads, images, fields, and
   technical replicates cannot silently become independent biological units.
7. **Claims are evidence products.** No result becomes a publication claim
   without linked analysis, denominator, uncertainty, quality findings, and
   limitations.
8. **Clean-room independence.** Source code, source paths, wrappers, and bridge
   modules are not retained. Concepts are rewritten behind project-owned
   contracts.

## Architecture

```text
biomed_workbench/
  kernel/
    artifacts.py       typed scientific data and result artifacts
    context.py         project, objective, constraints, and data inventory
    hypotheses.py      hypothesis and alternative-explanation ledger
    evidence.py        normalized evidence and claim links
    decisions.py       append-only scientific decisions and revisions
    state.py           canonical state serialization and replay

  modules/
    contract.py        module manifest and runtime contracts
    registry.py        discovery, validation, indexing, and version selection
    compatibility.py   input, dependency, policy, and quality compatibility
    execution.py       bounded invocation and normalized result handling
    <module-id>/
      module.json
      implementation.py
      tests/
      references/      optional concise scientific guidance

  orchestration/
    intent.py          structured intent and project-context extraction
    graph.py           capability graph and dependency resolution
    planner.py         serial, parallel, and mixed DAG construction
    controller.py      execute, inspect, revise, resume, and stop decisions
    quality.py         cross-module quality and inference gates
    interpretation.py  hypothesis adjudication and alternative explanations

  delivery/
    claims.py          claim-evidence matrix
    figures.py         panel-level evidence and statistical contracts
    manuscript.py      article architecture and section readiness
    review.py          independent review, synthesis, and revision actions
    package.py         reproducibility and final-delivery manifest

  assistant.py         one Codex-facing research cycle
```

The existing domain specification files are a migration stage. They will be
converted to independent module manifests. Domain labels remain searchable
metadata, not physical ownership boundaries or hardcoded workflow stages.

## Module Contract

Every module is an independently installable scientific capability unit with a
closed `module.json` manifest.

Required identity fields:

- `id`: stable source-neutral identifier;
- `version`: semantic module version;
- `title` and `description`;
- `module_type`: `data_source`, `transform`, `analysis`, `validation`,
  `interpretation`, `design`, or `delivery`;
- `domains`: one or more scientific domains;
- `intents`: structured intents and multilingual phrases used to build the
  search index automatically;
- `entrypoint`: project-owned callable;
- `execution`: Python, command, service, or workflow invocation kind with a
  bounded timeout and maximum normalized output size;
- `maturity`: `experimental`, `validated`, or `reference`.

Required scientific fields:

- `questions`: scientific questions the module can help answer;
- `input_artifacts`: typed inputs, accepted format names and versions,
  compression, indexes, coordinate systems, genome-build policy, processing
  levels, and required metadata;
- `output_artifacts`: typed outputs with the same machine-readable format
  contract and their interpretation scope;
- `preconditions`: design, data, and evidence conditions that must hold;
- `assumptions`: model and biological assumptions;
- `quality_gates`: checks that determine whether output is interpretable;
- `limitations`: prohibited interpretations and known blind spots;
- `evidence_effects`: hypothesis relations the result may support;
- `alternatives`: modules that answer the same intent by another method;
- `complements`: modules that provide orthogonal evidence;
- `tool_requirements`: upstream tools or public services, exact validated
  versions, machine-checkable compatibility rules, and bounded version probes;
- `dependencies`: Python, R, Java, system-program, database, and service
  dependencies with required or optional status and compatible versions;
- `compatibility_matrix`: validated combinations of module, upstream tool,
  dependency, input format, output format, and platform;
- `access`, `mutability`, and credential requirements.

Required engineering fields:

- a closed JSON input schema and output schema;
- deterministic error classes;
- timeout and result-size bounds where applicable;
- unit, contract, and end-to-end fixtures;
- provenance and license notes for conceptual influences;
- compatibility range with the plugin kernel.

## Tool, Dependency, and Format Compatibility

Bioinformatics modules must treat software and format versions as scientific
inputs. A module cannot claim support based only on a package name.

Every upstream tool requirement declares:

- canonical tool name and distribution or executable identity;
- ecosystem: Python, R, Java, system executable, web service, or database;
- exact versions exercised by module test fixtures;
- authoritative version source and the date the compatibility claim was verified;
- machine-readable allowed versions derived only from validated evidence;
- a bounded version probe and expected parse rule;
- version-specific parameter, API, default, field, and behavior differences;
- whether absence or mismatch blocks execution or activates a named alternative.

Every dependency declares its package or executable identity, ecosystem,
required or optional status, version rule, tested versions, purpose, and known
conflicts. Optional dependencies may enable a branch but cannot silently change
the scientific method or output schema.

Every artifact port declares:

- format name and format or schema version;
- text, binary, sparse, or container representation;
- supported compression and required companion indexes;
- sample and feature orientation;
- coordinate convention, reference assembly, annotation release, identifier
  namespace, and processing level where applicable;
- required metadata fields and output guarantees;
- compatible upstream and downstream module versions.

Before execution, the compatibility checker compares actual tools,
dependencies, and artifact metadata with a validated compatibility-matrix row.
An exact validated row permits execution. A documented range permits execution
only when the module contains regression evidence for that range. Unknown or
mismatched versions are blocked or routed to an explicitly validated
alternative; optimistic version guessing is forbidden.

Every execution result records module version, upstream tool versions,
dependency versions, selected compatibility row, input format metadata,
parameters, and output format metadata. Credentials and machine paths remain
excluded from this record.

Updating a supported tool or format requires a module version change,
version-specific fixtures, input-output regression, scientific-quality checks,
and representative end-to-end validation before rebuilding the registry index.
Compatibility claims must cite official upstream documentation or a released
format specification; secondary summaries cannot establish support.

## Adding a Future Tool

Adding a new bioinformatics tool requires only:

1. create one module directory;
2. declare its scientific and engineering contract in `module.json`;
3. declare exact tested tool, dependency, and input-output format compatibility;
4. implement the source-neutral entrypoint or established-tool invocation;
5. provide version-specific unit, contract, format, and representative
   end-to-end fixtures;
6. run `tools/validate_module.py <module-directory>`;
7. rebuild the generated capability index.

The registry discovers the module, validates it, and adds its intents,
artifacts, preconditions, alternatives, complements, and quality gates to the
capability graph. The central router and assistant code remain unchanged.

Modules can be added in the main repository or through a future extension
package that follows the same contract. Untrusted extension modules are not
executed until their manifest, schema, entrypoint, permissions, and tests pass.

## Scientific Artifact Types

Modules communicate through typed artifacts rather than module-specific
dictionaries. Initial artifact families include:

- research objective, hypothesis set, and experimental design;
- literature corpus, database record set, identifier map, and evidence table;
- sample manifest, feature matrix, count matrix, interval set, sequence set,
  image collection, clinical cohort, and assay table;
- quality report, normalized matrix, embedding, cluster assignment, annotation,
  contrast result, enrichment result, trajectory, network, structure, and
  candidate design;
- protocol, validation design, claim set, figure specification, manuscript,
  reviewer report, revision ledger, patent disclosure, and delivery package.

Each artifact records a stable ID, artifact type, schema version, producing
module, source inputs, scientific scope, coordinate or identifier system,
biological denominator, processing level, quality status, and content digest.
For bioinformatics formats it also records format version, compression, index
companions, reference assembly, annotation release, and producer tool version.

## Dynamic Capability Graph

At registry build time, the engine creates a graph:

- module nodes;
- artifact-type nodes;
- intent and question nodes;
- `consumes`, `produces`, `requires`, `alternative-to`, `complements`, and
  `validates` edges.

At runtime, the planner overlays project context:

- objective and proposed hypotheses;
- available artifacts and their quality state;
- species, tissue, assay, cohort, and study design;
- user constraints and requested deliverables;
- previously completed actions and unresolved findings.

Planning is then a constrained graph search from available artifacts to the
evidence and deliverables required by the objective. Candidate paths are ranked
by scientific validity, directness, orthogonality, maturity, data compatibility,
credential burden, and unresolved quality risk. Convenience cannot outrank a
required scientific precondition.

## Research Cycle

The unified assistant advances a project through a general cycle:

1. **Frame** the scientific question, scope, stakeholders, and deliverables.
2. **Audit** study design, data inventory, identifiers, metadata, and privacy.
3. **Hypothesize** with predicted, disconfirming, and alternative observations.
4. **Plan** a capability DAG from the current state and available modules.
5. **Execute** independent branches in parallel and dependent branches in order.
6. **Validate** every result against module and cross-project quality gates.
7. **Interpret** evidence against hypotheses and alternative explanations.
8. **Revise** hypotheses, parameters, annotations, contrasts, or the DAG through
   an explicit decision record.
9. **Synthesize** claims, figures, methods, limitations, and next experiments.
10. **Review** technical validity, significance, readability, reproducibility,
    ethics, and claim faithfulness.
11. **Deliver** a reproducible project package or continue the cycle.

No stage is tied to one data modality. The DAG is generated from artifact and
evidence needs. For a multiomics project, RNA and ATAC branches may run in
parallel. For a paper-to-patent project, evidence verification and disclosure
analysis may run in parallel before claim drafting. For a clinical imaging
project, image quantification can precede cohort statistics and manuscript
review.

## Hypothesis and Decision Model

Every hypothesis declares:

- a falsifiable statement and biological scope;
- experimental unit, comparison, direction, and expected observations;
- disconfirming observations and alternative explanations;
- required evidence types and minimum orthogonality;
- permitted claim strength;
- status: `proposed`, `active`, `supported`, `weakened`, `refuted`, or
  `inconclusive`;
- supporting, conflicting, and missing evidence IDs;
- revision lineage.

Every plan revision records the triggering finding, affected artifacts,
hypotheses and claims, superseded actions, replacement actions, and whether
prior results remain valid. Refuted hypotheses remain in history.

## Quality and Self-Correction

Module findings use `info`, `warning`, `major`, or `fatal` severity.

- `fatal` blocks the affected path because required inputs, design, integrity,
  or permissions are invalid.
- `major` prevents interpretation until a remediation or explicit scope change.
- `warning` permits bounded interpretation with a sensitivity check or named
  limitation.
- `info` preserves context and provenance.

Cross-module gates detect incompatible identifiers, genome builds, units,
sample denominators, preprocessing levels, duplicated evidence, circular
validation, pseudoreplication, complete confounding, outcome-informed threshold
changes, unsupported causal language, and claim-evidence drift.

Conflicting results do not get averaged into agreement. The controller creates
actions to examine timing, power, measurement scope, annotation, model
assumptions, data quality, and alternative biology before adjudication.

## Unified User Experience

The only user-facing skill remains `biomed-workbench`. Codex receives a project
request in natural language, inspects the available data and prior state, and
uses the registry to propose and execute the next scientifically justified
actions. Users do not need to know module IDs or invoke slash commands.

The assistant explains:

- the current scientific question and active hypotheses;
- which modules were selected and why;
- which actions can run in parallel;
- what evidence each action is expected to produce;
- which gates passed or failed;
- how results changed the hypotheses and next plan;
- what remains before a defensible conclusion or delivery.

## Source Capability Assimilation

The existing 89,314-file ledger remains the source of truth. Scientifically
relevant source files are assigned to one or more module families. Generated,
vendored, binary, infrastructure, and sensitive files retain explicit exclusion
decisions rather than being counted as implemented scientific capabilities.

Assimilation is complete only when every reasonable source capability has one
of these evidence-backed outcomes:

- implemented as a validated module;
- subsumed by a broader validated module with equivalent or stronger behavior;
- retained as scientific guidance or quality gates;
- explicitly excluded with a product-boundary or scientific-validity reason.

File counts alone do not prove functional coverage. The release report must map
source capability families to module contracts, tests, and end-to-end scenarios.

## Verification Scenarios

The engine requires diverse end-to-end scenarios:

1. paired and unpaired single-cell RNA and ATAC research;
2. bulk expression from design audit through differential analysis and writing;
3. variant evidence from databases through cohort interpretation;
4. molecular design through sequence checks and wet-lab validation planning;
5. microscopy quantification combined with molecular or clinical evidence;
6. clinical cohort analysis with privacy, reporting, and safety gates;
7. literature-to-hypothesis-to-experiment planning;
8. manuscript-to-review-to-revision-to-delivery;
9. paper or technical disclosure to patent-ready research package;
10. registration of a previously unknown mock bioinformatics module followed by
    automatic discovery and use without central router modification.

Every scenario must include at least one failed gate, plan revision, hypothesis
status change, and final evidence ledger. Together they verify single, serial,
parallel, and mixed module execution.

## Error and Permission Model

Schema violations fail before execution. Scientific incompatibilities return
structured findings and a recoverable state. Unexpected failures disclose the
module ID and safe error class without secrets or machine paths. Completed
upstream work is preserved when a downstream branch fails.

Tool execution is also blocked before invocation when no validated
compatibility-matrix row matches the detected tool, dependency, and artifact
versions. The finding names every mismatch and the validated alternatives.

Read-only modules run without mutation permission. Modules that create project
artifacts require explicit output permission and may write only inside the
declared project output root. Credentials are module-scoped, optional where
possible, and never persisted in project state or reports.

## Acceptance Criteria

The modular engine is complete only when:

- every current capability is represented by a valid independent module;
- every bioinformatics module declares tested tools, dependencies, formats, and
  a machine-validated compatibility matrix;
- a newly added fixture module is discovered without editing kernel or router;
- the planner creates valid single, serial, parallel, and mixed DAGs from module
  contracts and project context;
- result evidence deterministically changes hypotheses and future actions;
- fatal and major gates prevent invalid interpretation;
- one module can be replaced by a declared alternative without state loss;
- cross-domain scenarios reach claims, figures, review, revision, and delivery;
- the 89,314-file assimilation report accounts for all inclusion and exclusion
  decisions without overstating equivalence;
- module, contract, end-to-end, replay, independence, and release tests pass;
- unsupported tool or format versions are proven to block before execution;
- Codex official plugin and skill validators pass;
- installation from GitHub exposes one skill and the complete generated module
  index in a new conversation.
