# Architecture

Biomed Workbench exposes one Codex skill and discovers scientific capabilities from independent, versioned modules. A module owns its scientific contract; the router, runner, catalog projection, and assistant contain no module-specific registration tables.

## Runtime Layers

1. `skills/biomed-workbench/SKILL.md` is the only user-facing Codex entry.
2. `biomed_workbench/modules/builtin/<module-id>/module.json` is the source of truth for every built-in capability.
3. `biomed_workbench/modules/contract.py` validates scientific, execution, version, dependency, format, and provenance contracts.
4. `biomed_workbench/modules/registry.py` discovers modules recursively and rejects duplicate IDs or unresolved relationships.
5. `biomed_workbench/router.py` ranks intents, questions, artifact types, and the primary routing workflow read from manifests; it selects a compact nonredundant module set by incremental query-feature coverage, rejects declared alternatives, and derives serial versus parallel execution from artifact dependencies without module-specific IDs. Later domain entries are descriptive tags and cannot create phantom workflow steps.
6. `biomed_workbench/runner.py` validates structured input and invokes resolved entrypoints.
7. `biomed_workbench/catalog.py` provides the v0.2 compatibility projection; it does not define or load a second capability registry.
8. `biomed_workbench/modules/index.json` and `tools/catalog.json` are generated release artifacts and are never edited manually.

The plugin does not own environment provisioning, execution infrastructure, remote job systems, or model-hosting infrastructure.

## Stateful Research Engine

`biomed_workbench/kernel/` stores immutable project context, typed scientific artifacts, falsifiable hypotheses, directional evidence, plan nodes, DAGs, decisions, and canonical state digests. Every transition is append-only and links its prior and resulting state digest. Deserialization replays the complete event ledger; a changed payload, event order, lineage link, or digest is rejected.

`biomed_workbench/orchestration/` builds a capability graph from module manifests, searches validated artifact paths, plans single/serial/parallel/mixed DAGs, evaluates cross-module scientific quality, applies declared compatibility policies, executes bounded entrypoints, adjudicates hypotheses, and controls retries or child-plan revisions. When a node remains blocked or fails after its retry budget, the default controller may create one child plan only by replacing it with a manifest-declared alternative whose complete input and output artifact contracts are identical; completed upstream artifacts and downstream bindings are retained. Other scientific strategy changes require an explicit replanning policy. The graph and controller contain no built-in module IDs.

Scientific artifacts preserve format and schema version, compression, orientation, companion indexes, coordinates, genome build, annotation release, identifier namespace, producer module/tool versions, experimental unit, denominator, processing level, quality status, source artifact lineage, and content digest. Unknown or incompatible metadata is not inferred from a filename.

Large scientific payloads are imported into a project-owned content-addressed store. Project state records only a payload role, SHA-256-derived relative object key, media type, byte size, and SHA-256; it never records the source path or source filename. Import rejects symlinks and non-regular files, while every resolution rechecks containment, file type, byte size, and digest. Inline artifacts keep their original canonical digest, and payload-backed artifacts bind every payload descriptor into artifact identity.

Command modules use a closed shell-free execution contract. Each command declares one tool identity, complete argument tokens, input and output `port + role + runtime filename` bindings, scalar parameters, timeout, combined stdout/stderr limit, and output-payload limit. Runtime materializes only verified project payloads in an isolated working directory, inherits no credential variables, accepts only declared outputs, rechecks input immutability, imports outputs back into content-addressed storage, and deletes the working directory. A digest-bound input may declare `sidecar_for` when a tool discovers an adjacent index or companion file without receiving it as an argument; the contract requires a primary input, an extending filename, separate role and digest, and forbids sidecar-to-sidecar chains. A project-owned Python implementation may be named by module identity: runtime resolves and hashes its source, copies it read-only into the isolated directory, executes it with the version-gated interpreter, rechecks both source and runtime copies, and records only module identity and SHA-256 rather than a machine path. Collection inputs may use `zip-directory` materialization: encrypted, absolute, traversing, linked, oversized, or overpopulated archives are rejected; accepted members are extracted read-only and the complete tree digest is rechecked after execution. Provenance records actual detected tool and dependency versions, whether each matches a tested baseline, the applied compatibility policy, module and row identity, command-contract digest, executable and implementation SHA-256, normalized parameter digest, input and output payload hashes, formats, and platform without recording machine-local paths.

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
- optional module-local `code_templates` with language, purpose, blocking quality-gate binding, and adaptation policy.

The first `domains[]` value is the module's routing workflow. It may introduce a future scientific workflow without router edits. Additional values describe cross-cutting scientific scope, but routing and the compatibility catalog never treat them as separate required workflow branches.

`access: codex_native` is reserved for a validated handoff to a Codex-managed built-in tool. Such a module must request no user provider credential, invoke no provider SDK or CLI, emit a recognized operation plus post-result quality gates, and keep the handoff distinct from an observed artifact. The single Skill performs the host-native call and may record an artifact only after Codex returns and inspects it.

Tested versions are reproducibility evidence, while allowed-version rules are execution policy. A detected version inside a row's policy may execute even when it is not the exact tested baseline, but provenance must preserve that distinction. Missing tools, versions outside every declared policy, known breaking changes, incompatible formats, genome-build or coordinate mismatches, and failed output validation block scientific evidence ingestion. Routing and usage guidance remain available so the assistant can explain remediation or choose a validated alternative. Release validation resolves every row against `reports/compatibility-execution-evidence.json` and rejects missing, stale, failed, path-bearing, or credential-bearing evidence.

Bioinformatics modules are derived from manifest semantics rather than a central module-ID list: an `omics` or `molecular_design` module of type analysis, validation, transform, or design must expose at least one passing code template. Deterministic modules retain their executable entrypoint and add `code_templates`; `agent_generated` modules retain `agent_protocol.template_sections`. Packaged files must exactly match manifest references. Static validation requires substantive Python or R source with input and output handling, bounded failure behavior, version provenance, and scientific checks, and rejects placeholders, dependency provisioning, infrastructure control, unsafe shell execution, and local paths. `biomed_workbench/project_templates.py` supplies compatibility evaluation, closed-schema checks, finite-output checks, content-addressed command inputs, source immutability, provenance, and atomic no-overwrite result writing.

Tool version behavior is structured rather than free text. Each affected surface declares an ID, exact supported version rules, category (`parameter`, `api`, `field`, `default`, `behavior`, `input-format`, or `output-format`), compatibility effect, required action, and authoritative source. Dependencies declare their own identity, typed bounded version probe, parse pattern, tested and allowed versions, platform scope, and structured conflict records. Python runtime, Python/R packages, Java or system commands, services, and databases therefore enter the compatibility decision through declared evidence rather than implicit package discovery.

Foundational omics and static-raster formats are defined once in the project-owned registry under `biomed_workbench/formats/`. An exact `name@specification-version` match activates the shared profile during the normal module compatibility gate. The profile adds representation, compression, conditional companion-index, sort, coordinate, reference-sequence digest, annotation release, identifier namespace, sample-manifest digest, orientation, processing-level, metadata-field, and payload-role validation. No nearest-version or extension-based fallback is permitted. `reports/format-contract-registry.json` is rebuilt and digest-checked during release validation.

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

Creation occurs in a temporary same-filesystem directory. For a bioinformatics module without an explicit Agent protocol, the creator also generates one module-local project template and binds every blocking quality gate before validation. The validator checks package shape, permissions, symbolic links, local path traces, manifest closure, current kernel compatibility, entrypoint resolution, template source quality, dependency and format evidence, compatibility rows, test schemas, execution timeout, output size, output schema, and expected results. Only a fully valid package is atomically renamed into the registry; failure leaves no partial module.

Adding a module must not require edits to `catalog.py`, `router.py`, `runner.py`, the assistant, or the generated indexes. Built-in development places the validated package under `biomed_workbench/modules/builtin/`, then rebuilds generated projections:

```bash
python3 tools/build_module_index.py
python3 tools/build_catalog.py
python3 tools/audit_bioinformatics_templates.py --output reports/bioinformatics-template-coverage.json
python3 tools/scaffold_bioinformatics_templates.py --check
python3 tools/validate_workbench.py --release
python3 -m unittest discover -s tests -p 'test*.py'
```

## Compatibility Changes

- Adding a tested baseline or widening a compatibility range requires an authoritative version source, a bounded version probe, compatibility-row coverage, input/output regression fixtures, known-change review, and representative end-to-end validation.
- Changing required input fields, units, coordinate conventions, output meaning, defaults, or quality interpretation requires a module version update.
- Removing an ID or breaking the v0.2 compatibility projection requires a documented plugin-level migration.
- Optional credentials must remain in the project allowlist and be assigned to exact endpoint contracts. `NCBI_API_KEY` is currently the only stored credential and is optional for the implemented NCBI E-utilities and Datasets endpoints; private or paid services require separate future contracts rather than reuse by database name.
- Generated indexes must exactly match recursive manifest discovery and are checked by digest during release validation.

## Release Flow

The plugin manifest is the package version source. Publish only when rebuilding the generated index and catalog produces no diff, all unit/contract/end-to-end/release tests pass, and release validation confirms the single skill, every dynamically discovered built-in module, complete compatibility evidence, source-neutral paths, and absence of retired registration surfaces.

When one module changes, rerun that module's live verifier and issue a new compatibility row and evidence revision before rebuilding aggregate evidence. Reports for unchanged modules may be rebound to the new global registry digest with `python3 tools/rebind_live_evidence_registry.py`; the command rejects failed reports, unknown modules, changed module versions, and retired compatibility rows. Rebinding never replaces execution evidence for the changed module.

Public biomedical databases share `PublicJSONClient` only for transport safety: HTTPS host allow-listing, bounded request and response bodies, transient retry policy, JSON-root validation, and request metadata. Crossref/Europe PMC citation identity, bioRxiv version history, PubChem chemical identity, ClinicalTrials.gov cohort retrieval, and RCSB structural evidence keep separate parsers, contracts, outputs, and quality gates. ClinicalTrials.gov 1.1 is count-verified and server-filtered: opaque page tokens are followed to a declared cap, unique NCT IDs reconcile with `totalCount`, capped cohorts are marked truncated, same-site location constraints use grouped Essie semantics, no hidden local post-filtering is allowed, and every request is retained in provenance. RCSB Search API v2 uses a separately versioned bounded JSON POST contract; first-page HTTP 204 is an explicit zero-result set, later-page 204 is a protocol error, unique PDB IDs and total counts must reconcile, and truncation remains visible. RCSB Data API modules separately retain entry, polymer-entity, and nonpolymer-to-chemical-component identity without converting deposited metadata into biological or binding claims.

Generic plugin or Skill scaffolding, marketplace readers, provider model-release resolution, and host contract-validator implementations are not scientific runtime capabilities. The repository invokes current official validators unchanged, records their digests, and keeps the one curated Skill and plugin manifests under release tests.

Repository-quality checks are not scientific inference modules. They run the complete test and release suite, rebuild deterministic evidence, reject generated drift, and perform a redacted secret scan. Scientific eval thresholds and domain-specific gold sets remain separate named evidence requirements and are never inferred from a green generic quality job or a nondecreasing test count.

Release validation also binds `reports/research-engine-verification.json` to the current registry and generated capability graph. Four replayable research-cycle fixtures must cover single, serial, parallel, and mixed plans; each includes a failed compatibility gate, an alternative-module plan revision, evidence ingestion, a hypothesis transition, and an exact final state digest.

Start a new Codex task after reinstalling so updated Skill metadata and module indexes are loaded.
