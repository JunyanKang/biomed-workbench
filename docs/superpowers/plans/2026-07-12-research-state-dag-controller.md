# Research State and Self-Correcting DAG Controller Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the persistent scientific project state, typed artifact and hypothesis/evidence ledgers, dynamically generated capability DAG, strict execution gateway, quality gates, and result-driven controller that turn the module registry into a self-correcting research assistant.

**Architecture:** Immutable contracts under `biomed_workbench/kernel/` represent project context, artifacts, hypotheses, evidence, decisions, and replayable state. Source-neutral components under `biomed_workbench/orchestration/` derive a capability graph entirely from module manifests, plan serial/parallel/mixed DAGs from project artifacts and evidence needs, execute only exact compatibility rows, evaluate scientific quality, adjudicate hypotheses, and revise the plan without deleting history. The existing `ResearchAssistant` and `ResearchRecord` remain compatibility facades over the new engine until a later major release.

**Tech Stack:** Python 3.14.3 standard library, immutable dataclasses, canonical JSON and SHA-256, `concurrent.futures`, existing module registry and compatibility contracts, `unittest`, Codex plugin and Skill validators.

## Non-Negotiable Constraints

- Keep one user-facing Skill and no module-specific slash commands.
- Build the graph from manifests; do not add central module IDs, assay keyword maps, or domain pipelines.
- Keep CPU, GPU, container, Slurm, remote-compute, and local-model management out of the engine.
- Preserve biological experimental units and denominators. Cells, reads, images, fields, and technical replicates do not become independent samples by default.
- Never discard refuted hypotheses, failed nodes, quality findings, superseded plans, or conflicting evidence.
- Fatal findings block execution or interpretation. Major findings require remediation or an explicit scope decision. Warnings remain attached to claims and artifacts.
- Every execution uses a validated module, dependency, tool, platform, and format compatibility row. Unknown versions block before invocation.
- Credentials and machine paths are excluded from state, events, reports, digests, and errors.
- State transitions are append-only, deterministic, serializable, replayable, and digest-verified.
- Backward-compatible `ResearchAssistant.run(...)` behavior and the existing 48 module outputs remain green throughout migration.
- Use test-first development and commit each task independently.

---

## File Structure

Create focused kernel units:

- `biomed_workbench/kernel/__init__.py`: stable public state-contract exports.
- `biomed_workbench/kernel/identity.py`: source-neutral IDs, canonical JSON, digests, redaction, and path rejection.
- `biomed_workbench/kernel/artifacts.py`: typed scientific artifacts and immutable inventory.
- `biomed_workbench/kernel/context.py`: project objective, study design, experimental units, constraints, and deliverables.
- `biomed_workbench/kernel/hypotheses.py`: falsifiable hypothesis and revision-lineage contracts.
- `biomed_workbench/kernel/evidence.py`: normalized supporting, weakening, refuting, and inconclusive evidence.
- `biomed_workbench/kernel/decisions.py`: append-only scientific decision and plan-revision events.
- `biomed_workbench/kernel/plans.py`: immutable plan-node and research-DAG state contracts.
- `biomed_workbench/kernel/state.py`: canonical project state, transitions, serialization, and replay.

Create orchestration units:

- `biomed_workbench/orchestration/__init__.py`: public graph, planner, controller, and execution exports.
- `biomed_workbench/orchestration/graph.py`: capability/artifact/relationship graph generated from manifests.
- `biomed_workbench/orchestration/planner.py`: constrained DAG search and deterministic node construction.
- `biomed_workbench/orchestration/quality.py`: artifact, project, inference, and claim quality gates.
- `biomed_workbench/orchestration/execution.py`: strict compatibility gateway and normalized execution records.
- `biomed_workbench/orchestration/interpretation.py`: deterministic evidence-to-hypothesis adjudication.
- `biomed_workbench/orchestration/controller.py`: execute, inspect, revise, resume, stop, and preserve branch state.

Modify integration and compatibility surfaces:

- `biomed_workbench/modules/contract.py`: typed executable version-probe contract.
- `biomed_workbench/modules/compatibility.py`: probe dispatch without treating service probes as shell commands.
- `biomed_workbench/services/eutils.py`: bounded E-utilities contract probe.
- `biomed_workbench/modules/builtin/*/module.json`: regenerated probe-kind fields.
- `biomed_workbench/assistant.py`: one-entry facade over project state and controller.
- `biomed_workbench/research.py`: compatibility conversion to the new state.
- `skills/biomed-workbench/SKILL.md`: stateful closed-loop operating instructions.
- `docs/architecture.md`: state, DAG, compatibility, replay, and extension semantics.
- `reports/research-engine-verification.json`: path-free contract and E2E evidence.

---

### Task 1: Make Every Tool Version Probe Executable and Typed

**Files:**
- Modify: `biomed_workbench/modules/contract.py`
- Modify: `biomed_workbench/modules/compatibility.py`
- Modify: `biomed_workbench/services/eutils.py`
- Modify: `tools/module_migration_definitions.py`
- Modify: `tools/migrate_capabilities_to_modules.py`
- Regenerate: `biomed_workbench/modules/builtin/*/module.json`
- Regenerate: `biomed_workbench/modules/index.json`
- Regenerate: `tools/catalog.json`
- Test: `tests/unit/test_module_contract.py`
- Test: `tests/unit/test_module_compatibility.py`
- Test: `tests/contract/test_service_version_probe.py`

**Interfaces:**
- Add `ToolRequirement.version_probe_kind: Literal["command", "python_callable", "service_contract"]`.
- Add `ToolRequirement.version_probe_timeout_seconds: int` with range `1..30`.
- Add `probe_eutils_contract() -> str` returning the exact supported contract token only after a bounded live EInfo shape check.
- Extend `detect_environment(..., callable_probe_runner, service_probe_runner)` without changing exact-row matching.

- [x] **Step 1: Write failing typed-probe contract tests**

```python
def test_service_probe_is_not_dispatched_as_a_shell_command():
    manifest = parse_manifest(eutils_manifest_payload())
    shell_calls = []
    snapshot = detect_environment(
        manifest,
        probe_runner=lambda command, timeout: shell_calls.append(command) or "",
        service_probe_runner=lambda target, timeout: "contract-2026-03-04",
        dependency_provider=lambda name, ecosystem: "3.14.3",
    )
    assert shell_calls == []
    assert snapshot.tools == {"ncbi-eutils": "contract-2026-03-04"}

def test_unknown_service_contract_version_blocks_before_entrypoint():
    decision = evaluate_compatibility(
        eutils_manifest(),
        EnvironmentSnapshot({"ncbi-eutils": "contract-2027-01-01"}, {"python": "3.14.3"}, "any"),
        valid_eutils_artifacts(),
    )
    assert decision.allowed is False
    assert "UNVALIDATED_TOOL_VERSION" in {finding.code for finding in decision.findings}
```

- [x] **Step 2: Run and verify the old untyped probe behavior fails**

Run: `python3 -m unittest tests.unit.test_module_contract tests.unit.test_module_compatibility tests.contract.test_service_version_probe`

Expected: parser rejects the new fields and service dispatch is unavailable.

- [x] **Step 3: Implement strict probe parsing and dispatch**

Use a frozen probe-kind enum, reject shell metacharacters for command probes, require `module:function` for Python callables, require an HTTPS target plus project-owned probe callable for service contracts, and cap each probe timeout at 30 seconds. `probe_eutils_contract()` must request EInfo JSON, verify `einforesult` and database metadata structure, and return `contract-2026-03-04`; malformed or unavailable responses return no detected version and therefore block required service modules.

- [x] **Step 4: Regenerate and verify all 48 manifests**

Run:

```bash
python3 tools/migrate_capabilities_to_modules.py
python3 tools/build_module_index.py
python3 tools/build_catalog.py
python3 -m unittest tests.release.test_module_migration tests.release.test_module_packaging
```

Expected: 48 valid modules, 9 typed service-tool probes, 48 compatibility rows, and unchanged capability IDs.

- [x] **Step 5: Commit**

```bash
git add biomed_workbench/modules biomed_workbench/services/eutils.py tools tests/contract/test_service_version_probe.py tests/unit
git commit -m "feat: execute typed scientific version probes"
```

---

### Task 2: Define Canonical Project Context and Typed Scientific Artifacts

**Files:**
- Create: `biomed_workbench/kernel/__init__.py`
- Create: `biomed_workbench/kernel/identity.py`
- Create: `biomed_workbench/kernel/context.py`
- Create: `biomed_workbench/kernel/artifacts.py`
- Test: `tests/unit/kernel/test_identity.py`
- Test: `tests/unit/kernel/test_context.py`
- Test: `tests/unit/kernel/test_artifacts.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class ProjectContext:
    project_id: str
    objective: str
    scientific_question: str
    species: tuple[str, ...]
    biological_scope: dict[str, str]
    study_design: str
    experimental_unit: str
    comparisons: tuple[Comparison, ...]
    constraints: tuple[Constraint, ...]
    required_deliverables: tuple[str, ...]
    required_evidence_types: tuple[str, ...]
    privacy_level: str

@dataclass(frozen=True)
class ScientificArtifact:
    id: str
    artifact_type: str
    schema_version: str
    format_name: str
    format_version: str
    compression: str
    producing_module_id: str | None
    producing_module_version: str | None
    source_artifact_ids: tuple[str, ...]
    scientific_scope: dict[str, str]
    experimental_unit: str
    denominator: str
    processing_level: str
    quality_status: str
    coordinate_system: str | None
    genome_build: str | None
    annotation_release: str | None
    identifier_namespace: str | None
    producer_tool_versions: dict[str, str]
    content: dict[str, object]
    content_digest: str
```

- [x] **Step 1: Write failing immutability, denominator, and digest tests**

Test exact IDs, nonempty objective/question, unique comparison IDs, explicit experimental unit and denominator, closed known enums, digest recomputation, nested secret redaction, machine-path rejection, and detached serialization.

- [x] **Step 2: Run and verify kernel imports fail**

Run: `python3 -m unittest discover -s tests/unit/kernel -p 'test*.py'`

Expected: imports fail because `biomed_workbench.kernel` does not exist.

- [x] **Step 3: Implement canonical identity and artifact contracts**

`canonical_json()` sorts keys and uses compact UTF-8 JSON. `content_digest()` hashes the redacted canonical payload. IDs use source-neutral lowercase tokens plus a caller-supplied stable namespace. Reject absolute paths, `file://`, credential-shaped keys, non-finite numbers, unordered sets, and digest mismatches. Preserve format version, genome build, annotation release, orientation, and producer versions as scientific data.

- [x] **Step 4: Run focused tests and commit**

```bash
python3 -m unittest discover -s tests/unit/kernel -p 'test*.py'
git add biomed_workbench/kernel tests/unit/kernel
git commit -m "feat: define typed scientific project artifacts"
```

---

### Task 3: Build Falsifiable Hypothesis and Normalized Evidence Ledgers

**Files:**
- Create: `biomed_workbench/kernel/hypotheses.py`
- Create: `biomed_workbench/kernel/evidence.py`
- Modify: `biomed_workbench/kernel/__init__.py`
- Test: `tests/unit/kernel/test_hypotheses.py`
- Test: `tests/unit/kernel/test_evidence.py`

**Interfaces:**

```python
HYPOTHESIS_STATUSES = {"proposed", "active", "supported", "weakened", "refuted", "inconclusive"}
EVIDENCE_RELATIONS = {"supports", "weakens", "refutes", "inconclusive"}

@dataclass(frozen=True)
class Hypothesis:
    id: str
    statement: str
    biological_scope: dict[str, str]
    experimental_unit: str
    comparison_id: str
    expected_direction: str
    expected_observations: tuple[str, ...]
    disconfirming_observations: tuple[str, ...]
    alternative_explanations: tuple[str, ...]
    required_evidence_types: tuple[str, ...]
    minimum_independent_evidence_groups: int
    permitted_claim_strength: str
    status: str
    supporting_evidence_ids: tuple[str, ...]
    conflicting_evidence_ids: tuple[str, ...]
    missing_evidence_types: tuple[str, ...]
    parent_hypothesis_id: str | None
    revision: int

@dataclass(frozen=True)
class EvidenceRecord:
    id: str
    hypothesis_id: str
    artifact_id: str
    relation: str
    evidence_type: str
    independent_group: str
    study_design: str
    experimental_unit: str
    effect: dict[str, object]
    uncertainty: dict[str, object]
    quality_status: str
    limitations: tuple[str, ...]
    rationale: str
```

- [x] **Step 1: Write failing falsifiability and anti-confirmation-bias tests**

Reject hypotheses without disconfirming observations or alternatives. Reject evidence without an experimental unit, uncertainty, rationale, or linked artifact. Verify weakening and refuting evidence remain separate from support and that two records with the same `independent_group` count as one orthogonal group.

- [x] **Step 2: Run and verify missing ledger failures**

Run: `python3 -m unittest tests.unit.kernel.test_hypotheses tests.unit.kernel.test_evidence`

- [x] **Step 3: Implement immutable ledger operations**

Provide `add_hypothesis`, `revise_hypothesis`, `add_evidence`, and `evidence_partition`. Revisions create a new hypothesis value with incremented revision and parent linkage; they never mutate or remove the prior value. Duplicate evidence IDs or contradictory duplicate relations for the same artifact/hypothesis pair are rejected.

- [x] **Step 4: Run tests and commit**

```bash
python3 -m unittest tests.unit.kernel.test_hypotheses tests.unit.kernel.test_evidence
git add biomed_workbench/kernel tests/unit/kernel
git commit -m "feat: add falsifiable hypothesis and evidence ledgers"
```

---

### Task 4: Add Append-Only Decisions, State Transitions, and Replay

**Files:**
- Create: `biomed_workbench/kernel/decisions.py`
- Create: `biomed_workbench/kernel/plans.py`
- Create: `biomed_workbench/kernel/state.py`
- Modify: `biomed_workbench/kernel/__init__.py`
- Test: `tests/unit/kernel/test_state.py`
- Test: `tests/contract/test_state_replay.py`

**Interfaces:**

```python
NODE_STATUSES = {"pending", "ready", "running", "completed", "blocked", "failed", "superseded", "skipped"}

@dataclass(frozen=True)
class PlanNode:
    id: str
    module_id: str
    input_bindings: dict[str, str]
    dependencies: tuple[str, ...]
    branch_id: str
    target_hypothesis_ids: tuple[str, ...]
    expected_evidence_types: tuple[str, ...]
    expected_output_artifact_types: tuple[str, ...]
    planned_output_artifact_ids: dict[str, str]
    compatibility_row_candidates: tuple[str, ...]
    status: str
    attempt: int

@dataclass(frozen=True)
class ResearchDAG:
    id: str
    objective: str
    nodes: tuple[PlanNode, ...]
    required_output_artifact_types: tuple[str, ...]
    plan_type: str
    revision: int
    parent_plan_id: str | None
    rationale: tuple[str, ...]
    digest: str

@dataclass(frozen=True)
class DecisionEvent:
    id: str
    sequence: int
    event_type: str
    rationale: str
    trigger_finding_ids: tuple[str, ...]
    affected_artifact_ids: tuple[str, ...]
    affected_hypothesis_ids: tuple[str, ...]
    superseded_action_ids: tuple[str, ...]
    replacement_action_ids: tuple[str, ...]
    prior_results_valid: bool
    payload: dict[str, object]
    prior_state_digest: str
    resulting_state_digest: str

@dataclass(frozen=True)
class ProjectState:
    schema_version: int
    context: ProjectContext
    artifacts: tuple[ScientificArtifact, ...]
    hypotheses: tuple[Hypothesis, ...]
    evidence: tuple[EvidenceRecord, ...]
    decisions: tuple[DecisionEvent, ...]
    plans: tuple[ResearchDAG, ...]
    active_plan_id: str | None
    revision: int
    state_digest: str
```

- [x] **Step 1: Write failing transition and replay tests**

Test monotonic event sequences, exact prior/result digest linkage, immutable refuted hypotheses, preserved failed artifacts, secret/path rejection, canonical round trip, tamper detection, replay equivalence, and rejection of events that reference unknown state objects.

- [x] **Step 2: Run and verify missing state engine**

Run: `python3 -m unittest tests.unit.kernel.test_state tests.contract.test_state_replay`

- [x] **Step 3: Implement validated event application and replay**

Implement explicit event handlers for context creation, artifact registration, hypothesis addition/revision, evidence addition, plan creation/revision, node status, quality finding, and delivery readiness. `apply_event(state, event_payload)` calculates the next digest; `replay(context, events)` starts from a canonical empty state and verifies every link. Unknown event types fail closed.

- [x] **Step 4: Run tests and commit**

```bash
python3 -m unittest tests.unit.kernel.test_state tests.contract.test_state_replay
git add biomed_workbench/kernel tests/unit/kernel tests/contract/test_state_replay.py
git commit -m "feat: persist and replay scientific project state"
```

---

### Task 5: Generate the Dynamic Capability Graph From Module Manifests

**Files:**
- Create: `biomed_workbench/orchestration/__init__.py`
- Create: `biomed_workbench/orchestration/graph.py`
- Test: `tests/unit/orchestration/test_capability_graph.py`
- Test: `tests/e2e/test_future_module_graph.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    relation: str
    metadata: dict[str, object]

@dataclass(frozen=True)
class CapabilityGraph:
    module_ids: tuple[str, ...]
    artifact_types: tuple[str, ...]
    edges: tuple[GraphEdge, ...]
    digest: str

def build_capability_graph(registry: ModuleRegistry) -> CapabilityGraph: ...
def producers(graph, artifact_type) -> tuple[str, ...]: ...
def consumers(graph, artifact_type) -> tuple[str, ...]: ...
```

- [x] **Step 1: Write failing graph construction tests**

Assert `consumes`, `produces`, `alternative-to`, `complements`, `validates`, `addresses-intent`, and `addresses-question` edges derive only from manifests; graph order and digest are deterministic; unknown relationships fail; no module ID literals appear in graph source.

- [x] **Step 2: Prove a future module changes the graph without code edits**

Create a temporary module that consumes `quality_report`, produces `novel_biomarker_table`, and uses domain `systems_biology`. Discover it, rebuild, and assert the new nodes and edges appear while `graph.py` remains unchanged.

- [x] **Step 3: Implement graph construction**

Use bipartite module/artifact nodes plus relationship edges. Add validation edges from modules whose type is `validation` to their consumed and produced artifact families. Preserve all domains as metadata rather than graph partitions.

- [x] **Step 4: Run tests and commit**

```bash
python3 -m unittest tests.unit.orchestration.test_capability_graph tests.e2e.test_future_module_graph
git add biomed_workbench/orchestration tests/unit/orchestration tests/e2e/test_future_module_graph.py
git commit -m "feat: derive capability graph from module manifests"
```

---

### Task 6: Plan Valid Single, Serial, Parallel, and Mixed Research DAGs

**Files:**
- Create: `biomed_workbench/orchestration/planner.py`
- Test: `tests/unit/orchestration/test_planner.py`
- Test: `tests/contract/test_dag_validity.py`

**Interfaces:**

```python
def plan_research(state, registry, graph, requests) -> ResearchDAG: ...
```

- [x] **Step 1: Write failing constrained-planning tests**

Test direct single-module plans, dependent serial plans, independent parallel branches, mixed convergence, missing-artifact blockage, quality-invalid input exclusion, credential-aware ranking, exact compatibility candidate recording, orthogonal evidence requirements, cycle rejection, deterministic topological order, and declared-alternative selection.

- [x] **Step 2: Run and verify planner import failure**

Run: `python3 -m unittest tests.unit.orchestration.test_planner tests.contract.test_dag_validity`

- [x] **Step 3: Implement constrained graph search**

Search backward from requested artifact and evidence types to currently available valid artifacts. Rank paths by satisfied preconditions, validated format continuity, maturity, directness, independent evidence gain, nonfatal quality risk, optional credential burden, and node count in that order. Never choose a shorter path that violates an experimental-unit, format, identifier, or quality requirement.

- [x] **Step 4: Run tests and commit**

```bash
python3 -m unittest tests.unit.orchestration.test_planner tests.contract.test_dag_validity
git add biomed_workbench/orchestration/planner.py tests/unit/orchestration tests/contract/test_dag_validity.py
git commit -m "feat: plan dynamic scientific capability dags"
```

---

### Task 7: Enforce Cross-Module Scientific Quality and Inference Gates

**Files:**
- Create: `biomed_workbench/orchestration/quality.py`
- Test: `tests/unit/orchestration/test_quality.py`
- Test: `tests/contract/test_scientific_inference_gates.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class QualityFinding:
    id: str
    code: str
    severity: str
    subject_ids: tuple[str, ...]
    message: str
    blocks_execution: bool
    blocks_interpretation: bool
    remediation_artifact_types: tuple[str, ...]

def evaluate_project_quality(state, node, manifest) -> tuple[QualityFinding, ...]: ...
def interpretation_allowed(findings) -> bool: ...
```

- [ ] **Step 1: Write failing scientific-gate tests**

Cover identifier mismatch, genome-build mismatch, coordinate mismatch, unit mismatch, denominator mismatch, processing-level mismatch, duplicated evidence, circular validation, pseudoreplication, complete confounding, outcome-informed threshold change, unsupported causal language, claim-evidence drift, and privacy violation. Verify fatal and major findings block interpretation while warning and info findings remain attached.

- [ ] **Step 2: Run and verify missing quality engine**

Run: `python3 -m unittest tests.unit.orchestration.test_quality tests.contract.test_scientific_inference_gates`

- [ ] **Step 3: Implement deterministic cross-project gates**

Use artifact and context metadata only; do not infer missing units, identifiers, builds, or denominators from names. Every finding has stable code, linked subjects, remediation artifact types, and a content-derived ID. A quality waiver is a decision event that narrows scope; it never deletes the finding or changes fatal to pass.

- [ ] **Step 4: Run tests and commit**

```bash
python3 -m unittest tests.unit.orchestration.test_quality tests.contract.test_scientific_inference_gates
git add biomed_workbench/orchestration/quality.py tests/unit/orchestration tests/contract/test_scientific_inference_gates.py
git commit -m "feat: gate cross-module scientific interpretation"
```

---

### Task 8: Execute DAG Nodes Through the Strict Compatibility Gateway

**Files:**
- Create: `biomed_workbench/orchestration/execution.py`
- Modify: `biomed_workbench/runner.py`
- Modify: `biomed_workbench/models.py`
- Test: `tests/unit/orchestration/test_execution.py`
- Test: `tests/contract/test_execution_provenance.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class NodeExecution:
    node_id: str
    module_id: str
    module_version: str
    status: str
    compatibility_row_id: str | None
    input_artifact_ids: tuple[str, ...]
    output_artifact_ids: tuple[str, ...]
    quality_finding_ids: tuple[str, ...]
    provenance: dict[str, object]
    safe_error_class: str | None

def execute_node(state, dag, node, registry, environment_provider, executor) -> NodeExecution: ...
```

- [ ] **Step 1: Write failing pre-execution and provenance tests**

Assert input schema validation, mutation permission, exact environment detection, exact artifact snapshots, compatibility decision, entrypoint non-invocation on mismatch, output schema validation, output-size bound, module/tool/dependency/format provenance, parameter/output digests, safe errors, and absence of credentials and paths.

- [ ] **Step 2: Run and verify gateway import failure**

Run: `python3 -m unittest tests.unit.orchestration.test_execution tests.contract.test_execution_provenance`

- [ ] **Step 3: Implement normalized node execution**

Convert `ScientificArtifact` metadata to `ArtifactSnapshot`, run project quality gates, detect only declared versions, call `invoke_compatible`, create one output artifact per declared output port, and append node/provenance events. Preserve completed upstream artifacts when a downstream node blocks or fails.

- [ ] **Step 4: Keep direct runner compatibility**

Retain `run(capability_id, inputs)` for v0.2 callers. Add `run_compatible(...)` for the controller and route all new stateful execution through it. Existing direct tests remain unchanged while new controller tests prove strict preflight behavior.

- [ ] **Step 5: Run tests and commit**

```bash
python3 -m unittest tests.unit.test_runner tests.unit.orchestration.test_execution tests.contract.test_execution_provenance
git add biomed_workbench/orchestration/execution.py biomed_workbench/runner.py biomed_workbench/models.py tests
git commit -m "feat: execute research dags through compatibility gates"
```

---

### Task 9: Adjudicate Hypotheses Without Erasing Conflict or Uncertainty

**Files:**
- Create: `biomed_workbench/orchestration/interpretation.py`
- Test: `tests/unit/orchestration/test_interpretation.py`
- Test: `tests/contract/test_hypothesis_adjudication.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class HypothesisAssessment:
    hypothesis_id: str
    previous_status: str
    new_status: str
    supporting_ids: tuple[str, ...]
    conflicting_ids: tuple[str, ...]
    independent_support_groups: tuple[str, ...]
    missing_evidence_types: tuple[str, ...]
    alternative_explanations_to_test: tuple[str, ...]
    rationale: str

def assess_hypothesis(hypothesis, evidence, findings) -> HypothesisAssessment: ...
```

- [ ] **Step 1: Write failing adjudication tests**

Verify refuting evidence overrides support for the same predicted observation, conflicting high-quality evidence yields weakened or inconclusive rather than averaging, support requires the declared orthogonality count, major/fatal findings prevent supported status, absence of evidence is not refutation, and causal claim strength requires an appropriate design.

- [ ] **Step 2: Run and verify interpretation import failure**

Run: `python3 -m unittest tests.unit.orchestration.test_interpretation tests.contract.test_hypothesis_adjudication`

- [ ] **Step 3: Implement rule-explicit assessment**

Partition by relation, quality, evidence type, and independent group. Record all IDs used in the assessment. Status transitions are deterministic and auditable; they do not generate biological prose or invoke another model. Codex remains responsible for narrative interpretation grounded in this structured result.

- [ ] **Step 4: Run tests and commit**

```bash
python3 -m unittest tests.unit.orchestration.test_interpretation tests.contract.test_hypothesis_adjudication
git add biomed_workbench/orchestration/interpretation.py tests
git commit -m "feat: adjudicate hypotheses from conflicting evidence"
```

---

### Task 10: Build the Execute-Inspect-Revise-Resume Controller

**Files:**
- Create: `biomed_workbench/orchestration/controller.py`
- Test: `tests/unit/orchestration/test_controller.py`
- Test: `tests/contract/test_controller_recovery.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class ControllerPolicy:
    max_plan_revisions: int
    max_node_attempts: int
    parallel_workers: int
    stop_on_fatal: bool

@dataclass(frozen=True)
class CycleResult:
    state: ProjectState
    active_plan: ResearchDAG
    executions: tuple[NodeExecution, ...]
    assessments: tuple[HypothesisAssessment, ...]
    stop_reason: str

class ResearchController:
    def advance(self, state: ProjectState, plan: ResearchDAG) -> CycleResult: ...
    def resume(self, serialized_state: dict[str, object]) -> CycleResult: ...
```

- [ ] **Step 1: Write failing controller behavior tests**

Cover serial dependency execution, parallel independent branches, mixed convergence, branch isolation, fatal block, major remediation node insertion, alternative-module substitution, transient failure retry bound, permanent failure preservation, evidence ingestion, hypothesis status change, plan revision lineage, max-revision stop, resume after interruption, and deterministic event ordering despite parallel completion order.

- [ ] **Step 2: Run and verify controller import failure**

Run: `python3 -m unittest tests.unit.orchestration.test_controller tests.contract.test_controller_recovery`

- [ ] **Step 3: Implement dependency-aware execution**

Ready nodes have all dependencies completed and valid input artifacts. Execute independent ready nodes with `ThreadPoolExecutor`; merge results in stable node-ID order. Never share mutable branch state. Failed downstream branches do not invalidate completed independent branches.

- [ ] **Step 4: Implement revision policy**

Fatal findings block the affected branch. Major findings create remediation requests when a producer exists; otherwise the branch remains blocked. Compatibility findings select only declared alternatives whose own preflight passes. New evidence triggers hypothesis assessment and, when required evidence remains missing or conflict persists, a child plan with explicit superseded and replacement node IDs.

- [ ] **Step 5: Run tests and commit**

```bash
python3 -m unittest tests.unit.orchestration.test_controller tests.contract.test_controller_recovery
git add biomed_workbench/orchestration/controller.py tests
git commit -m "feat: control self-correcting research cycles"
```

---

### Task 11: Integrate the Unified Assistant and Preserve the v0.2 Facade

**Files:**
- Modify: `biomed_workbench/assistant.py`
- Modify: `biomed_workbench/research.py`
- Modify: `skills/biomed-workbench/SKILL.md`
- Test: `tests/unit/test_assistant.py`
- Test: `tests/e2e/test_stateful_assistant.py`
- Test: `tests/e2e/test_skill_entrypoint.py`

**Interfaces:**
- Add `ResearchAssistant.start(context, artifacts, hypotheses, requests) -> CycleResult`.
- Add `ResearchAssistant.continue_project(state, requests=()) -> CycleResult`.
- Keep `ResearchAssistant.run(objective, actions=..., ...) -> AssistantResult` by converting actions into a one-cycle compatibility DAG and converting the final state back to `ResearchRecord`.

- [ ] **Step 1: Write failing one-entry and compatibility tests**

Test natural project state creation, no user-facing module selection requirement, automatic graph/planner/controller use, state continuation, explicit gates and hypothesis changes in output, no routing scores in scientific delivery, secret/path-free serialization, and unchanged existing assistant tests.

- [ ] **Step 2: Run and verify stateful APIs are absent**

Run: `python3 -m unittest tests.unit.test_assistant tests.e2e.test_stateful_assistant tests.e2e.test_skill_entrypoint`

- [ ] **Step 3: Implement facade conversion**

The compatibility facade preserves legacy lifecycle stage order and fields. The stateful API exposes current question, active hypotheses, passed/failed gates, executed branches, evidence effects, plan revisions, unresolved requirements, and stop reason. It never asks users to invoke internal modules by ID.

- [ ] **Step 4: Update Skill operating instructions**

Require Codex to inspect or initialize project state, formulate disconfirming observations and alternatives, request or infer artifact metadata without guessing versions, call the stateful planner/controller, report plan revisions, and open a new task only for plugin reload rather than for ordinary project continuation.

- [ ] **Step 5: Run tests and commit**

```bash
python3 -m unittest tests.unit.test_assistant tests.e2e.test_stateful_assistant tests.e2e.test_skill_entrypoint
git add biomed_workbench/assistant.py biomed_workbench/research.py skills/biomed-workbench tests
git commit -m "feat: expose one stateful scientific assistant entry"
```

---

### Task 12: Verify Diverse Revision Scenarios, Replay, and Release Evidence

**Files:**
- Create: `tests/e2e/test_research_cycle_scenarios.py`
- Create: `tests/fixtures/research-cycles/omics-quality-revision.json`
- Create: `tests/fixtures/research-cycles/clinical-conflict-revision.json`
- Create: `tests/fixtures/research-cycles/molecular-validation-revision.json`
- Create: `tests/fixtures/research-cycles/publication-review-revision.json`
- Create: `reports/research-engine-verification.json`
- Create: `tests/release/test_research_engine_evidence.py`
- Modify: `docs/architecture.md`
- Modify: `README.md`
- Modify: `tools/validate_workbench.py`

- [ ] **Step 1: Write failing multi-domain release scenarios**

Each fixture must contain a context, at least one falsifiable hypothesis, typed inputs, requested evidence/deliverables, a controlled module-output sequence, one failed or major gate, one plan revision, one hypothesis status transition, a final evidence ledger, and an expected replay digest. Scenarios must collectively exercise single, serial, parallel, and mixed DAGs.

- [ ] **Step 2: Run and verify missing scenario support**

Run: `python3 -m unittest tests.e2e.test_research_cycle_scenarios tests.release.test_research_engine_evidence`

- [ ] **Step 3: Add path-free verification report**

Record contract counts, graph node/edge counts, scenario IDs, plan types, gate severities, revision counts, hypothesis transitions, replay success, strict compatibility blocks, alternative substitutions, module count, registry digest, test count, and explicit limitations. Do not record raw inputs, paths, credentials, usernames, or source-library names.

- [ ] **Step 4: Add release gates**

`validate_workbench.py --release` must verify kernel and DAG report digests, one Skill, 48 modules, no central module IDs in orchestration source, no machine paths or credentials in state fixtures/reports, all fixture replay digests, and that every scenario includes a failed gate, revision, hypothesis transition, and final evidence ledger.

- [ ] **Step 5: Run complete validation**

```bash
python3 -m unittest discover -s tests -p 'test*.py'
python3 tools/validate_workbench.py --release
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/biomed-workbench
git diff --check
```

Expected: all tests and validators pass, 48 modules remain registered, every unsupported version test blocks before execution, and all scenario states replay to their recorded digest.

- [ ] **Step 6: Commit**

```bash
git add tests/e2e tests/fixtures/research-cycles tests/release reports/research-engine-verification.json docs README.md tools/validate_workbench.py
git commit -m "test: verify self-correcting scientific research cycles"
```

---

## Plan Self-Review

- **Spec coverage:** Task 1 closes the service-version probe gap. Tasks 2-4 implement project context, typed artifacts, falsifiable hypotheses, normalized evidence, decisions, state, and replay. Tasks 5-6 build manifest-derived graph planning. Tasks 7-10 implement quality, strict execution, interpretation, revision, alternatives, parallelism, recovery, and resume. Task 11 preserves the one-entry experience and v0.2 facade. Task 12 verifies multi-domain cycles, release evidence, and official validators.
- **Scientific safeguards:** Experimental units, denominators, orthogonality, conflicting evidence, causal scope, quality severity, and plan revision history are first-class contracts rather than prose-only guidance.
- **Version safeguards:** Tool, dependency, platform, and format compatibility remains exact and moves into every stateful node execution. The E-utilities service probe becomes executable and cannot be mistaken for a local command.
- **Extensibility:** Graph, planner, quality engine, and controller consume module metadata and artifact contracts. A future module changes discovery and planning without edits to central routing or orchestration source.
- **Scope boundary:** This plan builds the general research kernel and controller. It does not claim the remaining source-union scientific breadth, complete all specialized omics tool modules, or publish the GitHub release; those remain subsequent goal stages.
- **Type consistency:** `ProjectContext`, `ScientificArtifact`, `Hypothesis`, `EvidenceRecord`, `DecisionEvent`, `ProjectState`, `PlanNode`, `ResearchDAG`, `QualityFinding`, `NodeExecution`, `HypothesisAssessment`, and `CycleResult` are introduced before their consumers and keep stable names throughout the plan.
- **Placeholder scan:** Every task names exact files, interfaces, red tests, implementation rules, verification commands, expected outcomes, and commit boundaries.
