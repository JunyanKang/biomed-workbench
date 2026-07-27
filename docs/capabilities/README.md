# Professional Capability Map

Languages: [English](README.md) · [中文](README.zh-CN.md) · Root: [中文](../../README.md) · [English](../../README.en.md)

Biomed Workbench is organized around scientific decisions, not a menu of unrelated tools. A user supplies a research question and available data; the workbench combines the modules needed to move from framing and evidence gathering to analysis, challenge, revision, and delivery.

## Capability Areas

| Area | Primary scientific role | Detailed guide |
| --- | --- | --- |
| Evidence and literature | Establish what is known, disputed, missing, and current | [Read guide](evidence-and-literature.md); [PDF evidence extraction](pdf-evidence-extraction.md); [HPO terminology](hpo-term-evidence.md); [GO terminology](quickgo-term-evidence.md); [Ensembl gene identity](ensembl-gene-evidence.md); [Open Targets target-disease evidence](opentargets-target-disease-evidence.md); [Reactome pathway identity](reactome-pathway-evidence.md); [Reactome overrepresentation context](reactome-overrepresentation-evidence.md); [gene-set library catalog](gene-set-library-catalog.md); [gene-set membership](gene-set-library-membership.md); [ARCHS4 expression context](archs4-expression-evidence.md) |
| Omics and single-cell | Turn sequencing and molecular measurements into validated biological conclusions | [Read guide](omics-and-single-cell.md); [bulk chromatin peak calling](bulk-chromatin-peak-calling.md); [known motif enrichment](sequence-motif-enrichment.md); [chromatin contact evidence](cool-contact-evidence.md); [GWAS fine-mapping](gwas-susie-fine-mapping.md); [genomic prediction](rrblup-genomic-prediction.md); [demographic simulation](msprime-demographic-simulation.md) |
| Molecular and structural biology | Connect sequence, chemical, and structural evidence to testable molecular hypotheses | [Read guide](molecular-and-structural.md); [GenBank CDS extraction](genbank-coding-sequence-extraction.md); [one-site ITC binding](itc-single-site-binding.md); [UniProtKB protein evidence](uniprot-protein-evidence.md); [protein disorder tendency evidence](protein-disorder-evidence.md); [UniProt-to-Ensembl mapping](uniprot-to-ensembl-evidence.md) |
| Imaging and visualization | Quantify images and create faithful scientific communication assets | [Read guide](imaging-and-visualization.md) |
| Clinical and experimental research | Connect cohorts, assays, and experimental measurements to interpretable decisions | [Read guide](clinical-and-experimental.md); [declared-period cosinor rhythm](fixed-period-cosinor.md); [reviewed Western blot densitometry](western-blot-densitometry.md); [radiotracer biodistribution](radiotracer-biodistribution.md); [xenograft tumor growth](xenograft-tumor-growth.md); [accelerated stability](accelerated-stability.md) |
| Publication and translation | Convert the evidence trail into reviewable manuscripts, responses, patents, and research packages | [Read guide](publication-and-translation.md) |

## Orchestration Model

Every project is represented as a dependency-aware research graph. Independent evidence sources can be explored in parallel; analyses that consume another module's artifact are ordered serially; mixed programs combine both patterns. The workbench records hypotheses, evidence, artifacts, decisions, quality checks, and revisions so an agent can continue a project without losing the scientific rationale.

Routing is dynamic. A literature question may require one database module, while a translational omics project may combine study-design checks, multiple analysis branches, mechanistic evidence, figure production, manuscript drafting, and adversarial review. The user invokes the same `biomed-workbench` skill in both cases.

For v1.0, broad horizontal requests are compiled into staged programs rather than flat module lists:

- evidence and database programs separate identifier resolution, source retrieval, derived evidence, freshness review, and citation or claim audit;
- publication programs move from figure and manuscript structure through citation, claim, reviewer, response, patent, and presentation checks;
- molecular programs move from sequence inspection through design, verification, structural assessment, docking, and chemical filtering;
- statistics and clinical programs move from cohort or data profiling through inferential models and boundary audits;
- omics programs move from read and matrix quality through alignment, variant or interval handling, expression and chromatin analysis, synthesis, and publication-facing interpretation.

The plan remains non-evidentiary until real project inputs are inspected, templates are adapted in the project workspace, outputs are reloaded, and module quality gates admit the observed artifacts.

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

The registry currently contains 174 independently discoverable modules. Modules cover literature and public databases, page-addressable PDF evidence extraction, HPO and GO terminology, Ensembl assembly-aware gene identity, source-resolved Open Targets target-disease evidence, Reactome pathway identity and bounded overrepresentation context, UniProtKB protein identity and bounded UniProt-to-Ensembl reconciliation, ARCHS4 public expression context, ClinVar, dbSNP reference identity, gnomAD GRCh38 gene constraint, cBioPortal cancer-genomics study, bounded gene-mutation, copy-number evidence and cohort coverage audit, gene-set library discovery and membership retrieval, bulk chromatin peak calling, known sequence-motif enrichment, bounded chromatin contact evidence, GWAS fine-mapping, grouped genomic prediction, declared demographic simulation, explicitly scored pairwise sequence alignment, descriptive sequence-difference localization, GenBank CDS extraction, ORF discovery, explicit PCR primer-pair selection, exact-match amplicon simulation and finite reference-panel specificity screening, linear Sanger-verification coverage plans, supplied RNA secondary-structure summaries, aligned protein conservation, circular-dichroism thermal transition summaries, declared-period cosinor rhythm fitting, one-trace electrophysiology summaries, reviewed Western blot densitometry, radiotracer biodistribution, xenograft tumor growth, accelerated stability, bounded 2D image translation registration, publication planning workflow (`presentation-delivery-plan`), omics, single-cell analysis, molecular design, structural biology, imaging, clinical analysis, wet-lab calculations, scientific quality control, and publication workflows.

The workbench does not claim that every named third-party method is installed in every user environment. It provides routing, contracts, templates, compatibility guidance, and quality criteria; consequential execution is accepted only when the required backend and output checks succeed. See [reproducibility and compatibility](../reproducibility.md) for the evidence model.

## Extending The Workbench

A new method is added as an independent scientific module with declared inputs, outputs, compatibility policy, quality gates, and at least one substantive code template when the capability performs bioinformatics analysis. The central registry discovers valid modules automatically, so adding a method does not require creating another user-facing skill. See [architecture and module extension](../architecture.md).
