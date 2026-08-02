# Professional Capability Map

Languages: [English](README.md) · [中文](README.zh-CN.md) · Root: [中文](../../README.md) · [English](../../README.en.md)

Biomed Workbench is organized around scientific decisions, not a menu of unrelated tools. A user supplies a research question and available data; the workbench combines the modules needed to move from framing and evidence gathering to analysis, challenge, revision, and delivery.

## Capability Areas

| Area | Primary scientific role | Detailed guide |
| --- | --- | --- |
| Evidence and literature | Establish what is known, disputed, missing, and current | [Read guide](evidence-and-literature.md); [PDF evidence extraction](pdf-evidence-extraction.md); [HPO terminology](hpo-term-evidence.md); [GO terminology](quickgo-term-evidence.md); [Ensembl gene identity](ensembl-gene-evidence.md); [Open Targets target-disease evidence](opentargets-target-disease-evidence.md); [Reactome pathway identity](reactome-pathway-evidence.md); [Reactome overrepresentation context](reactome-overrepresentation-evidence.md); [gene-set library catalog](gene-set-library-catalog.md); [gene-set membership](gene-set-library-membership.md); [ARCHS4 expression context](archs4-expression-evidence.md) |
| Bulk measurements | Analyse pooled RNA, chromatin, protein-binding, translation, nascent-transcription and genome-organization assays without confusing assay, target, control or normalization strategy | [Bulk sequencing assays](bulk-sequencing-assays.md); [bulk chromatin peak calling](bulk-chromatin-peak-calling.md); [known motif enrichment](sequence-motif-enrichment.md); [chromatin contact evidence](cool-contact-evidence.md) |
| Single-cell measurements | Preserve cell-level structure while controlling sample design, integration, annotation, trajectories, multi-omics and cross-species transfer | [Single-cell and universal analysis guide](omics-and-single-cell.md); [integration, reference mapping and cross-species contract](single-cell-integration-reference-cross-species.md) |
| Spatial measurements | Link molecular state to physical coordinates, tissue images, reference mapping, domains, communication, multislice alignment and three-dimensional organization | [Trajectory and spatial complete-analysis contract](trajectory-spatial-complete-analysis.md); [spatial deconvolution and projection methods](spatial-deconvolution-projection-methods.md) |
| Universal analysis and project methods | Apply format validation, design checks, statistics, enrichment, networks, figure standards and scientific review across compatible scales | [Analysis guide](omics-and-single-cell.md); [GWAS fine-mapping](gwas-susie-fine-mapping.md); [genomic prediction](rrblup-genomic-prediction.md); [demographic simulation](msprime-demographic-simulation.md) |
| Molecular and structural biology | Connect sequence, interaction-network, chemical, docking and structural evidence to testable molecular hypotheses | [Read guide](molecular-and-structural.md); STRING PPI; HADDOCK3/DockQ/PRODIGY; AlphaFold 3; MSBio2/Metascape/Cytoscape; [GenBank CDS extraction](genbank-coding-sequence-extraction.md); [one-site ITC binding](itc-single-site-binding.md); [UniProtKB protein evidence](uniprot-protein-evidence.md); [protein disorder tendency evidence](protein-disorder-evidence.md); [UniProt-to-Ensembl mapping](uniprot-to-ensembl-evidence.md) |
| Imaging and visualization | Quantify images and create faithful scientific communication assets | [Read guide](imaging-and-visualization.md) |
| Clinical and experimental research | Connect cohorts, assays, and experimental measurements to interpretable decisions | [Read guide](clinical-and-experimental.md); [declared-period cosinor rhythm](fixed-period-cosinor.md); [reviewed Western blot densitometry](western-blot-densitometry.md); [radiotracer biodistribution](radiotracer-biodistribution.md); [xenograft tumor growth](xenograft-tumor-growth.md); [accelerated stability](accelerated-stability.md) |
| Publication and translation | Match projects to journals and convert the evidence trail into standards-aware manuscripts, responses, patents, and research packages | [Read guide](publication-and-translation.md); [versioned journal standards](../journal-standards.md) |

## Orchestration Model

Every project is represented as a dependency-aware research graph. Independent evidence sources can be explored in parallel; analyses that consume another module's artifact are ordered serially; mixed programs combine both patterns. The workbench records hypotheses, evidence, artifacts, decisions, quality checks, and revisions so an agent can continue a project without losing the scientific rationale.

Routing is dynamic. A literature question may require one database module, while a translational omics project may combine study-design checks, multiple analysis branches, mechanistic evidence, figure production, manuscript drafting, and adversarial review. The user invokes the same `biomed-workbench` skill in both cases.

For v1.0, broad horizontal requests are compiled into staged programs rather than flat module lists:

- evidence and database programs separate identifier resolution, source retrieval, derived evidence, freshness review, and citation or claim audit;
- publication programs move from figure and manuscript structure through citation, claim, reviewer, response, patent, and presentation checks;
- molecular programs move from sequence inspection through design, verification, structural assessment, docking, and chemical filtering;
- statistics and clinical programs move from cohort or data profiling through inferential models and boundary audits;
- bulk, single-cell, and spatial programs first identify research scale, measurement family, assay, biological target, controls, and normalization strategy as separate fields, then move from input quality to assay-specific inference and publication-facing interpretation.

The plan remains non-evidentiary until real project inputs are inspected, execution parameters are bound without source editing, outputs are reloaded, and module quality gates admit the observed artifacts.

## Scientific Quality Boundaries

The workbench is designed to refuse false confidence. It distinguishes:

- data availability from data adequacy;
- technical replicates from independent biological samples;
- association from causal evidence;
- database retrieval from biological interpretation;
- prediction confidence from experimental validation;
- citation presence from claim support;
- a completed computation from a scientifically acceptable result.

When a required input, compatible backend, quality threshold, or evidence link is missing, the affected claim remains unresolved. A failed quality gate can revise the hypothesis and plan instead of being hidden in a final report. For an execution failure, the controller can automatically continue only with a module's explicitly declared alternative that has an identical artifact contract; broader changes to study strategy remain explicit research decisions.

## Current Scope

The registry currently contains **198** independently discoverable modules. Exact execution and public-data acceptance status is versioned in the release evidence rather than inferred from module registration. The bulk layer includes RNA-seq; ChIP-seq, CUT&RUN and CUT&Tag; R-loop mapping by DRIP-seq, DRIPc-seq, sDRIP/ssDRIP-seq, qDRIP-seq, R-ChIP, MapR and sensor-declared CUT&Tag; RIP-seq, eCLIP, iCLIP, HITS-CLIP, PAR-CLIP and LACE-seq; Ribo-seq with explicit multi-caller ORF evaluation; GRO-seq, PRO-seq, TT-seq and NET-seq; ATAC-seq and DNase-seq; WGBS, RRBS and EM-seq; Hi-C, Micro-C, Capture-C, HiChIP, PLAC-seq and ChIA-PET; and MeRIP-seq/m6A-seq. Each public-data case defines the exact accepted backend, version, study design, and artifact scope.

CUT&Tag is registered as the assay. S9.6 is a target or antibody identity, an exogenous internal reference is a normalization option, and RNase H treatment is specificity evidence. These fields are never promoted to peer assay classes.

Single-cell and spatial modules retain their platform and method-specific contracts, while universal modules provide cross-scale design, statistics, enrichment, network analysis, evidence review, visualization and publication support. Publication support includes a versioned 54-journal standards catalog and an executable project-fit and compliance module.

Named third-party methods are admitted only through explicit compatibility and runtime checks. Routing and executable contracts do not become observed biological evidence until the required backend runs on real inputs and the declared output checks succeed. See [reproducibility and compatibility](../reproducibility.md) for the evidence model.

## Extending The Workbench

A new method is added as an independent scientific module with declared inputs, outputs, compatibility policy, quality gates, and at least one substantive code template when the capability performs bioinformatics analysis. The central registry discovers valid modules automatically, so adding a method does not require creating another user-facing skill. See [architecture and module extension](../architecture.md).
