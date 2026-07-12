# Module Registry Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace domain-owned capability specifications and manually maintained routing boosts with independently discoverable scientific modules, while preserving all 48 current capabilities and the single Biomed Workbench entry.

**Architecture:** Each built-in capability receives a closed `module.json` manifest under `biomed_workbench/modules/builtin/<module-id>/`. A source-neutral registry discovers and validates these manifests, resolves their entrypoints, builds an immutable capability and intent index, and supplies the existing runner and router. Generated compatibility catalogs remain release artifacts, not sources of truth.

**Tech Stack:** Python 3.10+ standard library, immutable dataclasses, JSON Schema-like closed contracts implemented by the existing validator, `unittest`, Codex plugin validators.

## Global Constraints

- Keep exactly one user-facing skill: `skills/biomed-workbench/SKILL.md`.
- Do not add CPU, GPU, container, Slurm, remote-compute, or local-model management.
- Do not retain source-library paths, wrappers, adapters, copied source trees, or source-oriented operational names.
- Do not add a mandatory API credential; `NCBI_API_KEY` remains the only allowed optional credential.
- Every manifest uses a closed input schema and a closed output-envelope schema.
- Every bioinformatics tool module declares exact tested tool and dependency
  versions plus machine-readable input-output format compatibility.
- An unknown tool, dependency, or format version blocks before execution unless
  an explicitly validated compatibility row or alternative module matches.
- Adding a valid module must require no edits to registry, catalog, router, runner, or assistant source files.
- Existing 48 capability IDs and behavior remain backward compatible during migration.
- Use test-first development and commit after every task.

---

## File Structure

Create these focused units:

- `biomed_workbench/modules/__init__.py`: public module-registry exports.
- `biomed_workbench/modules/contract.py`: immutable manifest contracts and validation.
- `biomed_workbench/modules/registry.py`: recursive discovery, duplicate detection, indexing, and entrypoint resolution.
- `biomed_workbench/modules/compatibility.py`: tool, dependency, format, index,
  coordinate-system, and genome-build compatibility checks.
- `biomed_workbench/modules/index.py`: generated-index serialization and deterministic digesting.
- `biomed_workbench/modules/builtin/<module-id>/module.json`: one manifest per current capability.
- `tools/validate_module.py`: standalone module validator.
- `tools/build_module_index.py`: deterministic generated index builder.
- `tools/create_module.py`: atomic future-module scaffolder and validator.
- `reports/module-registry-migration.json`: migration and backward-compatibility evidence.

Modify these integration points:

- `biomed_workbench/catalog.py`: compatibility facade over the new registry.
- `biomed_workbench/router.py`: rank registry-provided intents and questions without per-module constants.
- `biomed_workbench/runner.py`: resolve execution through module records.
- `tools/catalog.json`: generated compatibility catalog.
- `tools/validate_workbench.py`: module and index release gates.

Delete after parity is proven:

- `biomed_workbench/capability_specs/*.json`.
- `tools/add_capability.py`.

---

### Task 1: Define the Independent Module Contract

**Files:**
- Create: `biomed_workbench/modules/__init__.py`
- Create: `biomed_workbench/modules/contract.py`
- Test: `tests/unit/test_module_contract.py`

**Interfaces:**
- Produces: `FormatContract`, `ArtifactPort`, `ToolRequirement`,
  `DependencyRequirement`, `CompatibilityRow`, `QualityGate`, `ModuleManifest`,
  `parse_manifest(payload)`, and `manifest_to_dict(manifest)`.
- Consumes: existing `Capability` input-schema and access/mutability invariants from `biomed_workbench.models` only for backward conversion.

- [x] **Step 1: Write failing identity and scientific-contract tests**

```python
def test_manifest_requires_scientific_contract_and_closed_schemas():
    payload = valid_manifest_payload()
    manifest = parse_manifest(payload)
    assert manifest.id == "fixture-analysis"
    assert manifest.module_type == "analysis"
    assert manifest.input_artifacts[0].artifact_type == "feature_matrix"
    assert manifest.quality_gates[0].severity == "major"

def test_manifest_rejects_unknown_fields_and_incomplete_scientific_metadata():
    payload = valid_manifest_payload()
    payload["unexpected"] = True
    with pytest_raises(ValueError, "unsupported manifest fields"):
        parse_manifest(payload)
```

- [x] **Step 2: Run the test and verify missing-module failure**

Run: `python3 -m unittest tests.unit.test_module_contract`

Expected: import failure for `biomed_workbench.modules.contract`.

- [x] **Step 3: Implement immutable contracts and strict parser**

```python
@dataclass(frozen=True)
class ArtifactPort:
    artifact_type: str
    formats: tuple[FormatContract, ...]
    processing_levels: tuple[str, ...]
    required_metadata: tuple[str, ...]

@dataclass(frozen=True)
class FormatContract:
    name: str
    versions: tuple[str, ...]
    representations: tuple[str, ...]
    compression: tuple[str, ...]
    required_indexes: tuple[str, ...]
    coordinate_systems: tuple[str, ...]
    genome_build_policy: str
    genome_builds: tuple[str, ...]
    annotation_releases: tuple[str, ...]
    orientations: tuple[str, ...]

@dataclass(frozen=True)
class ToolRequirement:
    name: str
    ecosystem: str
    identity: str
    tested_versions: tuple[str, ...]
    allowed_versions: tuple[str, ...]
    version_source: str
    verified_at: str
    version_probe: tuple[str, ...]
    mismatch_policy: str

@dataclass(frozen=True)
class DependencyRequirement:
    name: str
    ecosystem: str
    required: bool
    tested_versions: tuple[str, ...]
    allowed_versions: tuple[str, ...]
    purpose: str
    conflicts: tuple[str, ...]

@dataclass(frozen=True)
class CompatibilityRow:
    id: str
    module_version: str
    tool_versions: dict[str, tuple[str, ...]]
    dependency_versions: dict[str, tuple[str, ...]]
    input_formats: dict[str, tuple[str, ...]]
    output_formats: dict[str, tuple[str, ...]]
    platforms: tuple[str, ...]

@dataclass(frozen=True)
class QualityGate:
    id: str
    severity: str
    description: str
    blocks_interpretation: bool

@dataclass(frozen=True)
class ModuleManifest:
    id: str
    version: str
    title: str
    description: str
    module_type: str
    domains: tuple[str, ...]
    intents: tuple[str, ...]
    questions: tuple[str, ...]
    entrypoint: str
    maturity: str
    input_artifacts: tuple[ArtifactPort, ...]
    output_artifacts: tuple[ArtifactPort, ...]
    preconditions: tuple[str, ...]
    assumptions: tuple[str, ...]
    quality_gates: tuple[QualityGate, ...]
    limitations: tuple[str, ...]
    evidence_effects: tuple[str, ...]
    alternatives: tuple[str, ...]
    complements: tuple[str, ...]
    tool_requirements: tuple[ToolRequirement, ...]
    dependencies: tuple[DependencyRequirement, ...]
    compatibility_matrix: tuple[CompatibilityRow, ...]
    access: str
    mutability: str
    credentials: tuple[str, ...]
    input_schema: dict[str, object]
    output_schema: dict[str, object]
```

Validate SemVer, source-neutral IDs, allowed enums, nonempty scientific fields,
closed schemas, credential allowlist, format versions, nonempty tested versions
for external tools, compatibility-row references, and exact top-level fields.
Return tuples and copied dictionaries so callers cannot mutate loaded manifests.

- [x] **Step 4: Run focused and model regression tests**

Run: `python3 -m unittest tests.unit.test_module_contract tests.unit.test_models tests.unit.test_catalog`

Expected: all pass.

- [x] **Step 5: Commit**

```bash
git add biomed_workbench/modules tests/unit/test_module_contract.py
git commit -m "feat: define scientific module contract"
```

---

### Task 2: Discover and Validate Modules Without Central Registration

**Files:**
- Create: `biomed_workbench/modules/registry.py`
- Create: `tests/fixtures/modules/fixture-analysis/module.json`
- Test: `tests/unit/test_module_registry.py`

**Interfaces:**
- Consumes: `ModuleManifest`, `parse_manifest` from Task 1.
- Produces: `ModuleRegistry.discover(root)`, `all()`, `get(id)`, `search_terms(id)`, `resolve_entrypoint(id)`, and `digest`.

- [x] **Step 1: Write failing recursive-discovery tests**

```python
def test_registry_discovers_fixture_without_registration_code():
    registry = ModuleRegistry.discover(FIXTURE_ROOT)
    assert [module.id for module in registry.all()] == ["fixture-analysis"]
    assert "analyze fixture" in registry.search_terms("fixture-analysis")

def test_registry_rejects_duplicate_ids_across_directories():
    with pytest_raises(ValueError, "duplicate module id"):
        ModuleRegistry.discover(DUPLICATE_FIXTURE_ROOT)
```

- [x] **Step 2: Run and verify registry import failure**

Run: `python3 -m unittest tests.unit.test_module_registry`

Expected: import failure for `ModuleRegistry`.

- [x] **Step 3: Implement deterministic discovery**

Discover only files named `module.json`, parse every manifest, sort by module
ID, reject duplicate IDs, verify alternative and complement references after
the complete set is known, and calculate SHA-256 over canonical manifest JSON.
Resolve Python entrypoints as `module:function`, reject private names, and
require a callable.

- [x] **Step 4: Prove filesystem addition changes registry without code edits**

In the test, copy the fixture directory to a temporary registry root, discover
one module, add a second valid `module.json`, rediscover, and assert two IDs and
a changed digest. Do not monkeypatch registry internals.

- [x] **Step 5: Run tests and commit**

Run: `python3 -m unittest tests.unit.test_module_contract tests.unit.test_module_registry`

```bash
git add biomed_workbench/modules/registry.py tests/fixtures/modules tests/unit/test_module_registry.py
git commit -m "feat: discover scientific modules dynamically"
```

---

### Task 3: Enforce Tool, Dependency, and Format Compatibility

**Files:**
- Create: `biomed_workbench/modules/compatibility.py`
- Create: `tools/build_tool_compatibility_matrix.py`
- Test: `tests/unit/test_module_compatibility.py`
- Test: `tests/unit/test_module_compatibility_report.py`
- Test: `tests/contract/test_tool_version_compatibility.py`

**Interfaces:**
- Consumes: `ModuleManifest`, runtime version probe results, and typed artifact metadata.
- Produces: `EnvironmentSnapshot`, `ArtifactSnapshot`,
  `CompatibilityFinding`, `CompatibilityDecision`, `detect_environment`, and
  `evaluate_compatibility`.

- [x] **Step 1: Write failing compatibility-decision tests**

```python
def test_exact_validated_tool_dependency_and_format_row_allows_execution():
    decision = evaluate_compatibility(
        manifest=fixture_manifest(),
        environment=EnvironmentSnapshot(
            tools={"scanpy": "1.11.5"},
            dependencies={"anndata": "0.11.4", "python": "3.14.3"},
            platform="macos-arm64",
        ),
        artifacts=(ArtifactSnapshot(
            port="counts",
            format="h5ad",
            format_version="0.11",
            compression="gzip",
            indexes=(),
            coordinate_system=None,
            genome_build=None,
            metadata_fields=("sample_id", "batch"),
        ),),
    )
    assert decision.allowed is True
    assert decision.compatibility_row_id == "scanpy-1.11.5-h5ad-0.11"

def test_unknown_tool_version_blocks_before_execution():
    decision = evaluate_compatibility(
        fixture_manifest(),
        EnvironmentSnapshot(
            tools={"scanpy": "1.12.0"},
            dependencies={"anndata": "0.11.4", "python": "3.14.3"},
            platform="macos-arm64",
        ),
        valid_artifacts(),
    )
    assert decision.allowed is False
    assert "UNVALIDATED_TOOL_VERSION" in {finding.code for finding in decision.findings}
```

Add separate failures for missing required dependencies, conflicting packages,
unsupported format version, absent index, coordinate-system mismatch, genome
build mismatch, missing metadata, and an explicitly validated alternative.

- [x] **Step 2: Run and verify missing compatibility module**

Run: `python3 -m unittest tests.unit.test_module_compatibility tests.contract.test_tool_version_compatibility`

Expected: import failure for `biomed_workbench.modules.compatibility`.

- [x] **Step 3: Implement strict environment and artifact snapshots**

Use `importlib.metadata.version` for Python distributions and injected bounded
probe runners for R, Java, system tools, services, and databases. Parse only
the manifest-declared version pattern. Probe failures become structured
findings; raw command output and machine paths are not persisted.

`evaluate_compatibility` permits execution only when one complete compatibility
row matches module version, all required tool and dependency versions, platform,
and every input artifact contract. It does not infer compatibility from a
newer-looking version number.

- [x] **Step 4: Prove runner blocks before entrypoint invocation**

Use an entrypoint fixture that increments a counter. Supply an unvalidated tool
version, assert `CompatibilityError`, and assert the counter remains zero.
Then supply the validated row and assert one invocation plus a result provenance
record containing module, tool, dependency, format, row, and parameter versions.

- [x] **Step 5: Implement and verify the public compatibility-matrix generator**

The generator reports every module in a supplied registry, module version, external tools,
tested versions, dependencies, artifact formats, compatibility-row IDs, and
validation status. It must contain no credentials or machine paths. Modules
implemented only with the Python standard library explicitly state
`external_tool_required: false` rather than omitting compatibility evidence.
Test it against the independent fixture registry. The checked report for all
48 built-ins is generated after migration in Task 4.

- [x] **Step 6: Run tests and commit**

```bash
python3 -m unittest tests.unit.test_module_compatibility tests.unit.test_module_compatibility_report tests.contract.test_tool_version_compatibility
git add biomed_workbench/modules/compatibility.py tools/build_tool_compatibility_matrix.py tests/unit/test_module_compatibility.py tests/unit/test_module_compatibility_report.py tests/contract/test_tool_version_compatibility.py
git commit -m "feat: enforce scientific tool compatibility"
```

---

### Task 4: Convert Existing Capability Contracts to Module Manifests

**Files:**
- Create: `tools/migrate_capabilities_to_modules.py`
- Create: `biomed_workbench/modules/builtin/<48 module directories>/module.json`
- Create: `reports/module-registry-migration.json`
- Create: `reports/tool-compatibility-matrix.json`
- Test: `tests/release/test_module_migration.py`

**Interfaces:**
- Consumes: the current 48 capability records and new `ModuleManifest` parser.
- Produces: exactly 48 validated built-in manifests and a migration evidence report.

- [x] **Step 1: Write failing parity test**

```python
def test_every_legacy_capability_has_one_behavior_preserving_module():
    legacy = {row["id"]: row for row in json.loads(CATALOG.read_text())["capabilities"]}
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    current = {module.id: module for module in registry.all()}
    assert set(current) == set(legacy)
    for module_id, row in legacy.items():
        module = current[module_id]
        assert module.entrypoint == row["entrypoint"]
        assert module.input_schema == row["input_schema"]
        assert module.access == row["access"]
        assert module.mutability == row["mutability"]
```

- [x] **Step 2: Run and verify empty built-in registry failure**

Run: `python3 -m unittest tests.release.test_module_migration`

Expected: missing built-in root or zero modules.

- [x] **Step 3: Implement one-time structured migration tool**

The migration reads the current domain specs with `json`, maps each capability
to a scientific module family, and enriches it using a checked-in source-neutral
mapping table containing intents, questions, artifact ports, assumptions,
quality gates, limitations, evidence effects, alternatives, and complements.
It also declares Python/runtime dependencies, external-tool requirements,
format versions, and at least one compatibility row for every module. It must
refuse incomplete mappings; no generic placeholder text is allowed.

- [x] **Step 4: Generate and inspect all manifests**

Run: `python3 tools/migrate_capabilities_to_modules.py`

Expected: `created=48`, `validated=48`, `unmapped=0`, `duplicate=0`.

- [x] **Step 5: Build migration report**

The report records old and new counts, sorted IDs, registry digest, entrypoint
parity count, schema parity count, scientific-field completeness count, and
tool/dependency/format compatibility completeness count, and explicitly states
that runtime source paths are absent.

Run `python3 tools/build_tool_compatibility_matrix.py` against the migrated
built-in registry and require `module_count=48`, `compatibility_complete=48`,
and no unvalidated external-tool claim.

- [x] **Step 6: Run parity tests and commit**

Run: `python3 -m unittest tests.release.test_module_migration tests.unit.test_module_registry`

```bash
git add tools/migrate_capabilities_to_modules.py biomed_workbench/modules/builtin reports/module-registry-migration.json reports/tool-compatibility-matrix.json tests/release/test_module_migration.py
git commit -m "refactor: migrate capabilities to independent modules"
```

---

### Task 5: Generate a Stable Module Index and Compatibility Catalog

**Files:**
- Create: `biomed_workbench/modules/index.py`
- Create: `tools/build_module_index.py`
- Create: `biomed_workbench/modules/index.json`
- Modify: `tools/build_catalog.py`
- Modify: `tools/catalog.json`
- Test: `tests/unit/test_module_index.py`

**Interfaces:**
- Consumes: `ModuleRegistry`.
- Produces: canonical module index and the old capability catalog projection.

- [x] **Step 1: Write failing deterministic-index test**

```python
def test_index_is_deterministic_and_contains_scientific_search_fields():
    first = build_index(ModuleRegistry.discover(BUILTIN_ROOT))
    second = build_index(ModuleRegistry.discover(BUILTIN_ROOT))
    assert first == second
    assert first["module_count"] == 48
    assert first["modules"][0]["intents"]
    assert first["modules"][0]["input_artifacts"]
```

- [x] **Step 2: Run and verify missing index builder failure**

Run: `python3 -m unittest tests.unit.test_module_index`

- [x] **Step 3: Implement canonical index and compatibility projection**

`build_index` includes all scientific search fields and a registry digest.
It also includes exact tested versions, allowed versions, format contracts, and
compatibility-row IDs for pre-execution inspection.
`build_catalog.py` projects module identity, entrypoint, schema, requirements,
access, mutability, title, description, and primary domain into the existing
catalog shape so external users do not break during v0.2.

- [x] **Step 4: Verify rebuild cleanliness**

Run `python3 tools/build_module_index.py` twice and assert the second run leaves
`git diff --exit-code biomed_workbench/modules/index.json tools/catalog.json`.

- [x] **Step 5: Run tests and commit**

```bash
python3 -m unittest tests.unit.test_module_index tests.test_catalog_quality
git add biomed_workbench/modules/index.py biomed_workbench/modules/index.json tools/build_module_index.py tools/build_catalog.py tools/catalog.json tests/unit/test_module_index.py
git commit -m "feat: generate deterministic scientific module index"
```

---

### Task 6: Replace Catalog Loading With the Module Registry

**Files:**
- Modify: `biomed_workbench/catalog.py`
- Modify: `biomed_workbench/runner.py`
- Test: `tests/unit/test_catalog.py`
- Test: `tests/unit/test_runner.py`
- Test: `tests/e2e/test_offline_capabilities.py`

**Interfaces:**
- Consumes: built-in `ModuleRegistry`.
- Preserves: `all_capabilities()`, `resolve(id)`, `resolve_entrypoint(capability)`, and `run(id, inputs)`.

- [x] **Step 1: Add failing facade-parity tests**

Assert 48 IDs, immutable repeated loads, module-to-capability field parity,
entrypoint resolution, schema rejection, safe error wrapping, and representative
execution from every domain.

- [x] **Step 2: Run and verify catalog still reads domain specs**

The new test must patch the legacy specification root to an invalid directory
and fail, proving the old dependency remains before implementation.

- [x] **Step 3: Implement registry-backed compatibility facade**

Create one lazily initialized built-in registry. Convert manifests to existing
`Capability` values at the boundary. Resolve execution by module ID internally.
Do not load `capability_specs` or generated `index.json` at runtime.

- [x] **Step 4: Run all execution regressions**

Run: `python3 -m unittest tests.unit.test_catalog tests.unit.test_runner tests.e2e.test_offline_capabilities`

Expected: all 48 capability executions remain valid.

- [x] **Step 5: Commit**

```bash
git add biomed_workbench/catalog.py biomed_workbench/runner.py tests/unit/test_catalog.py tests/unit/test_runner.py tests/e2e/test_offline_capabilities.py
git commit -m "refactor: execute capabilities through module registry"
```

---

### Task 7: Replace Manual Intent Boosts With Manifest Search Metadata

**Files:**
- Modify: `biomed_workbench/router.py`
- Modify: `tests/test_routing.py`
- Create: `tests/e2e/test_dynamic_module_routing.py`

**Interfaces:**
- Consumes: module `intents`, `questions`, `domains`, title, and description.
- Produces: existing route response plus selected module rationale.

- [x] **Step 1: Write failing no-central-edit routing test**

```python
def test_new_fixture_module_routes_from_its_manifest_only(tmp_path):
    install_fixture_module(tmp_path, intents=["quantify neoenzyme flux", "新酶通量"])
    registry = ModuleRegistry.discover(tmp_path)
    plan = route("请量化新酶通量", registry=registry)
    assert plan["steps"][0]["candidates"][0]["id"] == "fixture-analysis"
```

Also assert existing Chinese and English routing, single/serial/parallel/mixed
plans, deterministic ties, and no source/adaptor fields.

- [x] **Step 2: Run and verify missing injectable-registry failure**

Run: `python3 -m unittest tests.e2e.test_dynamic_module_routing tests.test_routing`

- [x] **Step 3: Implement metadata-driven scoring**

Remove `INTENT_BOOSTS` and per-capability keyword constants. Infer candidate
domains from module metadata, score exact phrase, token, artifact, question,
maturity, and compatibility matches, and include a concise `selection_reasons`
array. Preserve plan-type behavior.

- [x] **Step 4: Run routing and assistant regressions**

Run: `python3 -m unittest tests.test_routing tests.unit.test_assistant tests.e2e.test_dynamic_module_routing`

- [x] **Step 5: Commit**

```bash
git add biomed_workbench/router.py tests/test_routing.py tests/e2e/test_dynamic_module_routing.py
git commit -m "feat: route dynamically from module manifests"
```

---

### Task 8: Add Standalone Validation and Future-Module Creation

**Files:**
- Create: `tools/validate_module.py`
- Create: `tools/create_module.py`
- Modify: `tools/validate_workbench.py`
- Test: `tests/e2e/test_create_module.py`
- Test: `tests/release/test_module_packaging.py`

**Interfaces:**
- Produces: `validate_module(path) -> report` and atomic CLI module creation.

- [x] **Step 1: Write failing create-validate-discover test**

The test creates a temporary module from a complete JSON request, validates it,
discovers it, routes a matching query, invokes the fixture implementation, and
asserts the repository built-in registry was not modified.

- [x] **Step 2: Run and verify missing tools**

Run: `python3 -m unittest tests.e2e.test_create_module`

- [x] **Step 3: Implement validators and atomic creator**

`validate_module.py` checks exact files, manifest contract, entrypoint,
permissions, credential allowlist, tested version evidence, dependency and
format contracts, compatibility rows, test presence, source-path absence, and
kernel compatibility. `create_module.py` writes to a temporary directory,
validates it, then atomically renames it; failures leave no partial module.

- [x] **Step 4: Add release gates**

`validate_workbench.py --release` must discover 48 modules, compare the checked
index digest, reject central intent tables, ensure one skill, check that all
module entrypoints and schemas load, and reject any bioinformatics module whose
tool, dependency, format, or compatibility evidence is incomplete.

- [x] **Step 5: Run tests and commit**

```bash
python3 -m unittest tests.e2e.test_create_module tests.release.test_module_packaging
python3 tools/validate_workbench.py --release
git add tools/validate_module.py tools/create_module.py tools/validate_workbench.py tests/e2e/test_create_module.py tests/release/test_module_packaging.py
git commit -m "feat: validate and add scientific modules atomically"
```

---

### Task 9: Retire the Domain Specification Migration Surface

**Files:**
- Delete: `biomed_workbench/capability_specs/*.json`
- Delete: `tools/add_capability.py`
- Modify: `tests/unit/test_registry_layout.py`
- Modify: `tests/e2e/test_add_capability.py`
- Modify: `docs/architecture.md`
- Test: `tests/release/test_release_surface.py`

**Interfaces:**
- Replaces: domain-spec addition workflow with `tools/create_module.py`.

- [x] **Step 1: Write failing release-surface test**

Assert no `capability_specs` directory, no `add_capability.py`, no operational
domain ownership in module paths, and one independent directory per module.

- [x] **Step 2: Run and verify legacy files trigger failure**

Run: `python3 -m unittest tests.release.test_release_surface`

- [x] **Step 3: Delete migration surfaces and update tests/docs**

Rewrite the old add-capability end-to-end test to create, validate, discover,
route, and execute a module. Document manifest fields, extension workflow,
compatibility policy, and generated-index rules.

- [x] **Step 4: Run complete test suite**

Run: `python3 -m unittest discover -s tests -p 'test*.py'`

Expected: all tests pass with 48 built-in modules.

- [x] **Step 5: Commit**

```bash
git add -A biomed_workbench/capability_specs tools/add_capability.py tests docs/architecture.md
git commit -m "refactor: retire domain-owned capability specifications"
```

---

### Task 10: Prove Codex Packaging and Installed-Cache Behavior

**Files:**
- Modify: `reports/codex-install-verification.json`
- Modify: `reports/capability-coverage-audit.json`
- Create: `reports/module-registry-verification.json`
- Modify: `tests/release/test_codex_install_evidence.py`
- Create: `tests/release/test_module_registry_evidence.py`

**Interfaces:**
- Produces: path-free release evidence for source checkout and installed cache.

- [x] **Step 1: Write failing evidence tests**

Require module count 48, registry and index digests, dynamic fixture discovery,
installed-cache route and execution, tool/dependency/format compatibility
counts, one skill, credential list, and absence of machine paths.

- [x] **Step 2: Run the isolated installation flow**

Using the bundled Codex CLI and a temporary HOME/CODEX_HOME:

1. add the local repository as a marketplace;
2. install the plugin;
3. list plugins;
4. inspect the installed module index;
5. route and execute representative modules from each domain;
6. validate that a new conversation is required to load the changed skill and
   module index.

- [x] **Step 3: Write path-free evidence reports**

Record booleans, counts, IDs, digests, and command outcomes only. Do not record
temporary paths, usernames, credentials, or raw environment dumps.

- [x] **Step 4: Run all release gates**

```bash
python3 -m unittest discover -s tests -p 'test*.py'
python3 tools/validate_workbench.py --release
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/biomed-workbench
git diff --check
```

- [x] **Step 5: Commit the verified foundation**

```bash
git add reports tests/release
git commit -m "test: verify installed scientific module registry"
```

---

## Plan Self-Review

- **Spec coverage:** Tasks cover independent manifests, no-central-edit
  discovery, dynamic intent indexing, compatibility projection, future module
  creation, strict tool/dependency/format compatibility, migration of all 48
  capabilities, retirement of domain specs, and installed-cache verification.
- **Scope boundary:** This plan intentionally stops before project-context,
  hypothesis, evidence, capability-graph, and feedback-controller work. Those
  depend on the stable module contract and receive a separate implementation
  plan after Task 10.
- **Type consistency:** `ModuleManifest`, `ModuleRegistry`, `build_index`, and
  registry-backed `route` are introduced before any consuming task.
- **No placeholders:** Every task defines files, interfaces, red test, expected
  failure, implementation behavior, verification command, and commit boundary.
