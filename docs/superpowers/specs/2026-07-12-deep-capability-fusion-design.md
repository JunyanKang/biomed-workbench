# Biomed Workbench Deep Capability Fusion Design

## Objective

Biomed Workbench v0.2.0 will be a Codex research-assistant plugin for biomedical scientists. The user gives it a scientific objective, data, paper, observation, or draft; the assistant scopes the question, gathers evidence, selects and executes appropriate capabilities, interprets results, records limitations, and produces the requested research artifact. It is not presented as a tool catalog and does not stop after returning tool IDs.

Internally, it is a self-contained, source-neutral biomedical capability system rather than a router over source-specific adapters and reference indexes. Every operational catalog entry must resolve to a local implementation, a tested optional runtime command, a public scientific service, or a substantive local workflow contract. Entries that only advertise an upstream capability without making it usable will be removed.

The plugin continues to expose exactly one Codex skill: `biomed-workbench`.

## Product Definition

The assistant supports the research lifecycle as one coherent interaction:

1. **Frame:** convert a broad request into a scientific question, constraints, inputs, and success criteria.
2. **Plan:** build an evidence and analysis plan, identifying serial dependencies and independent work that can run in parallel.
3. **Investigate:** search literature and biological databases, inspect supplied data, and run compatible analyses.
4. **Design:** propose computational or experimental validation with controls, assumptions, and decision points.
5. **Interpret:** connect outputs to the original question, distinguish results from inference, and surface uncertainty.
6. **Deliver:** produce analysis artifacts, figures, protocols, manuscripts, reviews, patents, or presentations as requested.
7. **Audit:** preserve evidence links, parameters, software/runtime facts, output paths, and unresolved limitations.

The router and catalog are internal implementation details. User-facing responses describe the scientific plan, work performed, evidence, outputs, and limitations rather than internal workflow names.

## Non-Negotiable Boundaries

- Operational paths, module names, catalog fields, router output, and README architecture must not use upstream project names as classifications.
- `tools/adapters/` and all source-named bridge modules are removed.
- `BIOMNI_SOURCE_ROOT`, `OPENSCIENCE_SOURCE_ROOT`, `CLAUDE_SCIENCE_*`, and equivalent source-checkout environment variables are removed.
- Upstream project names and commits may appear only in `NOTICE.md` and `references/provenance.json`, where attribution and license compliance require them.
- Scientific model identifiers remain valid only when the corresponding implementation can run locally under a clear redistribution and usage license.
- The default assistant must work without any user-supplied API key.
- Codex is the only general-purpose language-model reasoning layer. Upstream code that calls a model vendor, manages model-provider tokens, or implements a second agent loop is rewritten as Codex skill guidance, typed tool contracts, deterministic local functions, or removed.
- A small allowlist of optional scientific API credentials is permitted when it materially expands evidence or controlled-data access. Model-vendor inference credentials are outside the initial allowlist.
- No credential value is stored, printed, committed, or included in error messages.
- Third-party protocol text, restricted datasets, model weights, caches, and generated environments are not copied into the repository.
- Catalog size is an outcome, not a target. A smaller executable catalog is preferable to a larger catalog containing ghost capabilities.
- Every file in the three original source roots must be read and classified before capability migration is considered complete. Later-added Nature and accelerated-compute sources use the same exhaustive process.

## Exhaustive Source Assimilation

Source assimilation precedes implementation selection. The process enumerates every regular file and symlink, reads every file as bytes, computes a content hash, identifies its format, and produces a safe semantic record:

- source code: module purpose, public symbols, imports, side effects, command surfaces, and reusable algorithms;
- documentation/prompts: workflow rules, scientific assumptions, output contracts, and reusable guidance;
- structured data/notebooks: schema, dimensions or cell structure, declared dependencies, and role;
- binary/runtime artifacts: format, package or runtime role, architecture metadata where safely readable, and whether they are generated;
- sensitive/configuration material: classification and redacted structural summary only, never content or secret values.

No file may disappear through an unrecorded ignore rule. Every record receives one disposition: `integrate`, `rewrite`, `merge`, `provenance_only`, `generated_runtime`, `restricted`, `sensitive`, or `obsolete`. Generated/runtime and restricted files are still read and understood; their disposition explains why their bytes are not copied.

The exhaustive manifest is local release evidence because it may contain private runtime filenames and hashes. It is stored under the ignored `.source-audit/` directory. The public repository contains a redacted summary with source revision, total files, total bytes, format counts, disposition counts, capability mappings, and a deterministic root digest proving that the local manifest covered the inspected snapshot.

Completion requires exact set equality between the live source inventory and the local manifest for each inspected root. Counts or sampling are insufficient.

## Target Architecture

```text
biomed-workbench/
  biomed_workbench/
    __init__.py
    assistant.py
    research.py
    catalog.py
    router.py
    runner.py
    models.py
    errors.py
    domains/
      evidence/
      omics/
      molecular_design/
      imaging/
      clinical/
      wetlab/
      publication/
    services/
      http.py
      credentials.py
      model_backends.py
      containers.py
      schedulers.py
      environments.py
    workflows/
      structure_prediction.py
      drug_discovery.py
      sequence_design.py
      accelerated_genomics.py
      publication.py
  skills/
    biomed-workbench/
      SKILL.md
  references/
    capabilities/
    provenance.json
  tools/
    route_task.py
    search_tools.py
    run_tool.py
    validate_workbench.py
```

The scripts under `tools/` remain thin compatibility entrypoints. All behavior lives in the `biomed_workbench` package.

## Capability Contract

Each capability is represented by a validated record with these fields:

```python
@dataclass(frozen=True)
class Capability:
    id: str
    workflow: str
    kind: Literal["python", "command", "service", "workflow"]
    title: str
    description: str
    entrypoint: str
    input_schema: dict[str, object]
    requirements: tuple[str, ...]
    access: Literal["offline", "public_api", "optional_api", "local_runtime"]
    mutability: Literal["read_only", "writes_output", "changes_environment", "starts_service"]
```

Operational records do not contain `source`, `source_path`, source-specific kinds, or source-specific run policies. Provenance is maintained separately and joined only for release audits.

The catalog generator imports every registered capability and fails when an entrypoint cannot be resolved. `run_tool.py` accepts JSON input, validates it against `input_schema`, checks requirements, invokes the entrypoint, and emits a structured result. Mutating operations require explicit user intent and may never be selected solely because they scored highly in routing.

`assistant.py` owns the research-assistant loop. `research.py` defines the structured research record: objective, inputs, plan, evidence ledger, executed capabilities, artifacts, conclusions, limitations, and next decisions. Records are written only into the user's active project when the task benefits from reproducibility; ordinary questions do not create files unnecessarily.

## API Policy

### Codex-native model integration

Biomed Workbench does not call a second general-purpose LLM from inside the plugin. Codex owns scientific reasoning, task decomposition, tool selection, synthesis, and user interaction. Source files for OpenAI, Anthropic, NVIDIA-hosted inference, generic model endpoints, provider token management, and nested agent loops are assimilated for their workflow ideas but their execution path is rewritten to Codex-native skill instructions and structured tool inputs/outputs. They are never copied as another model client.

This boundary does not prohibit open scientific models running locally. A local structure, sequence, imaging, or omics model is a scientific compute backend, not a replacement reasoning agent, and remains subject to the license and reproducibility gates below.

Zero-key operation is the baseline. PubMed/PMC, Europe PMC, Crossref, OpenAlex, UniProt, RCSB PDB, Ensembl, ClinicalTrials.gov, ChEMBL, PubChem, and other stable public endpoints use their documented unauthenticated routes where available.

The initial optional credential allowlist contains at most three credential families:

1. `NCBI_API_KEY`: optional higher request limits across NCBI services.
2. `ELSEVIER_API_KEY`: optional Scopus or ScienceDirect metadata access for users who already hold authorized access.
3. `SYNAPSE_AUTH_TOKEN`: optional controlled or authenticated Synapse dataset access.

Rules for optional APIs:

- Missing credentials disable only the affected capability; they never block the assistant as a whole.
- The assistant must explain why an optional API would help before asking the user to configure it.
- One credential family serves all capabilities from that service; duplicate variables are forbidden.
- Credentials are read from the environment or operating-system secret facilities, never project files.
- Release validation rejects undeclared credential names. Expanding the allowlist requires an explicit design decision and documentation change.
- Scientific reasoning, writing, routing, local model execution, and core literature/database search must not require an additional model-provider API.

## Domain Implementation Fusion

### Portable scientific functions

Portable implementations from the existing source snapshots are moved into the relevant domain modules and refactored until they import only Workbench utilities and declared third-party packages. The old 224 function descriptions are not carried forward automatically.

Each function is classified as one of:

- **Portable:** copied and refactored into a local callable with tests.
- **Reimplemented:** rewritten around a stable public API or maintained Python package.
- **Workflow:** retained as substantive procedural guidance when execution inherently depends on user infrastructure or scientific judgment.
- **Removed:** excluded when it depends on unavailable private data, restricted content, or unbounded generated code.

Protocol search is reimplemented against authorized public APIs. Addgene, Thermo Fisher, or other third-party protocol bodies are not vendored.

### Evidence connectors

The 42 connector placeholders are replaced by Python clients grouped by scientific domain, not upstream origin. Shared HTTP behavior includes timeout, retries, rate-limit handling, user agent, response-size bounds, and normalized errors. Public unauthenticated connectors are executable by default. Connectors requiring credentials declare the environment variable without reading it until invocation.

Duplicate database access paths are consolidated. For example, PubMed is one capability with search and fetch operations rather than separate source-derived entries.

### Runtime execution

The source-specific runtime adapter is replaced by generic environment discovery:

- `BIOMED_PYTHON` overrides the Python executable.
- `BIOMED_RSCRIPT` overrides the R executable.
- PATH discovery is the default.
- Docker, generic GPU availability, SLURM, and local model services are detected through explicit runtime probes.

Runtime status reports capabilities such as `python`, `r`, `docker`, `gpu`, `slurm`, and locally available scientific model commands; it does not report upstream application installation state.

## Accelerated Model And Compute Fusion

The installed accelerated life-science toolkit is absorbed by capability rather than by skill name.

### Local model backends

A single `ModelBackend` contract handles:

- local Python packages, command-line tools, and containers;
- explicit executable and model-weight discovery;
- backend-specific timeouts and resource requirements;
- JSON, text, structure, and archive artifacts;
- response validation and safe output paths.

Model definitions provide command construction, input validation, output parsing, license status, installation guidance, and a scientific validation checklist. Candidate implementations include local Boltz, DiffDock, ProteinMPNN, RFdiffusion, OpenFold, and other independently installable models. A candidate is included only after its code, weights, and required datasets pass the license and reproducibility gate. Vendor-only models and endpoints are omitted.

### Composite workflows

The following become first-class Workbench workflows rather than exposed subskills:

- MSA search followed by structure prediction.
- Structure prediction, docking, molecule generation, and candidate ranking.
- RFdiffusion backbone generation followed by ProteinMPNN sequence design and structure validation.
- Local sequence generation or variant scoring followed by evidence and validation checks.

Each workflow persists an execution manifest containing inputs, model/backend identifiers, parameters, artifact paths, validation results, and failures. Secrets are never written to the manifest.

### Local GPU, container, and cluster execution

- Accelerated genomics is implemented with independently runnable tools such as DeepVariant, BWA-MEM2, GATK, samtools, and compatible workflow engines. Proprietary command suites are not required.
- Protein-complex design and molecular pretraining workflows retain useful setup, target, run, monitor, and evaluate phases only when those phases can be mapped to open local implementations.
- SLURM support is implemented through a generic scheduler backend; cluster configuration remains user-owned.
- Optional Python acceleration libraries are discovered by import and used only when their installation and license are independently acceptable.

## Routing Behavior

The assistant first decides what scientific work is needed; the router then scores scientific intent, input type, runtime readiness, and capability confidence. It must distinguish:

- scientific work that can run immediately;
- local GPU/container work requiring runtime readiness;
- cluster work requiring explicit configuration;
- model work that has no acceptable local backend and therefore must be rejected rather than rerouted to a paid service;
- procedural workflow guidance.

When multiple local backends can satisfy a request, the router prefers an already-ready backend and reports the chosen execution mode. It never starts containers, downloads model weights, or submits cluster work without explicit user intent.

After routing, the assistant continues through execution and synthesis. A routing JSON document is diagnostic output for developers, not a successful answer to a research request.

## Repository Cleanup

The following are removed or replaced:

- `tools/adapters/`
- `references/biomni_functions.md`
- `references/database_connectors.md`
- `references/runtime_adapters.md`
- `references/source_file_audit.json`
- `references/source_file_audit.md`
- source-specific catalog kinds and run policies
- source-specific environment variables and README sections

`references/source_manifest.json` is replaced by `references/provenance.json`. Provenance records repository URL, inspected commit, license, integration method, and affected capability IDs. It is never consumed by routing or execution.

## Validation And Testing

Release validation must prove all of the following:

1. Exactly one visible skill exists.
2. Every operational catalog entry resolves to a local callable, command builder, public scientific service client, local model definition, or local workflow document.
3. No operational path or catalog field contains the forbidden source project names.
4. No source-root environment variable remains.
5. No credential-like value exists in tracked files.
6. No vendor-hosted model credential or paid inference dependency exists in the operational package.
7. Input validation rejects malformed sequences, structures, SMILES, file paths, and unsupported parameters before network or process execution.
8. Command builders are tested without launching Docker, SLURM, GPU jobs, or model downloads.
9. Network clients use mocked contract tests by default. Live smoke tests are opt-in and environment-gated.
10. Router regression scenarios cover single, serial, parallel, mixed, CPU, local GPU, unavailable-backend, and cluster plans.
11. README installation commands and plugin cache validation remain correct.
12. End-to-end assistant tests begin with a scientific objective and finish with an evidence-backed answer or artifact, not a list of internal tools.
13. The plugin passes its core research-assistant test suite with none of the optional API credentials configured.

## Delivery Sequence

The work is delivered as four independently testable phases:

1. **Assistant kernel:** research record, assistant loop, capability schema, runner, generic runtime discovery, catalog migration, bridge removal.
2. **Scientific fusion:** portable function migration, executable evidence clients, removal of ghost entries.
3. **Accelerated compute fusion:** local model backends, composite workflows, open genomics tools, and GPU/container/SLURM command backends.
4. **Product surface:** router tuning, icon and diagrams, README rebuild, v0.2.0 migration notes, cache reinstall, GitHub release.

Each phase uses test-first implementation and leaves the plugin installable. The v0.2.0 release is created only after all four phases pass release validation from both the repository and installed Codex cache.

## Acceptance Criteria

- A repository-wide scan finds no bridge/adaptor architecture or operational source-project naming.
- The screenshot state that motivated this refactor cannot recur because release validation forbids it.
- A user invokes only `biomed-workbench`; routing can select one or several scientific, publication, CPU, local-model, GPU, or cluster capabilities.
- A broad research request is carried from framing through evidence, execution, interpretation, and delivery without requiring the user to invoke subskills or inspect the tool catalog.
- Catalog claims and executable reality match.
- The project installs from GitHub without any upstream checkout path.
- The plugin remains broadly useful with zero optional API credentials; no more than three documented credential families exist in v0.2.0.
- The README and icon describe Biomed Workbench itself, not the projects it absorbed.
