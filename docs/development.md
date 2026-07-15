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
python3 tools/run_tool.py sequence-inspect --input '{"sequence":"ATGCGC","alphabet":"dna"}'
```

These interfaces are for development, validation, and agent integration. End users should invoke the unified `biomed-workbench` skill with a scientific request rather than call internal scripts.

## Key Directories

- `skills/biomed-workbench/`: the single user-facing Codex skill.
- `biomed_workbench/modules/builtin/`: independently discoverable scientific modules.
- `biomed_workbench/capabilities/`: source-neutral scientific implementations.
- `biomed_workbench/kernel/`: project context, artifacts, hypotheses, evidence, decisions, and replay state.
- `biomed_workbench/orchestration/`: planning, compatibility-gated execution, quality checks, interpretation, and revision control.
- `biomed_workbench/formats/`: shared format profiles and pre-execution metadata validation.
- `biomed_workbench/services/`: bounded public scientific database clients and credential policy.
- `tools/`: registry, routing, execution, scaffolding, validation, reconciliation, and installation verification.
- `tests/`: unit, contract, integration, release, and end-to-end checks.
- `reports/`: release-safe generated evidence and verification summaries.

## Adding A Scientific Module

Create an independent module with a stable ID, scientific description, input and output contracts, compatibility policy, quality gates, and representative tests. Bioinformatics analysis modules must include at least one substantive Python or R template with real parameterization, validation, serialization, failure handling, version provenance, and scientific quality checks.

```bash
python3 tools/create_module.py --help
python3 tools/scaffold_bioinformatics_templates.py --check
```

The generated registry is source-neutral and dynamically discovers valid modules. Do not add a new user-facing skill for each method, encode module names in the routing algorithm, vendor a source project, or introduce a path bridge to external code.

## Source Reconciliation

Source-study ledgers are private development evidence and are never runtime dependencies. Reconcile them into the release-safe summary before publication:

```bash
python3 tools/reconcile_sources.py --manifest .source-audit/manifest.jsonl --design-ledger .source-audit/rewrite-ledger.jsonl --capability-bindings .source-audit/capability-bindings.jsonl --private-output .source-audit/reconciliation-ledger.jsonl --public-output reports/source-reconciliation-summary.json
```

Every source record must resolve to implemented, superseded, guidance, excluded, provenance, or a visible pending capability decision. Reading a source file is not accepted as implementation evidence.

## Release Discipline

- Regenerate deterministic registry and report artifacts before release.
- Keep plugin, catalog, and release versions consistent.
- Run compatibility regression and representative execution checks when changing a baseline or widening a policy.
- Run the full test suite, release validator, isolated plugin install verification, and complete-history secret scan.
- Review generated reports for local paths, credentials, temporary files, and bridge artifacts.
- Keep README counts and public claims synchronized with generated evidence.

The architecture and module contract are documented in [architecture](architecture.md); shared data requirements are documented in [format contracts](format-contracts.md).
