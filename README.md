# Biomed Workbench

Unified local biomedical research workbench for Codex.

This project exposes one Codex skill:

- `biomed-workbench`

Use that single entry for biomedical evidence search, omics, single-cell analysis, molecular design, imaging, clinical translation, experimental planning, manuscript work, citation auditing, peer review, patents, and presentation planning. The workbench decides whether a task needs one analysis, independent parallel analyses, or a dependent scientific pipeline.

The operational catalog is source-neutral. Provenance is kept separately from routing and execution.

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
python3 tools/validate_workbench.py --release
python3 -m unittest discover -s tests -v
python3 tools/route_task.py "single-cell analysis and Nature-style result writing"
python3 tools/search_tools.py --workflow publication reviewer --limit 5
python3 tools/run_tool.py sequence-inspect --input '{"sequence":"ATGCGC","alphabet":"dna"}'
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

Run a registered capability through the validated JSON interface:

```bash
python3 tools/run_tool.py sequence-inspect --input '{"sequence":"ATGCGC","alphabet":"dna"}'
python3 tools/run_tool.py clinical-deidentify --input-file record.json
```

Inspect the input contract with `tools/search_tools.py --id CAPABILITY_ID` before supplying data.

## Scientific Tool Dependencies

External scientific engines remain user-managed dependencies; the plugin validates and invokes them but does not provision Java, Python environments, containers, GPUs, or schedulers. The first production sequencing module has this exact tested combination:

| Module | Tool | Dependency | Input | Outputs |
| --- | --- | --- | --- | --- |
| `read-quality-fastqc` | FastQC `0.12.1` | Java `22` | `fastq@sanger-phred33` | FastQC ZIP `0.12.1` and HTML |

Unknown, missing, or mismatched versions block before invocation. `reports/fastqc-live-verification.json` records the bounded real-fixture execution, normalized scientific summary, report checks, and path-free provenance used by release validation.

## Internal Structure

- `skills/biomed-workbench/`: the only visible Codex skill.
- `tools/route_task.py`: automatic workflow and execution-shape router.
- `tools/search_tools.py`: catalog search and inspection.
- `tools/run_tool.py`: generic runner for direct, bounded tools.
- `tools/validate_workbench.py`: release validation for single-entry skill, catalog consistency, source coverage, and publish-safe paths.
- `reports/compatibility-execution-evidence.json`: path-free regression and end-to-end evidence bound to every supported compatibility row.
- `biomed_workbench/capabilities/`: independently rewritten scientific implementations.
- `biomed_workbench/modules/builtin/`: one versioned scientific contract per independently discoverable module.
- `biomed_workbench/kernel/`: immutable project context, content-addressed artifacts, hypotheses, evidence, decisions, DAG state, and replay.
- `biomed_workbench/orchestration/`: manifest-derived graph planning, compatibility-gated execution, quality checks, interpretation, and revision control.
- `biomed_workbench/modules/scientific_command.py`: shell-free, bounded, version-gated execution for payload-backed scientific tools.
- `biomed_workbench/formats/`: shared exact-version omics format profiles and pre-execution metadata validation.
- `biomed_workbench/services/`: bounded public scientific database clients and credential policy.
- `tests/`: unit, contract, end-to-end, and release checks.

The central registry contains no domain definitions. See `docs/architecture.md` for the extension contract, compatibility rules, and release flow.

Changing a supported tool, dependency, or format version requires a new validated compatibility row with named regression and end-to-end evidence. Module and release validation fail when either binding is missing or its captured execution did not pass.

Foundational FASTQ, FASTA, SAM/BAM/CRAM, VCF/BCF, BED, GTF/GFF3, count-matrix, H5AD, Loom, Matrix Market, fragments, bigWig, and tabular profiles are maintained once in `biomed_workbench/formats/catalog.json`. Modules that declare one of these exact format-version tokens automatically inherit its compression, index, sort, coordinate, reference, annotation, identifier, sample-manifest, orientation, processing-level, metadata, and payload-role gates.

## Sources And License Notes

This workbench is an independent clean-room implementation informed by inspected biomedical research projects and installed research skills. It does not route through those projects or vendor their source trees.

See `NOTICE.md` for attribution and `reports/` for aggregate source-learning evidence.
