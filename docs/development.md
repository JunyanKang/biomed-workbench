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

Every `agent_generated` workflow additionally requires one `observed_output_contract` per output port. This contract is distinct from the handoff schema and must close the returned content schema, require typed primary and semantic-metadata payloads, enumerate every blocking postflight gate, and freeze both a container reloader and a module-and-port semantic profile. Container reload proves that declared tables, structured text, archives, HDF5, RDS, PDF, image, and structure files are readable. Semantic admission separately binds module/version/port/result-schema identity, the primary payload SHA-256, input and result accounting, limitations, empty-result reasons, and structured quality metrics. The plugin—not the caller—runs each frozen evaluator and compares the observed metric with its typed threshold. Method-specific profiles must also recompute invariants available from the primary payload; functional enrichment, for example, checks separate ORA/GSEA columns, probability ranges, ratios, gene-set sizes, leading edges, and empty-result accounting. The semantic validator source digest is part of the handoff contract identity. `tools/add_observed_output_contracts.py` regenerates deterministic reviewed contracts; a new module must not be released from a mechanically generated skeleton without its scientific profile and adversarial fixtures.

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
