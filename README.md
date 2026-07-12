# Biomed Workbench

Unified local biomedical research workbench for Codex.

This project exposes one Codex skill:

- `biomed-workbench`

Use that single entry for biomedical evidence search, omics, single-cell analysis, molecular design, imaging, clinical translation, wet-lab protocol work, manuscript writing, reviewer simulation, citation checking, patent conversion, PPT planning, and runtime checks. The workbench routes internally across workflows and decides whether a task should use one tool, multiple independent tools, or a serial pipeline.

Source project names are kept only as metadata in `tools/catalog.json`; they are not the user-facing hierarchy.

## Install From GitHub

Install it as a Codex plugin marketplace:

```bash
codex plugin marketplace add JunyanKang/biomed-workbench --ref main
codex plugin add biomed-workbench@biomed-workbench
codex plugin list
```

If installing from a full Git URL:

```bash
codex plugin marketplace add https://github.com/JunyanKang/biomed-workbench --ref main
codex plugin add biomed-workbench@biomed-workbench
```

After installation, open a new Codex task so the `biomed-workbench` skill is loaded into the available skill list.

## Local Development Install

For local testing before publishing:

```bash
mkdir -p ~/plugins
git clone https://github.com/JunyanKang/biomed-workbench ~/plugins/biomed-workbench
codex plugin marketplace add ~/plugins/biomed-workbench
codex plugin add biomed-workbench@biomed-workbench
codex plugin list
```

## Validate Before Release

Run these checks from the repository root before pushing or tagging a release:

```bash
python3 tools/validate_workbench.py
python3 -m unittest discover -s tests -v
python3 -m py_compile tools/*.py tools/adapters/*.py
python3 tools/route_task.py "single-cell analysis and Nature-style result writing"
python3 tools/search_tools.py --workflow publication reviewer --limit 5
python3 tools/run_tool.py runtime_status
```

Expected validation result:

```text
OK: biomed-workbench validation passed
```

## Route

Run from the project root:

```bash
python3 tools/route_task.py "single-cell analysis and Nature-style result writing"
python3 tools/route_task.py "compare PubMed, UniProt, and PDB evidence for TP53"
python3 tools/route_task.py "design CRISPR guides and draft validation protocol"
```

## Search

Run from the project root:

```bash
python3 tools/search_tools.py "single cell annotation"
python3 tools/search_tools.py --workflow molecular_design crispr
python3 tools/search_tools.py --workflow publication reviewer
python3 tools/search_tools.py --id run_deseq2_analysis
```

## Run

Only entries with `run_policy=direct` are runnable through the generic runner:

```bash
python3 tools/run_tool.py runtime_status
python3 tools/run_tool.py run_deseq2_analysis -- --help
```

Heavy setup scripts, service commands, source-reference connectors, and Biomni functions are indexed but not auto-run.

## Internal Structure

- `skills/biomed-workbench/`: the only visible Codex skill.
- `tools/route_task.py`: automatic workflow and execution-shape router.
- `tools/search_tools.py`: catalog search and inspection.
- `tools/run_tool.py`: generic runner for direct, bounded tools.
- `tools/validate_workbench.py`: release validation for single-entry skill, catalog consistency, source coverage, and publish-safe paths.
- `tools/refresh_catalog_metadata.py`: refreshes script and Nature-workflow descriptions without exposing machine-local paths.
- `scripts/`: reusable local scripts organized by workflow.
- `references/biomni_functions.md`: internal index for Biomni function capabilities.
- `references/database_connectors.md`: internal index for OpenScience connector capabilities.
- `references/runtime_adapters.md`: environment-variable runtime adapter notes.
- `references/internal_workflows/`: detailed implementation notes used by the unified router.

## Local Runtime Configuration

Optional environment variables:

- `CLAUDE_SCIENCE_HOME`
- `CLAUDE_SCIENCE_CLI`
- `CLAUDE_SCIENCE_PYTHON`
- `CLAUDE_SCIENCE_RSCRIPT`
- `BIOMNI_SOURCE_ROOT`
- `OPENSCIENCE_SOURCE_ROOT`

## Sources And License Notes

This workbench integrates portable skills, scripts, workflow patterns, and metadata from Biomni, OpenScience, the local Claude Science runtime, and installed Nature-style Codex skills. Large upstream repositories, credentials, local runtime workspaces, generated artifacts, and third-party scientific datasets are not vendored into this repository.

See `references/source_manifest.json`, `references/source_file_audit.md`, and `NOTICE.md` for source coverage and redistribution notes.

## Maintainer Refresh

To absorb updated metadata from an installed Nature skill suite without adding a local path to the repository:

```bash
python3 tools/refresh_catalog_metadata.py --nature-skills-root "${CODEX_HOME:-$HOME/.codex}/skills"
python3 tools/validate_workbench.py
python3 -m unittest discover -s tests -v
```
