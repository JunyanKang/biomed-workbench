# Biomed Workbench Deep Capability Fusion Design

## Objective

Biomed Workbench v0.2.0 will be a self-contained, source-neutral biomedical capability system rather than a router over source-specific adapters and reference indexes. Every operational catalog entry must resolve to a local implementation, a tested optional runtime command, or a substantive local workflow contract. Entries that only advertise an upstream capability without making it usable will be removed.

The plugin continues to expose exactly one Codex skill: `biomed-workbench`.

## Non-Negotiable Boundaries

- Operational paths, module names, catalog fields, router output, and README architecture must not use upstream project names as classifications.
- `tools/adapters/` and all source-named bridge modules are removed.
- `BIOMNI_SOURCE_ROOT`, `OPENSCIENCE_SOURCE_ROOT`, `CLAUDE_SCIENCE_*`, and equivalent source-checkout environment variables are removed.
- Upstream project names and commits may appear only in `NOTICE.md` and `references/provenance.json`, where attribution and license compliance require them.
- Product and runtime identifiers that users must actually configure remain valid: model names such as Boltz2, DiffDock, OpenFold3, Evo2, ProteinMPNN, RFdiffusion, Parabricks, and environment variables such as `NVIDIA_API_KEY` and `NGC_API_KEY`.
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
      hosted_models.py
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
    kind: Literal["python", "command", "hosted", "workflow"]
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
- Docker, NVIDIA Container Toolkit, Parabricks, SLURM, and local model services are detected through explicit runtime probes.

Runtime status reports capabilities such as `python`, `r`, `docker`, `gpu`, `slurm`, and `hosted_model_key`; it does not report upstream application installation state.

## Accelerated Model And Compute Fusion

The installed accelerated life-science toolkit is absorbed by capability rather than by skill name.

### Hosted and local model service

A single `HostedModelClient` handles:

- hosted bearer authentication using `NGC_API_KEY`, falling back to `NVIDIA_API_KEY`;
- local endpoints without hosted authorization headers;
- endpoint-specific timeouts;
- JSON, text, structure, and archive artifacts;
- response validation and safe output paths.

Model definitions provide endpoint, mode support, input validator, output parser, and scientific validation checklist. Initial integrated models are Boltz2, DiffDock, Evo2, GenMol, MolMIM, MSA Search, OpenFold2, OpenFold3, ProteinMPNN, and RFdiffusion.

### Composite workflows

The following become first-class Workbench workflows rather than exposed subskills:

- MSA search followed by structure prediction.
- Structure prediction, docking, molecule generation, and candidate ranking.
- RFdiffusion backbone generation followed by ProteinMPNN sequence design and structure validation.
- Evo2 sequence generation or variant scoring followed by evidence and validation checks.

Each workflow persists an execution manifest containing inputs, model/endpoint identifiers, parameters, artifact paths, validation results, and failures. Secrets are never written to the manifest.

### Local GPU, container, and cluster execution

- Parabricks commands are generated from a typed tool registry and guarded by GPU/runtime preflight.
- Complexa and KERMT operations are represented as command workflows with setup, target, run, monitor, and evaluate phases.
- SLURM support is implemented through a generic scheduler backend; cluster configuration remains user-owned.
- cuEquivariance and nvMolKit remain optional Python capabilities discovered by import, not copied libraries.

## Routing Behavior

The router scores scientific intent, input type, runtime readiness, and capability confidence. It must distinguish:

- scientific work that can run immediately;
- hosted work requiring an available API key;
- local GPU/container work requiring runtime readiness;
- cluster work requiring explicit configuration;
- procedural workflow guidance.

When multiple backends can satisfy a request, the router prefers an already-ready backend and reports the chosen execution mode. It never silently changes from hosted to local GPU execution or starts containers and services without explicit user intent.

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
2. Every operational catalog entry resolves to a local callable, command builder, hosted model definition, or local workflow document.
3. No operational path or catalog field contains the forbidden source project names.
4. No source-root environment variable remains.
5. No credential-like value exists in tracked files.
6. Hosted clients never send authorization to local endpoints.
7. Input validation rejects malformed sequences, structures, SMILES, file paths, and unsupported parameters before network or process execution.
8. Command builders are tested without launching Docker, SLURM, GPU jobs, or paid hosted calls.
9. Network clients use mocked contract tests by default. Live smoke tests are opt-in and environment-gated.
10. Router regression scenarios cover single, serial, parallel, mixed, hosted, local GPU, and cluster plans.
11. README installation commands and plugin cache validation remain correct.

## Delivery Sequence

The work is delivered as four independently testable phases:

1. **Kernel fusion:** package, capability schema, runner, generic runtime discovery, catalog migration, bridge removal.
2. **Scientific fusion:** portable function migration, executable evidence clients, removal of ghost entries.
3. **Accelerated compute fusion:** hosted model client, model definitions, composite workflows, GPU/container/SLURM command backends.
4. **Product surface:** router tuning, icon and diagrams, README rebuild, v0.2.0 migration notes, cache reinstall, GitHub release.

Each phase uses test-first implementation and leaves the plugin installable. The v0.2.0 release is created only after all four phases pass release validation from both the repository and installed Codex cache.

## Acceptance Criteria

- A repository-wide scan finds no bridge/adaptor architecture or operational source-project naming.
- The screenshot state that motivated this refactor cannot recur because release validation forbids it.
- A user invokes only `biomed-workbench`; routing can select one or several scientific, publication, hosted-model, GPU, or cluster capabilities.
- Catalog claims and executable reality match.
- The project installs from GitHub without any upstream checkout path.
- Existing hosted NVIDIA credentials continue to work through the generic hosted-model runtime.
- The README and icon describe Biomed Workbench itself, not the projects it absorbed.
