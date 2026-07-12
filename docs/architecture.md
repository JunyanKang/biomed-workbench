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

## Stateful Research Engine

`biomed_workbench/kernel/` stores immutable project context, typed scientific artifacts, falsifiable hypotheses, directional evidence, plan nodes, DAGs, decisions, and canonical state digests. Every transition is append-only and links its prior and resulting state digest. Deserialization replays the complete event ledger; a changed payload, event order, lineage link, or digest is rejected.

`biomed_workbench/orchestration/` builds a capability graph from module manifests, searches validated artifact paths, plans single/serial/parallel/mixed DAGs, evaluates cross-module scientific quality, runs exact compatibility gates, executes bounded entrypoints, adjudicates hypotheses, and controls retries or child-plan revisions. The graph and controller contain no built-in module IDs.

Scientific artifacts preserve format and schema version, compression, orientation, companion indexes, coordinates, genome build, annotation release, identifier namespace, producer module/tool versions, experimental unit, denominator, processing level, quality status, source artifact lineage, and content digest. Unknown or incompatible metadata is not inferred from a filename.

Large scientific payloads are imported into a project-owned content-addressed store. Project state records only a payload role, SHA-256-derived relative object key, media type, byte size, and SHA-256; it never records the source path or source filename. Import rejects symlinks and non-regular files, while every resolution rechecks containment, file type, byte size, and digest. Inline artifacts keep their original canonical digest, and payload-backed artifacts bind every payload descriptor into artifact identity.

Command modules use a closed shell-free execution contract. Each command declares one versioned tool identity, complete argument tokens, input and output `port + role + runtime filename` bindings, scalar parameters, timeout, combined stdout/stderr limit, and output-payload limit. Runtime materializes only verified project payloads in an isolated working directory, inherits no credential variables, accepts only declared outputs, rechecks input immutability, imports outputs back into content-addressed storage, and deletes the working directory. Collection inputs may use `zip-directory` materialization: encrypted, absolute, traversing, linked, oversized, or overpopulated archives are rejected; accepted members are extracted read-only and the complete tree digest is rechecked after execution. Provenance records the module, compatibility row, exact tool and dependency versions, command-contract digest, executable SHA-256, normalized parameter digest, input and output payload hashes, formats, and platform without recording executable, project, temporary, or source paths.

Fatal findings stop the affected path. Major findings block interpretation until remediation or an explicit scope decision. Warnings remain attached to downstream artifacts and claims. Refuting, weakening, supporting, and inconclusive evidence remain separate; refuted hypotheses and superseded plans remain in history.

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

An undeclared or untested tool, dependency, format, genome build, coordinate system, or compatibility combination blocks execution. A newer version is not assumed compatible until its independent regression and end-to-end evidence IDs are recorded in a new module version. Release validation resolves every ID against `reports/compatibility-execution-evidence.json`, reruns the evidence capture, and rejects missing, stale, failed, path-bearing, or credential-bearing evidence.

Tool version behavior is structured rather than free text. Each affected surface declares an ID, exact supported version rules, category (`parameter`, `api`, `field`, `default`, `behavior`, `input-format`, or `output-format`), compatibility effect, required action, and authoritative source. Dependencies declare their own identity, typed bounded version probe, parse pattern, tested and allowed versions, platform scope, and structured conflict records. Python runtime, Python/R packages, Java or system commands, services, and databases therefore enter the compatibility decision through declared evidence rather than implicit package discovery.

Foundational omics formats are defined once in the project-owned registry under `biomed_workbench/formats/`. An exact `name@specification-version` match activates the shared profile during the normal module compatibility gate. The profile adds representation, compression, conditional companion-index, sort, coordinate, reference-sequence digest, annotation release, identifier namespace, sample-manifest digest, orientation, processing-level, metadata-field, and payload-role validation. No nearest-version or extension-based fallback is permitted. `reports/format-contract-registry.json` is rebuilt and digest-checked during release validation.

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

The plugin manifest is the package version source. Publish only when rebuilding the generated index and catalog produces no diff, all unit/contract/end-to-end/release tests pass, and release validation confirms the single skill, 51 built-in modules, complete compatibility evidence, source-neutral paths, and absence of legacy registration surfaces.

Release validation also binds `reports/research-engine-verification.json` to the current registry and generated capability graph. Four replayable research-cycle fixtures must cover single, serial, parallel, and mixed plans; each includes a failed compatibility gate, an alternative-module plan revision, evidence ingestion, a hypothesis transition, and an exact final state digest.

For local Codex iteration:

```bash
python3 tools/prepare_local_update.py
codex plugin add biomed-workbench@biomed-workbench
```

Start a new Codex task after reinstalling so updated Skill metadata and module indexes are loaded.
