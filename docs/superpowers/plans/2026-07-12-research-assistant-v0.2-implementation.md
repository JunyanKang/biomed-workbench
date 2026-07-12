# Biomed Workbench Research Assistant v0.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Biomed Workbench as a source-neutral Codex research assistant whose advertised capabilities are executable or substantively actionable, with every script and capability covered by an end-to-end verification record.

**Architecture:** A new `biomed_workbench` Python package owns research orchestration, typed capability registration, routing, execution, public scientific API clients, and optional local compute backends. Existing `tools/*.py` files become thin CLIs. A generated operational catalog contains no upstream-source fields, while legal attribution is isolated in `references/provenance.json` and `NOTICE.md`.

**Tech Stack:** Python 3.10+ standard library first, `unittest`, JSON Schema-like local validation, HTTP via `urllib`, subprocess command backends, optional Docker/SLURM/local scientific packages, Codex plugin manifests, Markdown/SVG/PNG documentation assets.

## Global Constraints

- Expose exactly one Codex skill: `biomed-workbench`.
- Default operation requires zero user-supplied API keys.
- The only optional credential families in v0.2.0 are `NCBI_API_KEY`, `ELSEVIER_API_KEY`, and `SYNAPSE_AUTH_TOKEN`.
- Do not use model-vendor inference credentials or paid hosted inference as core capabilities.
- Do not ship a nested general-purpose LLM client or agent loop. Rewrite upstream provider/token/model-endpoint code into Codex-native skill guidance, typed tool contracts, deterministic functions, or an explicit removal record.
- Operational files and catalog records must not classify capabilities by upstream project name.
- Upstream names and commits are restricted to `NOTICE.md`, `references/provenance.json`, and historical design/plan documents.
- Remove source checkout environment variables and source-specific adapters.
- Do not preserve catalog count for appearance; remove capabilities that cannot be made executable or substantively actionable.
- Every operational catalog entry must resolve to a local callable, command builder, public scientific service client, local model backend, or substantive workflow document.
- Every tracked script and every operational capability must have a machine-readable end-to-end verification record.
- Tests must not launch paid calls, download model weights, mutate the host environment, or submit cluster jobs.
- Live public-API verification uses bounded queries, explicit timeouts, and no more than one request sequence per service.
- No credential value may be written, printed, committed, or embedded in an error.

## File Map

- `biomed_workbench/models.py`: immutable capability, plan, evidence, artifact, and verification record types.
- `biomed_workbench/catalog.py`: registration, resolution, search, serialization, and catalog generation.
- `biomed_workbench/research.py`: research record and evidence ledger.
- `biomed_workbench/assistant.py`: frame-plan-investigate-design-interpret-deliver-audit orchestration.
- `biomed_workbench/router.py`: scientific intent and execution-shape routing.
- `biomed_workbench/runner.py`: validated capability invocation and structured results.
- `biomed_workbench/services/`: HTTP, environment, container, scheduler, and local-model infrastructure.
- `biomed_workbench/domains/`: source-neutral scientific capability modules.
- `biomed_workbench/workflows/`: composite research workflows.
- `tools/*.py`: compatibility CLI entrypoints only.
- `tests/unit/`: deterministic package tests.
- `tests/contract/`: mocked public API and command contract tests.
- `tests/e2e/cases.json`: one verification case per tracked script and operational capability.
- `tests/e2e/fixtures/`: minimal synthetic scientific inputs.
- `tests/e2e/test_cases.py`: manifest-driven verification runner.
- `reports/capability-verification.json`: generated release evidence, not hand-authored claims.

---

### Task 0: Exhaustively Read And Assimilate Every Source File

**Files:**
- Create: `tools/assimilate_sources.py`
- Create: `biomed_workbench/assimilation.py`
- Create: `tests/unit/test_assimilation.py`
- Create: `tests/release/test_assimilation_summary.py`
- Create locally, ignored: `.source-audit/manifest.jsonl`
- Create locally, ignored: `.source-audit/file-errors.jsonl`
- Create: `reports/source-assimilation-summary.json`
- Modify: `references/provenance.json` when Task 7 creates the final public provenance file.

**Interfaces:**
- Produces: `FileRecord`, `SourceSummary`, `inventory(root)`, `read_record(path, root)`, `verify_complete(root, records)`, and a deterministic root digest.
- Consumes: source roots passed explicitly on the CLI; no machine-local path is written into tracked files.

- [ ] **Step 1: Write failing exhaustive-coverage tests**

```python
def test_manifest_requires_exact_inventory_equality():
    with temporary_source({"a.py": "def a(): return 1", "b.md": "# B"}) as root:
        records = [read_record(root / "a.py", root)]
        with self.assertRaises(IncompleteAssimilationError):
            verify_complete(root, records)

def test_sensitive_text_is_redacted_but_counted():
    record = read_record(secret_fixture(), secret_fixture().parent)
    self.assertEqual(record.disposition, "sensitive")
    self.assertNotIn("secret-value", json.dumps(record.to_dict()))
```

- [ ] **Step 2: Verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.unit.test_assimilation -v`

Expected: import failure because the assimilation module does not exist.

- [ ] **Step 3: Implement safe per-format readers**

Every reader starts from the already-read byte stream and records SHA-256, relative path, size, media/format, and disposition. Implement AST extraction for Python, structured parsing for JSON/YAML/TOML/notebooks, Markdown heading/rule extraction, safe `pickletools` opcode inspection without unpickling, archive member listing without extraction, image dimensions, PDF metadata/text availability, executable headers, symlink targets, and a bounded redacted text summary. Unknown formats still receive a byte-level record and cannot be skipped.

- [ ] **Step 4: Implement completeness and privacy gates**

`verify_complete()` compares normalized live relative paths to manifest paths exactly, detects changes during scanning, rejects duplicate paths, records read failures, and fails when any file lacks a disposition. Tracked reports contain source aliases rather than local absolute roots and exclude private relative paths from sensitive/runtime sources.

- [ ] **Step 5: Run the three original sources exhaustively**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/assimilate_sources.py \
  --source primary-a="$PRIMARY_A_ROOT" \
  --source primary-b="$PRIMARY_B_ROOT" \
  --source primary-c="$PRIMARY_C_ROOT" \
  --private-manifest .source-audit/manifest.jsonl \
  --public-summary reports/source-assimilation-summary.json
```

Use the actual local roots at execution time without saving them in tracked output. Expected baseline at plan creation: 260 files in the first source, 3,952 in the second, and 82,807 in the third. The scan must use live inventory totals rather than hard-coded counts.

- [ ] **Step 6: Run later-added Nature and accelerated-compute sources through the same reader**

Append records using stable source aliases. Exact inventory equality and root digests apply independently to all five sources.

- [ ] **Step 7: Review every non-generated source record by capability cluster**

Produce integration mappings from code symbols, scripts, skills, workflows, connectors, prompts, and scientific references. Generated runtime packages are grouped by package/version/role only after every file has an individual record. Sensitive records remain local and contribute only aggregate counts to the public summary.

Model-provider clients, provider-token handlers, hosted generic model endpoints, and nested agent loops receive the `rewrite` disposition and `codex_native_orchestration` capability cluster. Their useful planning and interaction contracts are translated into the single `biomed-workbench` skill and typed tool interfaces; their vendor API execution code is not retained.

- [ ] **Step 8: Verify assimilation evidence**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/assimilate_sources.py --verify .source-audit/manifest.jsonl
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.unit.test_assimilation tests.release.test_assimilation_summary -v
```

Expected: zero missing, extra, unreadable, duplicate, or unclassified files; public counts and root digests match the private manifest without exposing machine paths or secrets.

- [ ] **Step 9: Commit**

```bash
git add biomed_workbench/assimilation.py tools/assimilate_sources.py tests reports/source-assimilation-summary.json .gitignore
git commit -m "feat: add exhaustive source assimilation"
```

### Task 1: Establish The Research Assistant Kernel

**Files:**
- Create: `biomed_workbench/__init__.py`
- Create: `biomed_workbench/models.py`
- Create: `biomed_workbench/catalog.py`
- Create: `biomed_workbench/research.py`
- Create: `biomed_workbench/assistant.py`
- Create: `tests/unit/test_models.py`
- Create: `tests/unit/test_catalog.py`
- Create: `tests/unit/test_research.py`
- Create: `tests/unit/test_assistant.py`

**Interfaces:**
- Produces: `Capability`, `ResearchRecord`, `EvidenceItem`, `Artifact`, `ExecutionResult`, `register()`, `resolve()`, `all_capabilities()`, and `ResearchAssistant.run()`.
- Consumes: no legacy catalog code; this task establishes the new contracts.

- [ ] **Step 1: Write failing model and registry tests**

```python
def test_capability_rejects_unresolvable_entrypoint():
    capability = Capability(
        id="broken", workflow="evidence", kind="python", title="Broken",
        description="Broken test capability", entrypoint="missing.module:call",
        input_schema={}, requirements=(), access="offline", mutability="read_only",
    )
    with self.assertRaises(CapabilityResolutionError):
        resolve_entrypoint(capability)

def test_catalog_serialization_has_no_source_fields():
    record = capability_to_dict(EXAMPLE_CAPABILITY)
    self.assertNotIn("source", record)
    self.assertNotIn("source_path", record)
```

- [ ] **Step 2: Run the new unit tests and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.unit.test_models tests.unit.test_catalog -v`

Expected: import failures because `biomed_workbench.models` and `biomed_workbench.catalog` do not exist.

- [ ] **Step 3: Implement immutable contracts and registry**

Implement `Capability` with exact fields from the approved design and enforce lowercase hyphen/underscore-safe IDs, allowed workflow/kind/access/mutability values, nonempty descriptions, and local entrypoint resolution.

Implement:

```python
def register(capability: Capability) -> Capability: ...
def resolve(capability_id: str) -> Capability: ...
def resolve_entrypoint(capability: Capability) -> Callable[..., object] | Path: ...
def all_capabilities() -> tuple[Capability, ...]: ...
def capability_to_dict(capability: Capability) -> dict[str, object]: ...
```

- [ ] **Step 4: Write failing research-loop tests**

```python
def test_assistant_finishes_with_scientific_output_not_tool_ids():
    assistant = ResearchAssistant(registry=fake_registry())
    result = assistant.run("Assess TP53 evidence and propose validation")
    self.assertTrue(result.summary)
    self.assertTrue(result.evidence)
    self.assertNotIn("tool_ids", result.user_output)
```

- [ ] **Step 5: Implement research records and orchestration states**

Implement the seven states `frame`, `plan`, `investigate`, `design`, `interpret`, `deliver`, and `audit`. The assistant may skip irrelevant states but must record why. `ResearchRecord.to_dict()` must exclude secrets and serialize artifact paths relative to the active project when possible.

- [ ] **Step 6: Run kernel tests and verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/unit -p 'test_*.py' -v`

Expected: all Task 1 tests pass.

- [ ] **Step 7: Commit**

```bash
git add biomed_workbench tests/unit
git commit -m "feat: add research assistant kernel"
```

### Task 2: Replace Legacy Routing And Runtime Adapters

**Files:**
- Create: `biomed_workbench/router.py`
- Create: `biomed_workbench/runner.py`
- Create: `biomed_workbench/services/environments.py`
- Modify: `tools/route_task.py`
- Modify: `tools/search_tools.py`
- Modify: `tools/run_tool.py`
- Delete: `tools/adapters/__init__.py`
- Delete: `tools/adapters/biomni.py`
- Delete: `tools/adapters/claude_science.py`
- Delete: `tools/adapters/openscience.py`
- Create: `tests/unit/test_router_v2.py`
- Create: `tests/unit/test_runner.py`
- Create: `tests/contract/test_environments.py`

**Interfaces:**
- Consumes: Task 1 registry and research contracts.
- Produces: `route(query, runtime=None) -> ResearchPlan`, `run(capability_id, inputs, allow_mutation=False) -> ExecutionResult`, `runtime_status() -> dict[str, RuntimeState]`.

- [ ] **Step 1: Write failing tests for generic runtime discovery and safety**

```python
def test_runtime_status_has_no_upstream_application_keys():
    status = runtime_status(which=lambda name: None)
    self.assertEqual(set(status), {"python", "r", "docker", "gpu", "slurm"})

def test_runner_blocks_mutating_capability_without_intent():
    with self.assertRaises(MutationPermissionError):
        run("install-runtime", {}, allow_mutation=False)
```

- [ ] **Step 2: Verify RED, then implement generic discovery and runner**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.unit.test_runner tests.contract.test_environments -v`

Implement PATH-based discovery with only `BIOMED_PYTHON` and `BIOMED_RSCRIPT` overrides. GPU probes are read-only. Runner input validation occurs before importing optional dependencies or starting subprocesses.

- [ ] **Step 3: Port router scoring into the package**

Preserve the validated serial/parallel/mixed scenarios while adding runtime readiness and access class. Router output must contain scientific steps, dependencies, execution mode, and capability IDs for diagnostics; `ResearchAssistant` translates this into user-facing work.

- [ ] **Step 4: Replace tool CLIs with thin imports**

Each `tools/*.py` wrapper may parse CLI arguments and format output but must not contain routing, search, runtime, or invocation business logic.

- [ ] **Step 5: Delete adapters and run focused tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.unit.test_router_v2 tests.unit.test_runner tests.contract.test_environments -v
rg -n "from adapters|tools/adapters|SOURCE_ROOT|CLAUDE_SCIENCE" biomed_workbench tools tests
```

Expected: tests pass; `rg` returns no matches.

- [ ] **Step 6: Commit**

```bash
git add biomed_workbench tools tests
git commit -m "refactor: unify routing and runtime execution"
```

### Task 3: Convert Existing Scripts Into Resolvable Capabilities

**Files:**
- Create: `biomed_workbench/domains/scripts.py`
- Create: `tools/build_catalog.py`
- Replace: `tools/catalog.json`
- Create: `tests/unit/test_script_registry.py`
- Create: `tests/e2e/cases.json`
- Create: `tests/e2e/test_cases.py`
- Create: `tests/e2e/fixtures/`

**Interfaces:**
- Consumes: Task 1 registry and Task 2 runner.
- Produces: one `command` capability for every retained executable script and one `ScriptCase` record for every tracked script.

- [ ] **Step 1: Inventory every tracked executable**

Generate a deterministic inventory of `.py`, `.R`, `.sh`, and `.mjs` files under `scripts/`. Record language, CLI behavior, mutability, dependency group, input fixture class, and expected output contract. Exclude test helper modules from user-facing capabilities but include them in file verification.

- [ ] **Step 2: Write failing completeness tests**

```python
def test_every_script_has_exactly_one_e2e_case():
    scripts = discover_scripts(ROOT / "scripts")
    cases = load_cases(ROOT / "tests/e2e/cases.json")
    self.assertEqual({p.as_posix() for p in scripts}, {c.path for c in cases})

def test_every_script_capability_resolves():
    for capability in script_capabilities():
        self.assertTrue(resolve_entrypoint(capability))
```

- [ ] **Step 3: Verify RED and classify scripts**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.unit.test_script_registry tests.e2e.test_cases.ScriptCaseCompletenessTests -v`

Expected: failures listing every script without a case.

- [ ] **Step 4: Build source-neutral script capabilities**

Use domain, action, inputs, and mutability to create records. Descriptions come from module documentation or explicit overrides. Do not copy legacy `source`, `source_path`, kind, or run-policy fields.

- [ ] **Step 5: Add minimal fixtures and bounded execution cases**

Use small synthetic CSV, FASTA, VCF, image, DICOM, expression matrix, clinical text, and manuscript fixtures. Cases use one of: `invoke`, `command`, `syntax`, `service_preflight`, or `environment_guard`. A retained user-facing script must use `invoke` or `command`; syntax-only cases are permitted only for non-user-facing support files.

- [ ] **Step 6: Run all script cases**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.e2e.test_cases -v`

Expected: every case passes or reports an expected environment guard with a concrete missing requirement. Unexpected exceptions, hangs, empty outputs, and undeclared dependencies fail.

- [ ] **Step 7: Commit**

```bash
git add biomed_workbench tools/catalog.json tools/build_catalog.py tests/e2e tests/unit/test_script_registry.py
git commit -m "feat: register and verify executable scripts"
```

### Task 4: Implement Public Scientific Evidence Services

**Files:**
- Create: `biomed_workbench/services/http.py`
- Create: `biomed_workbench/services/credentials.py`
- Create: `biomed_workbench/domains/evidence/literature.py`
- Create: `biomed_workbench/domains/evidence/genes.py`
- Create: `biomed_workbench/domains/evidence/proteins.py`
- Create: `biomed_workbench/domains/evidence/chemistry.py`
- Create: `biomed_workbench/domains/evidence/clinical.py`
- Create: `biomed_workbench/domains/evidence/datasets.py`
- Create: `tests/contract/test_http.py`
- Create: `tests/contract/test_evidence_services.py`
- Create: `tests/e2e/test_public_services_live.py`

**Interfaces:**
- Consumes: Task 1 capability registry.
- Produces: normalized `search_*` and `fetch_*` service capabilities returning `EvidenceItem` records.

- [ ] **Step 1: Write HTTP contract tests**

Test timeout propagation, bounded retries for 429/5xx, response-size limits, JSON/text parsing, user-agent presence, and secret-free errors. Confirm optional credentials are allowlisted and read only during invocation.

- [ ] **Step 2: Implement shared HTTP and credential policy**

`request_json()` and `request_text()` use `urllib` and injectable transports for deterministic tests. `credential(name)` rejects names outside the three-item allowlist.

- [ ] **Step 3: Port and consolidate public services**

Implement the existing connector coverage by stable endpoint family. Merge duplicate source-derived connectors. Each retained service requires a mocked response test and normalized evidence mapping.

- [ ] **Step 4: Add bounded live smoke cases**

Live tests query stable identifiers such as `TP53`, `P04637`, `1TUP`, or a one-result literature query. Tests skip only when a service explicitly requires an absent optional credential. Public zero-key services must not skip.

- [ ] **Step 5: Run contract and live tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/contract -p 'test_*.py' -v
BIOMED_LIVE_TESTS=1 PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.e2e.test_public_services_live -v
```

Expected: all mocked contracts pass; every public service returns a bounded nonempty normalized result; optional services either pass or report the exact missing allowlisted credential.

- [ ] **Step 6: Commit**

```bash
git add biomed_workbench/services biomed_workbench/domains/evidence tests/contract tests/e2e/test_public_services_live.py
git commit -m "feat: add unified scientific evidence services"
```

### Task 5: Migrate And Validate Portable Scientific Functions

**Files:**
- Create: `biomed_workbench/domains/biochemistry.py`
- Create: `biomed_workbench/domains/cell_biology.py`
- Create: `biomed_workbench/domains/genetics.py`
- Create: `biomed_workbench/domains/genomics.py`
- Create: `biomed_workbench/domains/imaging.py`
- Create: `biomed_workbench/domains/immunology.py`
- Create: `biomed_workbench/domains/microbiology.py`
- Create: `biomed_workbench/domains/molecular_biology.py`
- Create: `biomed_workbench/domains/pathology.py`
- Create: `biomed_workbench/domains/pharmacology.py`
- Create: `biomed_workbench/domains/physiology.py`
- Create: `references/capability-migration.json`
- Create: `tests/unit/test_domain_functions.py`
- Create: `tests/e2e/test_domain_capabilities.py`

**Interfaces:**
- Consumes: Task 1 registry, Task 2 runner, Task 3 fixtures, and Task 4 evidence services.
- Produces: local callables or substantive workflows for every scientifically valid retained function, plus an auditable disposition for all 227 public source functions and the one stale catalog-only record.

- [ ] **Step 1: Generate the complete function migration ledger**

Build the union of public top-level functions discovered from the inspected scientific source modules and legacy function records from the catalog. The current baseline is 227 source functions, 224 catalog records, 223 shared IDs, four source-only functions, and one stale catalog-only record. For every union member capture ID, scientific domain, dependencies, data/license risk, side effects, and one disposition: `portable`, `reimplemented`, `workflow`, or `removed`. Every disposition includes a reason and target capability ID when retained.

- [ ] **Step 2: Write failing migration-completeness tests**

```python
def test_every_legacy_function_has_one_disposition():
    old_ids = load_source_and_catalog_function_union()
    ledger = load_migration_ledger()
    self.assertEqual(old_ids, {row["legacy_id"] for row in ledger})
    self.assertEqual(len(old_ids), len(ledger))

def test_every_retained_target_resolves_and_has_e2e_case():
    for row in retained_rows():
        self.assertTrue(resolve(row["target_id"]))
        self.assertTrue(e2e_case_for(row["target_id"]))
```

- [ ] **Step 3: Verify RED and classify legal/runtime boundaries**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.unit.test_domain_functions -v`

Expected: failure listing all unclassified function IDs.

- [ ] **Step 4: Port pure and bounded scientific calculations**

Move implementations into source-neutral domain modules. Replace imports of upstream configuration, agents, and generated-code helpers with Workbench services. Preserve scientific formulas and input semantics, add parameter validation, and return structured values rather than prose-only strings where practical.

- [ ] **Step 5: Reimplement stable public-data functions**

Use Task 4 service clients for database-backed functions. Consolidate duplicates around one normalized evidence capability instead of retaining multiple source-derived IDs.

- [ ] **Step 6: Convert infrastructure-dependent functions into substantive workflows**

A workflow record must specify required inputs, executable steps, controls, outputs, interpretation checks, and stopping conditions. A title and description alone do not qualify. Functions dependent on restricted datasets, undeclared generated code, or unavailable private infrastructure are removed.

- [ ] **Step 7: Execute retained domain capability cases**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.e2e.test_domain_capabilities -v`

Expected: every retained callable executes on a minimal synthetic fixture; workflows pass structural and scientific-contract checks; removed IDs cannot resolve from the operational catalog.

- [ ] **Step 8: Commit**

```bash
git add biomed_workbench/domains references/capability-migration.json tests
git commit -m "feat: fuse portable scientific capabilities"
```

### Task 6: Integrate Open Local Model And Compute Backends

**Files:**
- Create: `biomed_workbench/services/model_backends.py`
- Create: `biomed_workbench/services/containers.py`
- Create: `biomed_workbench/services/schedulers.py`
- Create: `biomed_workbench/workflows/structure_prediction.py`
- Create: `biomed_workbench/workflows/drug_discovery.py`
- Create: `biomed_workbench/workflows/sequence_design.py`
- Create: `biomed_workbench/workflows/accelerated_genomics.py`
- Create: `references/capabilities/local-models.md`
- Create: `tests/contract/test_model_backends.py`
- Create: `tests/contract/test_compute_backends.py`
- Create: `tests/e2e/test_workflow_manifests.py`

**Interfaces:**
- Consumes: Task 1 records and Task 2 runner/runtime status.
- Produces: local backend discovery, dry-run command plans, workflow manifests, and explicit unavailable-backend results.

- [ ] **Step 1: Write failing backend safety tests**

```python
def test_missing_backend_is_explicit_not_hosted_fallback():
    result = select_backend("structure_prediction", available={})
    self.assertEqual(result.status, "unavailable")
    self.assertFalse(result.network_fallback)

def test_dry_run_never_starts_container_or_slurm_job():
    plan = build_execution_plan(EXAMPLE_INPUT, dry_run=True)
    self.assertTrue(plan.commands)
    self.assertFalse(plan.executed)
```

- [ ] **Step 2: Implement license-gated local backend registry**

Each backend record includes executable/package probes, code license, weight license, required data, CPU/GPU support, command builder, output parser, and scientific checks. Backends without verified licenses are absent rather than marked usable.

- [ ] **Step 3: Implement composite workflow manifests**

Structure prediction, docking, sequence design, and accelerated genomics produce manifests with inputs, commands, parameters, expected artifacts, validations, and unresolved requirements. Manifests never include environment values.

- [ ] **Step 4: Run backend contract and manifest tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.contract.test_model_backends tests.contract.test_compute_backends tests.e2e.test_workflow_manifests -v`

Expected: all tests pass without GPU, Docker execution, cluster access, model downloads, or vendor API keys.

- [ ] **Step 5: Commit**

```bash
git add biomed_workbench/services biomed_workbench/workflows references/capabilities tests
git commit -m "feat: add open local compute workflows"
```

### Task 7: Purge Bridge Architecture And Generate Provenance

**Files:**
- Delete: `references/biomni_functions.md`
- Delete: `references/database_connectors.md`
- Delete: `references/runtime_adapters.md`
- Delete: `references/source_file_audit.json`
- Delete: `references/source_file_audit.md`
- Delete: `references/source_manifest.json`
- Create: `references/provenance.json`
- Modify: `NOTICE.md`
- Modify: `tools/validate_workbench.py`
- Create: `tests/release/test_no_bridges.py`
- Create: `tests/release/test_provenance.py`

**Interfaces:**
- Consumes: final capability IDs from Tasks 3-6.
- Produces: legal-only provenance and release gates that prevent bridge architecture from returning.

- [ ] **Step 1: Write failing forbidden-architecture tests**

Scan operational paths, package source, catalog, skill, and README for source-specific adapter names, source checkout variables, legacy kinds, legacy run policies, and references to deleted bridge pages. Exempt only `NOTICE.md`, `references/provenance.json`, and historical design/plan documents.

- [ ] **Step 2: Create provenance records**

For each inspected source snapshot record repository URL, commit, license expression, integration method, and resulting capability IDs. Provenance must not be imported by the runtime package.

- [ ] **Step 3: Delete bridge artifacts and strengthen validator**

Validator must also enforce exact optional credential allowlist, local entrypoint resolution, e2e case completeness, and absence of credential values.

- [ ] **Step 4: Run release gates**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/release -p 'test_*.py' -v && PYTHONDONTWRITEBYTECODE=1 python3 tools/validate_workbench.py`

Expected: no forbidden bridge traces; provenance and operational catalog cover identical capability IDs where attribution applies.

- [ ] **Step 5: Commit**

```bash
git add -A references NOTICE.md tools/validate_workbench.py tests/release
git commit -m "refactor: remove source bridge architecture"
```

### Task 8: Produce Per-Script And Per-Capability Release Evidence

**Files:**
- Create: `tools/verify_capabilities.py`
- Create: `reports/capability-verification.json`
- Create: `reports/capability-verification.md`
- Create: `tests/release/test_verification_report.py`

**Interfaces:**
- Consumes: e2e cases, operational catalog, runtime probes, and test results.
- Produces: deterministic verification reports with one row per script and capability.

- [ ] **Step 1: Write failing report-completeness tests**

Require each tracked script and capability to have status, verification method, command, exit state, duration, outputs checked, and environment requirements. `pass`, `guarded`, and `removed` are valid only with evidence; `unknown` and missing rows fail release.

- [ ] **Step 2: Implement verification runner**

The runner executes bounded cases, captures stdout/stderr summaries without secrets, validates expected artifacts, and writes JSON plus a human-readable Markdown summary. It exits nonzero on unexpected failure, timeout, missing case, stale catalog, or empty expected output.

- [ ] **Step 3: Execute the full verification matrix**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_capabilities.py --all --report reports/capability-verification.json
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Expected: every row is `pass`, justified `guarded`, or documented `removed`; no unknown or unexpected failure remains.

- [ ] **Step 4: Review every guarded and removed row**

Confirm guarded rows correspond only to optional credentials, optional local packages, GPU/container/SLURM readiness, or user-owned data. Confirm removed rows are absent from the operational catalog.

- [ ] **Step 5: Commit**

```bash
git add tools/verify_capabilities.py reports tests/release/test_verification_report.py
git commit -m "test: verify every script and capability"
```

### Task 9: Rebuild Product Surface And Release v0.2.0

**Files:**
- Create: `assets/biomed-workbench-icon.png`
- Create: `assets/research-flow.png` or `assets/research-flow.svg`
- Modify: `README.md`
- Modify: `skills/biomed-workbench/SKILL.md`
- Modify: `.codex-plugin/plugin.json`
- Modify: `tools/catalog.json`
- Create: `CHANGELOG.md`
- Modify: `tests/test_release_surface.py`

**Interfaces:**
- Consumes: verified assistant behavior and reports from Tasks 1-8.
- Produces: accurate public documentation, v0.2.0 plugin metadata, installed cache, GitHub release.

- [ ] **Step 1: Write failing product-surface tests**

Require README to lead with the assistant value, show the icon and research flow, provide the verified GitHub installation commands, show three end-to-end research examples, explain zero-key operation and three optional credential families, and link the verification report.

- [ ] **Step 2: Generate and validate original visual assets**

Create a source-neutral scientific-router icon and research lifecycle diagram. Validate image dimensions, nonblank pixels, legible rendering on light/dark GitHub themes, and repository-relative Markdown paths.

- [ ] **Step 3: Rewrite skill and README around research assistance**

The skill must instruct Codex to carry tasks through framing, execution, interpretation, delivery, and audit. It must not ask users to invoke subskills or expose internal source hierarchy.

- [ ] **Step 4: Bump version and run all release checks**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 tools/validate_workbench.py
PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_capabilities.py --all --report reports/capability-verification.json
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/plugin-creator/scripts/validate_plugin.py" .
```

Expected: all tests and validators pass; plugin and catalog versions both equal `0.2.0`.

- [ ] **Step 5: Reinstall from the GitHub marketplace snapshot and verify cache**

Remove the installed v0.1.0 GitHub selector, refresh the marketplace at `main`, install `biomed-workbench@biomed-workbench`, run the validator from the installed cache, and compare hashes for the skill, runner, catalog, and verification report.

- [ ] **Step 6: Commit, push, tag, and release**

```bash
git add -A
git commit -m "release: biomed workbench v0.2.0"
git push -u origin agent/research-assistant-v0.2
```

After review and integration, tag `v0.2.0`, publish release notes describing the breaking catalog/runtime migration, and verify the GitHub installation commands from a fresh marketplace checkout.
