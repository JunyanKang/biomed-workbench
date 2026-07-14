# Biomed Workbench

Unified local biomedical research workbench for Codex.

This project exposes one Codex skill:

- `biomed-workbench`

Use that single entry for biomedical evidence search, omics, single-cell analysis, molecular design, imaging, clinical translation, experimental planning, manuscript work, citation auditing, peer review, patents, and presentation planning. The workbench decides whether a task needs one analysis, independent parallel analyses, or a dependent scientific pipeline.

The current registry contains 89 dynamically discovered modules and 90 fully evidenced compatibility rows. The release suite discovers 568 tests; these counts are observations of this revision, not monotonic quality targets.

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
python3 tools/reconcile_sources.py --manifest .source-audit/manifest.jsonl --design-ledger .source-audit/rewrite-ledger.jsonl --capability-bindings .source-audit/capability-bindings.jsonl --private-output .source-audit/reconciliation-ledger.jsonl --public-output reports/source-reconciliation-summary.json
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
| `alignment-sort-index-samtools` | samtools `1.23` | htslib `1.23` | unsorted `sam@1.6` | coordinate-sorted `bam@1.6` plus CSI |
| `variant-region-query-tabix` | tabix `1.23` | htslib `1.23` | coordinate-sorted `vcf@4.5` BGZF plus TBI | header-preserving regional `vcf@4.5` |
| `variant-filter-vcf` | Python `3.14.3` | Python standard library `3.14.3` | one-sample or sites-only biallelic `vcf@4.5` | filtered `vcf@4.5` plus exclusion audit |
| `variant-decompress-bgzip` | bgzip `1.23` | htslib `1.23` | coordinate-sorted `vcf@4.5` BGZF plus TBI | byte-preserved uncompressed `vcf@4.5` |
| `tumor-mutation-burden-vcf` | Python `3.14.3` | Python standard library `3.14.3` | filtered ANN `vcf@4.5` plus build-matched callable `bed@1.0` | auditable nonsynonymous mutations per callable union Mb |
| `metagene-factorization-nmf` | Python `3.14.3` | NumPy `2.4.4`, SciPy `1.17.1`, scikit-learn `1.8.0` | normalized nonnegative `count-matrix@1.0.0` plus ordered feature/sample manifests | stable rank-selected metagene loadings, sample exposures, and independently reconstructed quality report |
| `single-cell-communication` | LIANA `1.7.3`, CellPhoneDB `5.0.1`, CellChat `2.2.0`, NicheNet `2.2.1.1` | Python `3.10.20`, Scanpy `1.11.5`, AnnData `0.11.4`, R package runtimes | count-backed H5AD or Matrix Market plus cell type, biological sample, condition, species, and versioned resources | method-native and standardized sample interactions, replicate support, ligand activities, links, and validation report |
| `citation-record-resolution` | Crossref REST v1 and Europe PMC REST contracts observed `2026-07-13` | Python `3.14.3` standard-library HTTPS client | one DOI | source-preserved Crossref and Europe PMC records plus explicit agreement fields |
| `preprint-evidence` | bioRxiv details API contract observed `2026-07-13` | Python `3.14.3` standard-library HTTPS client | bioRxiv or medRxiv DOI and server | ordered, uncollapsed version history and separately reported publication DOIs |
| `chemical-evidence` | PubChem PUG REST contract observed `2026-07-13` | Python `3.14.3` standard-library HTTPS client | declared name, CID, or InChIKey namespace | all matched CIDs, SMILES/connectivity, InChIKey, formula, charge, synonyms, and ambiguity checks |
| `clinical-trial-evidence` | ClinicalTrials.gov API v2 contract observed `2026-07-13` | Python `3.14.3` standard-library HTTPS client | free query, closed declarative filters, or bounded Essie expression | count-verified, deterministically ordered cohort with complete bounded pageToken traversal, truncation state, design/results context, and per-request provenance |
| `structure-evidence` | RCSB PDB Data REST v1 contract observed `2026-07-13` | Python `3.14.3` standard-library HTTPS client | one to 25 explicit PDB IDs | identifier-preserved entry method, resolution, release, citation, entity, and deposition context |
| `structure-search` | RCSB PDB Search API v2 contract observed `2026-07-13` | Python `3.14.3` bounded JSON POST client | text, organism, taxonomy, UniProt, method, resolution, ligand, and model-scope filters | unique PDB IDs with reconciled total count, page provenance, explicit truncation, and first-page HTTP 204 preserved as a zero-result set |
| `structure-polymer-entities` | RCSB PDB Data REST v1 contract observed `2026-07-13` | Python `3.14.3` standard-library HTTPS client | PDB ID plus optional bounded entity IDs and sequence inclusion | entity identity, source organism, UniProt links, sequence length, mutation count, optional canonical sequence, and explicit missing entities |
| `structure-ligands` | RCSB PDB Data REST v1 contract observed `2026-07-13` | Python `3.14.3` standard-library HTTPS client | PDB ID and ligand cap | entry-to-nonpolymer-to-chemical-component links with formula, charge, InChIKey, stereochemical SMILES, truncation, and explicit missing records |
| `image-chroma-key-remove` | Python `3.14.3` | Pillow `10.4.0` | one static untagged-sRGB PNG `3.0`, JPEG `T.81`, or WebP `riff-container-2025` communication asset | canonical RGBA PNG plus independently recomputed matte-quality report |

Tool-use guidance and routing remain available regardless of the installed version. For scientific execution, versions inside the declared compatibility policy may run and are recorded verbatim; provenance also states whether each version is an exact tested baseline. Missing tools, versions outside the policy, known breaking changes, or invalid output structures prevent the result from entering the evidence ledger until the environment is corrected or a validated alternative is selected. The `reports/*-live-verification.json` files preserve the concrete versions used for FastQC, fastp, MultiQC, FastQ Screen, samtools, bedtools, VCF processing, TMB, and NMF regression evidence.

The public evidence clients require no new credentials. They use HTTPS host allow-listing, bounded request and response sizes, retries only for transient failures, closed request schemas, identifier preservation, source-specific parsers, and explicit truncation or disagreement states. `clinical-trial-evidence` 1.1 translates condition, intervention, status, phase, study type, enrollment, dates, sponsor, investigator, eligibility, age, sex, and same-site location constraints into API v2 server-side parameters; it walks opaque page tokens to the declared cap and refuses an exhaustive-cohort claim when `records_truncated` is true. RCSB Search and Data API contracts remain separate: search reconciles unique entry IDs and totals across POST pages, while entity and ligand modules retain deposited identity and missing-record state without inferring biological relevance. See `reports/public-database-live-verification.json` for eight live database checks and independent package-case execution.

## Bioinformatics Code Templates

Every built-in `omics` or `molecular_design` analysis, validation, transform, or design module packages at least one substantive Python or R template for Codex to inspect and adapt. The current release covers 38/38 bioinformatics modules with 42 templates. A template must expose real parameterization, input validation, output serialization, failure handling, version provenance, and scientific quality checks; placeholders, dependency installation, infrastructure management, unsafe shell execution, local paths, and unbound blocking quality gates fail release validation.

Deterministic modules declare `code_templates`; Agent-generated workflows reference templates through `agent_protocol.template_sections`. Both routes use module-local source, exact manifest references, the shared compatibility and artifact contracts, and observed output checks. `tools/create_module.py` automatically scaffolds and validates a template when a future bioinformatics module is created, while `tools/scaffold_bioinformatics_templates.py --check` detects drift. See `reports/bioinformatics-template-coverage.json` for the complete inventory.

`single-cell-communication` is the first multi-backend template module under this contract. Its live fixture contains 160 cells from four independent samples and two conditions. LIANA and CellPhoneDB produce sample-stratified interactions and cross-sample support; CellChat runs each biological sample separately; NicheNet requires donor-aware receiver differential expression and project-pinned network resources. The verified run executes all four backends and is recorded in `reports/single-cell-communication-live-verification.json`. Cells are never treated as condition-level replicates.

`scientific-illustration-generation` uses a separate `codex_native` contract. It validates a non-evidentiary scientific illustration brief and returns a machine-readable handoff to Codex `image_gen`; the unified Skill invokes the native tool and checks the observed bitmap. It never asks the user for a provider image API key, runs a provider SDK/CLI, or claims that a handoff alone created an image. See `reports/codex-native-handoff-verification.json` for the exact covered and retired source behaviors.

`image-chroma-key-remove` is the local deterministic follow-up for a deliberately uniform key background. It rejects format-signature mismatches, animation, oversized rasters, unsupported modes, embedded ICC profiles, noncanonical orientation, and heterogeneous automatic key samples; then emits a lossless RGBA PNG and a digest-bound report that independently recomputes alpha classes and residual edge spill. Its output is a communication asset only and cannot replace primary image data or support segmentation, intensity, morphology, localization, or colocalization claims. See `reports/chroma-key-live-verification.json`.

`source-freshness-audit` performs deterministic, offline review-window governance for reporting guidelines, database snapshots, protocols, and other versioned research sources. It requires an explicit as-of date, upstream URL and version, intended use, review interval, currentness requirement, and due policy; rejects future-dated snapshots; and blocks or warns on due records exactly as declared. A young snapshot is only inside its review window: the module always reports `upstream_drift_assessed: false` and never treats snapshot age as proof that the upstream source is unchanged or current.

`citation-resolution-adjudication` keeps resolver evidence honest: a match wins, an identifier-keyed miss is separated from a title-only coverage gap, and outages or skipped resolvers remain unresolved. None of these states alone proves claim support or nonexistence. `classification-gold-set-evaluation` then evaluates any closed-label scientific classifier with a digest-bound gold-set version, confusion matrix, explicit aggregate and per-class metrics, minimum-support gates, independent-annotation and leakage gates, advisory expert concordance, and polarity-aware baseline regression checks. It names per-class recall as recall rather than the ambiguous "per-class accuracy", blocks empty declared classes, treats dropped metrics as regressions, and does not misclassify improvement from a zero baseline as regression.

`assertion-citation-coverage-audit` separates external assertions requiring inventory-backed citations from current-study results requiring analysis or experiment artifact provenance. It rejects unresolved IDs, treats raw citation markers as intent rather than proof of coverage, preserves manifest-bound findings, and blocks a false clean result when sentence segmentation or citation extraction is incomplete. `claim-evidence-integrity-audit` then adjudicates the direction and eligibility of reviewed literature, experiment, clinical, omics, imaging, and statistical evidence while preserving refutation, negative constraints, audit failure, independence, and causal-design limits.

`manuscript-revision-base` and `manuscript-revision-lineage` form a dynamically discovered serial revision chain. The first scans the complete block set before assigning IDs above the global maximum and mechanically emits full exact-content SHA-256 digests. The second turns reviewer-driven revision into a verifiable transformation instead of a prose-only promise: it validates the entire patch before applying anything, preserves untouched blocks exactly, issues fresh deterministic block IDs, detects exact moves, and records parent-child lineage. A revision is refused when structural changes lack acknowledgment, comment extraction is incomplete, the audit is not independent, a claimed analysis/experiment/figure/citation lacks evidence, response locations do not resolve, placeholders remain, or conflicting reviewers lack an editor-priority decision.

`temporal-integrity-audit` evaluates explicit source, event, version, and causal bindings using precision-aware calendar intervals and non-path provenance records. It distinguishes publication date from effective range, refuses arithmetic over low-confidence dates, checks reciprocal acyclic supersession chains, handles leap years, treats overlapping causal intervals as unresolved, and calls an absent comparator phantom only for an explicitly exhaustive version catalog. The router exposes a compact `selected_module_ids` set: independent modules are parallel, producer-consumer artifact contracts are serial, and no module name is encoded in the selection algorithm.

## Internal Structure

- `skills/biomed-workbench/`: the only visible Codex skill.
- `tools/route_task.py`: automatic workflow and execution-shape router.
- `tools/search_tools.py`: catalog search and inspection.
- `tools/run_tool.py`: generic runner for direct, bounded tools.
- `tools/validate_workbench.py`: release validation for single-entry skill, catalog consistency, source coverage, and publish-safe paths.
- `tools/reconcile_sources.py`: development-only one-to-one reconciliation of ignored source/design ledgers into a path-free release receipt root.
- `tools/refine_source_design_ledger.py`: deterministic product-boundary policy that retires compute-infrastructure responsibilities without touching scientific pending records.
- `tools/apply_source_capability_bindings.py`: generic private-rule binder; source paths remain ignored while the public report exposes only rule and receipt counts.
- `reports/compatibility-execution-evidence.json`: path-free regression and end-to-end evidence bound to every supported compatibility row.
- `reports/bioinformatics-template-coverage.json`: complete bioinformatics module-to-template coverage and source-quality results.
- `reports/single-cell-communication-live-verification.json`: four-backend LIANA, CellPhoneDB, CellChat, and NicheNet execution evidence.
- `reports/public-database-live-verification.json`: live Crossref, Europe PMC, bioRxiv, PubChem, ClinicalTrials.gov v2, and RCSB PDB evidence plus isolated module-package validation.
- `reports/chroma-key-live-verification.json`: real command-boundary execution, synthetic edge fixture, output digests, alpha-class checks, and non-quantitative-use evidence for chroma keying.
- `reports/source-reconciliation-summary.json`: public counts, pending capability decisions, current module/project-contract evidence binding, and an irreversible digest over all private per-file receipts.
- `reports/plugin-contract-verification.json`: path-free official Codex plugin and Skill validation bound to the current manifest, single Skill entry, generated registry, and isolated snapshot.
- `reports/local-update-verification.json`: digest-bound proof that local cachebuster updates replace one SemVer build suffix atomically and never enter the scientific runtime.
- `reports/ci-quality-verification.json`: current GitHub test, release-validation, deterministic-evidence, and checksum-verified full-history secret-scan contract.
- `biomed_workbench/capabilities/`: independently rewritten scientific implementations.
- `biomed_workbench/modules/builtin/`: one versioned scientific contract per independently discoverable module.
- `biomed_workbench/kernel/`: immutable project context, content-addressed artifacts, hypotheses, evidence, decisions, DAG state, and replay.
- `biomed_workbench/orchestration/`: manifest-derived graph planning, compatibility-gated execution, quality checks, interpretation, and revision control.
- `biomed_workbench/modules/scientific_command.py`: shell-free, bounded, compatibility-guided execution for payload-backed scientific tools.
- `biomed_workbench/project_templates.py`: compatibility-gated execution and atomic result support shared by module-local project templates.
- `biomed_workbench/formats/`: shared exact-version omics format profiles and pre-execution metadata validation.
- `biomed_workbench/services/`: bounded public scientific database clients and credential policy.
- `tests/`: unit, contract, end-to-end, and release checks.

The central registry contains no domain definitions. See `docs/architecture.md` for the extension contract, compatibility rules, and release flow.

Public CI uses the exact repository verification baselines in `requirements-ci.txt`; these versions reproduce release testing but do not pin a user's scientific environment. The workflow rebuilds deterministic registry evidence and rejects any diff, while Gitleaks `8.30.1` is downloaded from its official release, SHA-256 checked, and run over complete Git history with redacted findings.

Changing a tested baseline or widening a compatibility policy requires named regression and end-to-end evidence plus review of known parameter, field, default, and format changes. A compatible runtime version does not masquerade as a tested baseline: both the actual version and baseline-match status are retained.

Foundational FASTQ, FASTA, SAM/BAM/CRAM, VCF/BCF, BED, GTF/GFF3, count-matrix, H5AD, Loom, Matrix Market, fragments, bigWig, tabular, PNG, JPEG, and WebP profiles are maintained once in `biomed_workbench/formats/catalog.json`. Modules that declare one of these exact format-version tokens automatically inherit its compression, index, sort, coordinate, reference, annotation, identifier, sample-manifest, orientation, processing-level, metadata, and payload-role gates.

## Sources And License Notes

This workbench is an independent clean-room implementation informed by inspected biomedical research projects and installed research skills. It does not route through those projects or vendor their source trees.

Every inspected source file has one private content-identified design receipt. The release reconciler rejects missing or duplicate receipts, then classifies each as implemented, superseded, guidance, excluded, provenance, or pending. Executable capability and schema decisions remain pending until a path-free private receipt binding resolves them to current passing module compatibility, regression, and representative execution evidence; therefore reading a source file is never presented as functional implementation.

The current reconciliation accounts for all 89,314 inspected files, with 88,076 resolved and 1,238 still pending specific scientific module or project-contract evidence. Nonzero pending records deliberately prevent a source-union completeness or overall-superiority claim; they are the maintained backlog for deeper capability absorption rather than a hidden bridge to source code.

The ignored `.source-audit/` ledgers are development evidence and are neither runtime inputs nor published path bridges. The repository publishes only source-neutral aggregate reports and a SHA-256 receipt root. See `NOTICE.md` for attribution and `reports/` for the releasable evidence.
