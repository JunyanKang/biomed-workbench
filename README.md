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

External scientific engines remain user-managed dependencies; the plugin guides, validates, and invokes them but does not provision Java, Python environments, containers, GPUs, or schedulers. Versions in the table are reproducibility baselines observed in real verification runs, not installation pins. Each module separately declares a conservative compatibility policy and records the user's actual detected versions in execution provenance.

| Module | Tested baseline | Tested dependency baseline | Input | Outputs |
| --- | --- | --- | --- | --- |
| `read-quality-fastqc` | FastQC `0.12.1` | Java `22` | `fastq@sanger-phred33` | FastQC ZIP `0.12.1` and HTML |
| `quality-report-multiqc` | MultiQC `1.35` | Python `3.13.12` plus exact report-runtime lock | FastQC collection `1.0.0` | MultiQC data ZIP `1.35` and HTML |
| `read-quality-fastp` | fastp `1.3.6` | Bioconda macOS-arm64 build `ha1d0559_0` | `fastq@sanger-phred33` | fastp JSON `1.3.6` and HTML |
| `read-contamination-screen` | FastQ Screen `0.16.0` | Bowtie2 `2.5.5` build `h9e91881_0`, Perl `5.32.1` | FASTQ plus versioned reference bundle | mapping summary and HTML |
| `alignment-quality-samtools` | samtools `1.23` | htslib `1.23` | coordinate-sorted `bam@1.6` plus BAI | QC-stratified flagstat JSON |
| `interval-overlap-bedtools` | bedtools `2.31.1` | XZ `5.8.3` runtime | two build-matched `bed@1.0` sets | pairwise query/reference overlaps |
| `dna-align-bwa-mem-single` | BWA `0.7.19-r1273` | Homebrew arm64 bottle `0.7.19` | single-end FASTQ plus BWA reference bundle | portable unsorted SAM |

Tool-use guidance and routing remain available regardless of the installed version. For scientific execution, versions inside the declared compatibility policy may run and are recorded verbatim; provenance also states whether each version is an exact tested baseline. Missing tools, versions outside the policy, known breaking changes, or invalid output structures prevent the result from entering the evidence ledger until the environment is corrected or a validated alternative is selected. The `reports/*-live-verification.json` files preserve the concrete versions used for FastQC, fastp, MultiQC, FastQ Screen, samtools, and bedtools regression evidence.

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
- `biomed_workbench/modules/scientific_command.py`: shell-free, bounded, compatibility-guided execution for payload-backed scientific tools.
- `biomed_workbench/formats/`: shared exact-version omics format profiles and pre-execution metadata validation.
- `biomed_workbench/services/`: bounded public scientific database clients and credential policy.
- `tests/`: unit, contract, end-to-end, and release checks.

The central registry contains no domain definitions. See `docs/architecture.md` for the extension contract, compatibility rules, and release flow.

Changing a tested baseline or widening a compatibility policy requires named regression and end-to-end evidence plus review of known parameter, field, default, and format changes. A compatible runtime version does not masquerade as a tested baseline: both the actual version and baseline-match status are retained.

Foundational FASTQ, FASTA, SAM/BAM/CRAM, VCF/BCF, BED, GTF/GFF3, count-matrix, H5AD, Loom, Matrix Market, fragments, bigWig, and tabular profiles are maintained once in `biomed_workbench/formats/catalog.json`. Modules that declare one of these exact format-version tokens automatically inherit its compression, index, sort, coordinate, reference, annotation, identifier, sample-manifest, orientation, processing-level, metadata, and payload-role gates.

## Sources And License Notes

This workbench is an independent clean-room implementation informed by inspected biomedical research projects and installed research skills. It does not route through those projects or vendor their source trees.

See `NOTICE.md` for attribution and `reports/` for aggregate source-learning evidence.
