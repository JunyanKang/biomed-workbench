# Sequencing Intake, Readiness, And Workflow Interoperability

[English](sequencing-intake-and-interoperability.md) · [中文](sequencing-intake-and-interoperability.zh-CN.md) · [Capability map](README.md)

These capabilities connect FASTQ, BAM/CRAM, VCF, single-cell matrices, sample sheets and reference resources to downstream analysis, and bring completed outputs from an external sequencing workflow back into the project. They answer three separate questions: what the inputs are, whether execution can start, and whether returned results can be trusted and reloaded.

## Input inspection

`sequencing-input-intake` reads file identity and lightweight structure, recognises FASTQ, BAM/CRAM, variant files, single-cell matrices, tables and common reference files, and checks duplicate or missing paths, paired-read completeness and unique sample identities. It proposes a next analysis direction from the declared assay, but does not infer library chemistry, strandedness, study groups or biological quality from filenames.

## Pre-execution readiness

`sequencing-execution-readiness` checks two conditions separately:

- whether the declared analysis programs already exist;
- whether the genome, annotation, index, blacklist, known-sites, taxonomy database or barcode-whitelist resources exist and are nonempty.

A readiness pass means only that launch prerequisites are present. Exact version compatibility, workflow completion and scientific interpretability remain properties of the selected analysis module and its observed output. This step neither installs software nor rebuilds an existing environment.

## Receiving external workflow results

`sequencing-run-package-ingest` reads an external `manifest.json` and `artifact_index.json`. A package proceeds to assay-specific and scientific review only when its status is explicitly complete, outputs exist inside the run directory, declared checksums match and the analysis-environment identity is recorded. A plan, prepared or blocked state, failed run or empty output directory is never accepted as completed analysis.

This interface can receive a standard run package from another specialist sequencing workflow while preserving Biomed Workbench's input, environment, result and claim boundaries. Raw-read QC, alignment, quantification, variant calling, peak calling, microbiome processing and single-cell count generation still require the relevant execution workflow; package intake is not a substitute for those computations.

## Example requests

> Check whether these FASTQs, sample sheet and reference genome are sufficient to start bulk RNA-seq. Tell me what is missing before reusing the existing environment and running the appropriate workflow.

> Read this external sequencing run directory, determine whether it truly completed, verify its outputs and recorded environment, and only then continue to result QC and biological interpretation.
