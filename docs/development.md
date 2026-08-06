# Development And Release

This guide is for maintainers and agents extending Biomed Workbench. User-facing installation and scientific usage live in [installation](installation.md) and [using Biomed Workbench](using-biomed-workbench.md).

## Repository Verification

Run the release validator and complete test suite from the repository root:

```bash
python3 tools/validate_workbench.py --release
python3 -m unittest discover -s tests -v
```

Verify the Codex installation surface with the active CLI:

```bash
python3 tools/verify_codex_install.py --codex-cli "$(command -v codex)"
```

## Developer Interfaces

Inspect routing, discovery, and bounded execution during module development:

```bash
python3 tools/route_task.py "single-cell analysis and manuscript review"
python3 tools/search_tools.py --workflow publication reviewer --limit 5
python3 tools/run_tool.py --help
python3 tools/project_workflow.py --help
```

These interfaces are for development, validation, and agent integration. Public execution requires an existing project root, exact artifact bindings, an approved analysis admission, and one declared compatibility row; there is no path that executes a scientific module from an unbound JSON object. End users should invoke the unified `biomed-workbench` skill with a scientific request rather than call internal scripts.

## Key Directories

- `skills/biomed-workbench/`: the single user-facing Codex skill.
- `biomed_workbench/modules/builtin/`: independently discoverable scientific modules.
- `biomed_workbench/capabilities/`: source-neutral scientific implementations.
- `biomed_workbench/kernel/`: project context, artifacts, hypotheses, evidence, decisions, and replay state.
- `biomed_workbench/orchestration/`: planning, compatibility-gated execution, quality checks, interpretation, and revision control.
- `biomed_workbench/formats/`: shared format profiles and pre-execution metadata validation.
- `biomed_workbench/services/`: bounded public scientific database clients and credential policy.
- `tools/`: registry, routing, execution, scaffolding, validation, evidence, and installation verification.
- `tests/`: unit, contract, integration, release, and end-to-end checks.
- `reports/`: release-safe generated evidence and verification summaries.

## Adding A Scientific Module

Create an independent module with a stable ID, scientific description, input and output contracts, compatibility policy, quality gates, and representative tests. Bioinformatics analysis modules must include at least one substantive Python or R template with real parameterization, validation, serialization, failure handling, version provenance, and scientific quality checks.

Every `agent_generated` workflow additionally requires one versioned `observed_output_contract` per output port. Container and family admission prove that the returned tables, archives, HDF5 objects, figures, structures, identities, accounting and primary bytes satisfy their frozen family rules. Manifest quality gates are a separate layer: each gate is assigned once to an evidence-capable port and classified by its required evidence. A gate is system-provenance only when an exact dedicated evaluator emits the complete declared observations; gate names never select an automatic evaluator. Gates without that implementation remain `requires_review`, never promoted from family admission. The centralized observed-output protocol registry currently supports `2.1.0`; handoff creation, state loading, event replay, and execution ingest reject unknown or legacy versions rather than silently weakening coverage. The protocol freezes a sorted, unique gate-ID set and its digest, then requires a structured result and digest for every member on return. The handoff contract also binds each packaged evaluator's callable identity, evaluator-contract version, and packaged source digest. A real evaluator `failed` result is reloaded as a negative artifact and receives only the exact plugin-created automatic rejection; `requires_review` and `not_evaluable` remain manual decisions and cannot be released by caller-supplied automatic metadata. Artifact imports are transactional, so a container or family-admission failure leaves neither state references nor newly created orphan objects. Each pending gate requires an immutable `ScientificGateAdjudication` that binds the observed value, frozen criterion, finding, result digest, and evidence digest. The artifact review and decision bind the exact adjudication IDs and set digest, and those records enter delivery-slice and evidence-map identity. Complete adjudications make negative results reviewable, but only accepted gates can be retained: rejected or unresolved gates require a major or fatal review plus exclusion, rerun, method change, more data, plan revision, or branch stop. New modules require family fixtures, gate-level negative fixtures, and both positive and negative state reachability tests before release.

Rerun and method-switch actions use a registry-validated child plan prepared after artifact review and before the scientific decision. Its node-level revision contract freezes the source and target nodes, action, source and target manifest digests, typed port mappings, observed and planned request identities, structured parameter overrides, and rationale. Every output from one producing node must share that contract, action, target, and request identity. A same-method rerun preserves the observed request identity; an adjusted rerun freezes a different identity after command-parameter normalization. A method switch must use an explicit `revision_alternatives` relation with validated input, output, additional-artifact, and parameter mappings. Ordinary `alternatives` remain routing or recommendation relationships. Untouched downstream nodes are recreated against the mapped replacement outputs, and the replacement requires a new analysis admission before execution. Public FastQC scenarios cover both adjusted rerun and FastQC-to-fastp method switching through actual command execution and artifact reload.

Project state schema v2 records migration provenance. A digest-valid v1 state is replayed into v2 only when every added gate field can be recovered exactly from its original receipt; the migration retains the source digest and event count. Map-bound v1 states use the separate `migrate-state-v1` path, which verifies the immutable publication store and writes a distinct v2 file without overwriting the old state. The command reports exact scientific-dependency blockers. If prior admission was not serialized, a `historical-unavailable` recovery record documents the gap without claiming approval; it is accepted only for project snapshots and blocks delivery authorization and validated delivery. The public regression completes review and decision recovery, publishes the next map revision through `project map`, verifies the new immutable store, and reloads the resulting state.

```bash
python3 tools/create_module.py --help
python3 tools/scaffold_bioinformatics_templates.py --check
```

The generated registry is source-neutral and dynamically discovers valid modules. Routing aliases, exclusions, required context, named-method priority, scientific stage, and reviewed-upstream requirements belong in the manifest. Do not add a new user-facing skill for each method, encode module names in the routing algorithm, maintain a second plan-stage table, vendor a source project, or introduce a path bridge to external code.

## Release Discipline

- Regenerate deterministic registry and report artifacts before release.
- Version scientific implementations, runtime compatibility, module-scoped evidence, and documentation separately. A global registry or documentation change never invalidates scientific outputs by itself; a module metadata change requires reviewed scope reissue; a runtime-policy change requires targeted compatibility retesting; only a scientific implementation, parameter-semantic, input-processing, or output-recognition change requires recomputation.
- Routing and orchestration metadata are discovery-only evidence scope. They change registry discovery and plan compilation, but they cannot reissue or invalidate an unchanged scientific execution receipt.
- External-result admission contracts carry a separate protocol version and handoff digest. Tightening that controller boundary changes future handoffs without reissuing an unchanged scientific computation.
- A declared fixture and an executed fixture are separate readiness axes. Process-JSON round trips and serialized artifact-payload reloads are reported separately. A receipt records module/version/compatibility identity, the case digest, complete normalized output digest, validated projection digest, actual runtime versions, reload method, and round-trip kind.
- Run `tools/assess_report_revalidation.py` before reissuing or rerunning observed evidence. Never rebind a changed scientific implementation to old outputs, and never spend compute merely because an unrelated global digest changed.
- Keep plugin, catalog, and release versions consistent.
- Run compatibility regression and representative execution checks when changing a baseline or widening a policy.
- Run the full test suite, release validator, isolated plugin install verification, and complete-history secret scan.
- Review generated reports for local paths, credentials, temporary files, and bridge artifacts.
- Keep README counts and public claims synchronized with generated evidence.

## Reference Host And Adapter Boundaries

Codex is the fully validated reference host. Optional Agent Skills and MCP support are interoperability adapters that read the existing skill, registry, router, and runner. Entry compatibility is not end-to-end host certification. Keep adapter implementation and documentation outside scientific module directories; a new host must not copy modules, rewrite packaged templates, change quality gates, or cause prior scientific execution evidence to be reissued.

Run `tools/audit_adapter_boundaries.py` and regenerate `reports/adapter-boundary-audit.json` after adapter changes. `access: codex_native` remains a Codex-owned native handoff; another host may complete that node only through a separately validated equivalent. Validate adapters independently from scientific maturity, and keep installation identity, adapter compatibility and scientific evidence identity separate.

The architecture and module contract are documented in [architecture](architecture.md); shared data requirements are documented in [format contracts](format-contracts.md).
