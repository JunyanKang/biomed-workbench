# Biomed Workbench Deep Capability Fusion Design

## Objective

Biomed Workbench v0.2.0 will be a self-contained, source-neutral biomedical capability system rather than a router over source-specific adapters and reference indexes. Every operational catalog entry must resolve to a local implementation, a tested optional runtime command, or a substantive local workflow contract. Entries that only advertise an upstream capability without making it usable will be removed.

The plugin continues to expose exactly one Codex skill: `biomed-workbench`.

## Non-Negotiable Boundaries

- Operational paths, module names, catalog fields, router output, and README architecture must not use upstream project names as classifications.
- `tools/adapters/` and all source-named bridge modules are removed.
- `BIOMNI_SOURCE_ROOT`, `OPENSCIENCE_SOURCE_ROOT`, `CLAUDE_SCIENCE_*`, and equivalent source-checkout environment variables are removed.
- Upstream project names and commits may appear only in `NOTICE.md` and `references/provenance.json`, where attribution and license compliance require them.
- Scientific model identifiers remain valid only when the corresponding implementation can run locally under a clear redistribution and usage license.
- Vendor-hosted model APIs, vendor registry credentials, and paid inference services are outside the core architecture.
- No credential value is stored, printed, committed, or included in error messages.
- Third-party protocol text, restricted datasets, model weights, caches, and generated environments are not copied into the repository.
- Catalog size is an outcome, not a target. A smaller executable catalog is preferable to a larger catalog containing ghost capabilities.

## Target Architecture

```text
biomed-workbench/
  biomed_workbench/
    __init__.py
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
    mutability: Literal["read_only", "writes_output", "changes_environment", "starts_service"]
```

Operational records do not contain `source`, `source_path`, source-specific kinds, or source-specific run policies. Provenance is maintained separately and joined only for release audits.

The catalog generator imports every registered capability and fails when an entrypoint cannot be resolved. `run_tool.py` accepts JSON input, validates it against `input_schema`, checks requirements, invokes the entrypoint, and emits a structured result. Mutating operations require explicit user intent and may never be selected solely because they scored highly in routing.

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

The router scores scientific intent, input type, runtime readiness, and capability confidence. It must distinguish:

- scientific work that can run immediately;
- local GPU/container work requiring runtime readiness;
- cluster work requiring explicit configuration;
- model work that has no acceptable local backend and therefore must be rejected rather than rerouted to a paid service;
- procedural workflow guidance.

When multiple local backends can satisfy a request, the router prefers an already-ready backend and reports the chosen execution mode. It never starts containers, downloads model weights, or submits cluster work without explicit user intent.

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

## Delivery Sequence

The work is delivered as four independently testable phases:

1. **Kernel fusion:** package, capability schema, runner, generic runtime discovery, catalog migration, bridge removal.
2. **Scientific fusion:** portable function migration, executable evidence clients, removal of ghost entries.
3. **Accelerated compute fusion:** local model backends, composite workflows, open genomics tools, and GPU/container/SLURM command backends.
4. **Product surface:** router tuning, icon and diagrams, README rebuild, v0.2.0 migration notes, cache reinstall, GitHub release.

Each phase uses test-first implementation and leaves the plugin installable. The v0.2.0 release is created only after all four phases pass release validation from both the repository and installed Codex cache.

## Acceptance Criteria

- A repository-wide scan finds no bridge/adaptor architecture or operational source-project naming.
- The screenshot state that motivated this refactor cannot recur because release validation forbids it.
- A user invokes only `biomed-workbench`; routing can select one or several scientific, publication, CPU, local-model, GPU, or cluster capabilities.
- Catalog claims and executable reality match.
- The project installs from GitHub without any upstream checkout path.
- The plugin remains useful without any vendor-hosted model account or credential.
- The README and icon describe Biomed Workbench itself, not the projects it absorbed.
