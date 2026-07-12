# Production Scientific Tool Expansion Plan

**Goal:** Expand the stateful research engine from bounded inline functions to production scientific tools while preserving exact tool, dependency, format, provenance, and replay guarantees.

**Boundary:** This work manages scientific artifacts, scientific-tool compatibility, analysis execution, and result validation. It does not provision CPUs, GPUs, containers, Slurm, remote compute, or local models.

## Guiding Order

Production bioinformatics tools must not be added as path-taking wrappers around the state kernel. The work proceeds from durable artifacts to exact execution contracts, then representative end-to-end tool families, then breadth expansion. Every public module remains source-neutral and independently discoverable.

### Task 1: Project-owned large-artifact store

- [x] Define immutable payload references containing only role, project-relative object key, media type, byte size, and SHA-256.
- [x] Import regular files by streaming copy into a content-addressed project store.
- [x] Reject symlinks, traversal, absolute serialized paths, non-regular files, digest drift, and size drift.
- [x] Bind payload descriptors into scientific-artifact identity without changing existing inline-artifact digests.
- [x] Add unit tests for import, deduplication, replay, tampering, traversal, and source-path exclusion.

### Task 2: Scientific command execution contract

- [ ] Add declarative argument templates, input/output payload bindings, working-directory policy, timeout, output-size, and mutation scope.
- [ ] Resolve only verified project payloads into runtime paths after compatibility approval.
- [ ] Capture exact executable and dependency versions, selected compatibility row, normalized parameters, input digests, output digests, and safe errors.
- [ ] Reject shell interpolation, undeclared files, undeclared environment variables, unknown versions, unexpected outputs, and output-schema drift.

### Task 3: Structured version-change evidence

- [ ] Replace prose-only version differences with typed parameter, API, field, default, behavior, and format transition records.
- [ ] Add typed dependency probes for Python, R, Java, system executables, services, and databases.
- [ ] Require official version/specification sources, verification date, exact tested versions, allowed rules backed by regression fixtures, conflicts, and platform constraints.
- [ ] Make module upgrades fail release validation without version-specific regression and end-to-end evidence.

### Task 4: Foundational omics artifact and format contracts

- [ ] Add FASTQ, FASTA, SAM/BAM/CRAM, VCF/BCF, BED, GTF/GFF3, count-matrix, H5AD, Loom, MTX, fragment, bigWig, and tabular contracts.
- [ ] Validate compression, companion indexes, sorting, coordinate convention, reference assembly, annotation release, identifier namespace, orientation, sample manifest, and processing level.
- [ ] Add format-pair fixtures covering accepted and rejected version combinations.

### Task 5: Production sequencing quality modules

- [ ] Implement read-level QC and aggregate QC modules using established tools with exact tested versions.
- [ ] Validate real bounded fixtures, output structures, tool reports, sample identity, contamination indicators, and downstream readiness.
- [ ] Provide declared alternatives where a validated tool is absent or incompatible; never infer compatibility.

### Task 6: Production bulk, single-cell, epigenomic, and variant modules

- [ ] Implement modular raw-data QC, alignment/quantification, matrix QC, normalization, differential testing, annotation, enrichment, and report validation.
- [ ] Implement single-cell RNA, chromatin, and multimodal modules without encoding one fixed project pipeline.
- [ ] Implement interval/peak, germline, somatic, and annotation modules with exact coordinate, build, index, and reference checks.
- [ ] Keep every engine replaceable through manifest alternatives and complements.

### Task 7: Database, molecular, imaging, clinical, wet-lab, and publication breadth

- [ ] Convert remaining audited capability families into service, analysis, validation, design, or delivery modules.
- [ ] Prefer official public APIs and established scientific engines; limit user credentials to APIs that materially improve supported research.
- [ ] Integrate local Nature Skills as scientific workflow and quality contracts behind the one assistant entry, not as slash-command bridges.

### Task 8: Source-union reconciliation

- [ ] Reconcile every non-generated audited source file to implemented, superseded, guidance, excluded, sensitive, or provenance-only status.
- [ ] Link every implemented family to module, tests, compatibility rows, and representative evidence without publishing source paths or copied source text.
- [ ] Recalculate breadth and superiority verdicts from evidence; do not claim source-union superiority while unresolved or missing families remain.

### Task 9: Full acceptance and release

- [ ] Run multi-domain real-data cases including single-cell multi-omics, bulk omics, variants and clinical evidence, molecular design, imaging, literature-to-experiment, and manuscript-to-review revision.
- [ ] Verify isolated plugin installation, installed-cache execution, one-entry routing, state replay, new-conversation loading, and extension-module auto-discovery.
- [ ] Publish path-free audit, coverage, version/dependency, format, E2E, independence, limitation, and release reports before GitHub release.
