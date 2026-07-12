# Architecture

Biomed Workbench exposes one Codex skill and discovers scientific capabilities from independent, versioned modules. A module owns its scientific contract; the router, runner, catalog projection, and assistant contain no module-specific registration tables.

## Runtime Layers

1. `skills/biomed-workbench/SKILL.md` is the only user-facing Codex entry.
2. `biomed_workbench/modules/builtin/<module-id>/module.json` is the source of truth for every built-in capability.
3. `biomed_workbench/modules/contract.py` validates scientific, execution, version, dependency, format, and provenance contracts.
4. `biomed_workbench/modules/registry.py` discovers modules recursively and rejects duplicate IDs or unresolved relationships.
5. `biomed_workbench/router.py` ranks intents, questions, artifact types, and domains read from manifests.
6. `biomed_workbench/runner.py` validates structured input and invokes resolved entrypoints.
7. `biomed_workbench/catalog.py` provides the v0.2 compatibility projection; it does not define or load a second capability registry.
8. `biomed_workbench/modules/index.json` and `tools/catalog.json` are generated release artifacts and are never edited manually.

The plugin does not manage CPUs, GPUs, containers, Slurm, remote compute, or local model infrastructure.

## Module Contract

Every `module.json` is closed and versioned. It declares:

- identity, semantic module version, scientific domains, intents, questions, maturity, entrypoint, and kernel compatibility;
- typed input and output artifacts, processing levels, required metadata, and closed JSON input/output schemas;
- preconditions, assumptions, limitations, evidence effects, alternatives, complements, and blocking quality gates;
- each upstream tool's exact tested versions, allowed ranges, authoritative version source, verification date, version probe, known version differences, platform scope, and mismatch policy;
- each Python, R, Java, system, service, database, or runtime dependency's tested versions, allowed ranges, source, purpose, conflicts, and platform scope;
- input/output format names and versions, representation, compression, required indexes, coordinate systems, genome builds, annotation releases, and orientations;
- explicit compatibility rows joining one module version to validated tool, dependency, platform, and input/output format combinations;
- access, mutation, credential, timeout, output-size, license, and clean-room provenance boundaries.

An undeclared or untested tool, dependency, format, genome build, coordinate system, or compatibility combination blocks execution. A newer version is not assumed compatible until its independent regression and end-to-end evidence is recorded in a new module version.

## Add A Module

Implement an importable, bounded scientific function, then prepare a complete creation request:

```json
{
  "manifest": {"schema_version": 1, "id": "new-analysis", "version": "1.0.0"},
  "tests": [
    {
      "name": "representative-case",
      "input": {},
      "expected_subset": {}
    }
  ]
}
```

The abbreviated object above only illustrates the envelope. Use an existing `module.json` as the field-complete template; omitted contract fields are rejected.

```bash
python3 tools/create_module.py request.json --registry-root /path/to/module-registry
python3 tools/validate_module.py /path/to/module-registry/new-analysis
```

Creation occurs in a temporary same-filesystem directory. The validator checks package shape, permissions, symbolic links, local path traces, manifest closure, current kernel compatibility, entrypoint resolution, dependency and format evidence, compatibility rows, test schemas, execution timeout, output size, output schema, and expected results. Only a fully valid package is atomically renamed into the registry; failure leaves no partial module.

Adding a module must not require edits to `catalog.py`, `router.py`, `runner.py`, the assistant, or the generated indexes. Built-in development places the validated package under `biomed_workbench/modules/builtin/`, then rebuilds generated projections:

```bash
python3 tools/build_module_index.py
python3 tools/build_catalog.py
python3 tools/validate_workbench.py --release
python3 -m unittest discover -s tests -p 'test*.py'
```

## Compatibility Changes

- Adding a tested version requires an authoritative version source, a version probe, exact compatibility-row coverage, input/output regression fixtures, and representative end-to-end validation.
- Changing required input fields, units, coordinate conventions, output meaning, defaults, or quality interpretation requires a module version update.
- Removing an ID or breaking the v0.2 compatibility projection requires a documented plugin-level migration.
- Optional credentials must remain in the project allowlist. `NCBI_API_KEY` is currently the only allowed credential.
- Generated indexes must exactly match recursive manifest discovery and are checked by digest during release validation.

## Release Flow

The plugin manifest is the package version source. Publish only when rebuilding the generated index and catalog produces no diff, all unit/contract/end-to-end/release tests pass, and release validation confirms the single skill, 48 built-in modules, complete compatibility evidence, source-neutral paths, and absence of legacy registration surfaces.

For local Codex iteration:

```bash
python3 tools/prepare_local_update.py
codex plugin add biomed-workbench@biomed-workbench
```

Start a new Codex task after reinstalling so updated Skill metadata and module indexes are loaded.
