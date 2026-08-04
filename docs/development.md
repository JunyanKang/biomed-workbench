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

Every `agent_generated` workflow additionally requires one `observed_output_contract` per output port. This contract is distinct from the handoff schema and must close the returned content schema, require at least one payload role with allowed media types, enumerate every blocking postflight gate, and bind a packaged reload validator. The released validator reloads declared tables, structured text, and archives; checks supported HDF5, RDS, PDF, image, and structure containers or signatures; and reconciles table record counts, workflow versions, and gate evidence with imported payloads. Freeze the contract digest in `ExecutionHandoff`; reject a return when the contract drifted, a required field or payload is absent, a gate is missing, or gate evidence does not match an imported payload. Run `tools/add_observed_output_contracts.py` after a generator adds a new packaged workflow, then scientifically review the generated port formats and gate coverage rather than treating mechanical generation as acceptance.

```bash
python3 tools/create_module.py --help
python3 tools/scaffold_bioinformatics_templates.py --check
```

The generated registry is source-neutral and dynamically discovers valid modules. Routing aliases, exclusions, required context, named-method priority, scientific stage, and reviewed-upstream requirements belong in the manifest. Do not add a new user-facing skill for each method, encode module names in the routing algorithm, maintain a second plan-stage table, vendor a source project, or introduce a path bridge to external code.

## Release Discipline

- Regenerate deterministic registry and report artifacts before release.
- Version scientific implementations, runtime compatibility, module-scoped evidence, and documentation separately. A global registry or documentation change never invalidates scientific outputs by itself; a module metadata change requires reviewed scope reissue; a runtime-policy change requires targeted compatibility retesting; only a scientific implementation, parameter-semantic, input-processing, or output-recognition change requires recomputation.
- Routing and orchestration metadata are discovery-only evidence scope. They change registry discovery and plan compilation, but they cannot reissue or invalidate an unchanged scientific execution receipt.
- External-result admission contracts have a separate handoff digest. Tightening that controller boundary changes installation identity and all future handoffs, while an already observed public computation remains bound to its unchanged execution protocol, templates, method fields, and dependencies.
- A declared fixture and an executed fixture are separate readiness axes. Only an isolated case receipt carrying case and reloaded-output digests may set `controlled_fixture_executed_and_reloaded`.
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
