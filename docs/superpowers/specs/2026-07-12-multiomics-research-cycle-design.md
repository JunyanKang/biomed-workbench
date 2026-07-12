# Multiomics Research Cycle Design

## Purpose

Biomed Workbench will treat single-cell multiomics as a research programme, not
as a collection of unrelated analysis commands. One Codex-facing capability,
`multiomics-research-cycle`, will maintain the scientific question, sample
design, hypotheses, analysis graph, evidence, quality decisions, revisions,
figures, manuscript claims, and delivery state across repeated invocations.

The first complete workflow supports:

- paired single-cell RNA and ATAC measurements from the same cells;
- unpaired RNA and ATAC measurements linked at the biological-sample level;
- RNA-only or ATAC-only projects through an explicit degraded mode;
- multiple conditions, time points, batches, donors, and biological replicates;
- resumable work from raw inputs, partially processed objects, or result tables.

## Product Boundary

The plugin owns scientific planning, tool selection, analysis contracts,
quality control, evidence interpretation, iteration, and publication delivery.
It does not own CPU allocation, GPU allocation, local model hosting,
containers, Slurm, or remote-compute infrastructure. Codex may use scientific
software already available in the user's environment, but infrastructure
provisioning is outside the workflow.

The workflow must never:

- treat cells as independent biological replicates;
- infer causality from association without a declared causal design;
- overwrite raw matrices or prior project states;
- continue after a fatal sample-design or data-integrity failure;
- promote a result to a manuscript claim without linked evidence and limits;
- hide a failed hypothesis by silently changing its wording.

## Source Assimilation Basis

The focused design audit read 214 source files relevant to this workflow,
totalling 1,361,851 bytes. It extracted 408 code symbols and 2,491 document
headings. The combined semantic-ledger digest is
`91118fc877944ef39f25b00ebaeb6b56a735fd4a966645a6e3ec1e460bf6b90a`.

The design assimilates four complementary classes of lessons:

1. Cell annotation must combine markers, references, automated predictions,
   hierarchical labels, biological context, and explicit uncertainty.
2. RNA, ATAC, latent integration, trajectory, and regulatory-network tools need
   modality-specific input assumptions and retained raw data.
3. Public atlas, marker, archive, motif, and regulatory databases strengthen
   interpretation but do not replace dataset-level evidence.
4. Publication work must preserve a claim-evidence ledger through figures,
   writing, review, revision, and final delivery.

The source collections are individually stronger than the current workbench in
local analysis breadth, but none provides the complete stateful research loop
defined here. This project rewrites the combined concepts behind stable,
source-neutral contracts.

## Architecture

The implementation is a focused package rather than another large omics file:

```text
biomed_workbench/omics_project/
  __init__.py
  models.py          immutable project, hypothesis, action, evidence, and decision contracts
  intake.py          data inventory and experimental-design validation
  hypotheses.py      hypothesis generation, revision, and adjudication
  planner.py         dependency graph construction and next-action selection
  quality.py         modality and stage quality gates
  interpretation.py cross-modal evidence chains and alternative explanations
  manuscript.py      claim, figure, section, review, and revision state
  state.py           canonical serialization, digesting, and append-only transitions
  api.py             one public advance_research_cycle entrypoint
```

Scientific computation remains in focused capability modules. The project
package coordinates those capabilities and records their results; it does not
reimplement established algorithms.

## Unified Public Entry

The only new user-facing capability is `multiomics-research-cycle`.

`advance_research_cycle(request: dict) -> dict` accepts one closed request:

- `objective`: the biological question in explicit language;
- `project`: species, tissue, perturbations, time points, conditions, and aims;
- `samples`: sample IDs, donor or organism IDs, condition, batch, replicate,
  modality, pairing group, and file references;
- `state`: an optional prior canonical state returned by the capability;
- `results`: newly completed action results with metrics and artifact records;
- `command`: `initialize`, `advance`, `reassess`, or `prepare_delivery`.

The result contains:

- canonical `state` and `state_digest`;
- `decision`: proceed, revise, add-evidence, block, deliver, or complete;
- ordered `next_actions`, including serial and parallel groups;
- unresolved quality findings and their scientific consequences;
- hypothesis status changes with cited evidence IDs;
- manuscript-readiness and delivery-readiness assessments;
- a user-facing explanation that names why the next action was selected.

The state is returned rather than hidden in process memory. Codex can save it
inside the user's analysis project, making every transition recoverable and
portable without binding the plugin to a machine-specific path.

## Project State

Every state has these top-level records:

- `project`: immutable study identity and declared biological scope;
- `design`: samples, experimental units, contrasts, covariates, pairing, and
  known confounders;
- `data_inventory`: modality, format, processing level, genome build, feature
  identifiers, count preservation, and checksums when available;
- `hypotheses`: primary, secondary, and alternative hypotheses;
- `actions`: dependency-linked scientific actions and their execution status;
- `evidence`: normalized observations, statistics, database records, and
  limitations linked to hypotheses and claims;
- `quality_findings`: severity, stage, affected scope, evidence, and remedy;
- `decisions`: append-only transition history with rationale;
- `claims`: candidate manuscript claims and their evidence sufficiency;
- `figures`: panel-level question, data, analysis, statistic, and claim links;
- `manuscript`: section readiness, review findings, and revision history;
- `delivery`: reproducibility manifest and final package checks.

State mutation is append-only at the decision and evidence layers. Superseded
hypotheses and actions remain visible with links to their replacements.

## Hypothesis Contract

Each hypothesis declares:

- a stable ID and falsifiable statement;
- biological scope, comparison, and expected direction;
- required modalities and biological replication;
- predicted observations;
- disconfirming observations;
- alternative explanations;
- required analyses and orthogonal validations;
- current status: `proposed`, `active`, `supported`, `weakened`, `refuted`, or
  `inconclusive`;
- supporting, conflicting, and missing evidence IDs;
- revision lineage.

An observational association may support a descriptive or mechanistic-candidate
hypothesis. It cannot independently support a causal claim.

## Analysis Graph

The planner creates a dependency DAG with these stage families:

1. **Frame**: objective, literature baseline, prior knowledge, and alternative
   mechanisms.
2. **Audit design**: experimental units, biological replicates, pairing,
   covariates, confounding, power limitations, and admissible contrasts.
3. **Audit data**: format, raw counts, metadata alignment, genome build,
   feature identifiers, barcode overlap, and modality pairing.
4. **RNA preprocessing**: ambient RNA, doublets, cell and gene QC,
   normalization representation, batch diagnostics, embeddings, and clusters.
5. **ATAC preprocessing**: fragment integrity, TSS enrichment, nucleosome
   signal, FRiP, doublets, peaks, accessibility matrix, latent representation,
   and clusters.
6. **Integration**: paired or unpaired integration, neighborhood mixing,
   biological conservation, modality agreement, and sensitivity analyses.
7. **Annotation**: broad lineage, subtype, state, marker evidence, reference
   transfer, accessibility support, conflicts, and confidence.
8. **Sample-aware inference**: cell composition, pseudobulk expression,
   pseudobulk accessibility, interaction terms, repeated measures, covariates,
   effect sizes, uncertainty, and multiplicity control.
9. **Mechanism**: trajectory alternatives, differential dynamics, motifs,
   footprint limitations, peak-gene links, TF-target networks, regulon activity,
   and cross-modal concordance.
10. **Adjudicate**: support, weaken, refute, or retain uncertainty for every
    hypothesis and alternative explanation.
11. **Iterate**: revise thresholds, annotations, contrasts, confounder handling,
    or mechanism analyses only through an explicit decision record.
12. **Publish**: claim-evidence matrix, figures, methods, results, discussion,
    limitations, data/code availability, and supplementary audit.
13. **Review**: independent reviewer perspectives, cross-review synthesis,
    response matrix, revision, and repeated claim audit.
14. **Deliver**: state, manifests, tables, figures, manuscript, review ledger,
    software versions, and unresolved limitations.

RNA and ATAC preprocessing run in parallel after shared design and inventory
gates. Integration waits for both modalities when both are required. Evidence
discovery can run in parallel with preprocessing but must be reconciled before
hypothesis adjudication. Publication begins only after claim-level evidence
gates pass.

## Tool Selection

Actions describe scientific intent, required inputs, expected outputs, and
quality gates before naming a tool. Codex then selects an available established
implementation appropriate to the data:

- annotated matrices and basic RNA analysis: AnnData and Scanpy or equivalent;
- paired multiome integration: a paired-data method preserving modality links;
- unpaired integration: a method that exposes alignment uncertainty;
- ATAC processing: established fragment, peak, latent-semantic, and motif tools;
- sample-aware inference: pseudobulk statistical models with biological sample
  as the experimental unit;
- regulatory inference: motif-supported and cross-modal networks, with
  stability checks across seeds or resamples;
- trajectories: at least one topology sensitivity or alternative-root check.

Tool availability may change execution details but never relaxes the scientific
contract. If no valid implementation is available, the action is blocked with
an installation-neutral explanation; the plugin does not provision compute.

## Quality and Self-Correction

Findings have `info`, `warning`, `major`, or `fatal` severity.

- `fatal`: corrupt inputs, irreconcilable metadata, missing experimental units,
  or an impossible requested contrast. The affected branch stops.
- `major`: likely invalid inference, such as pseudoreplication, unmodelled
  complete confounding, severe modality mismatch, or unsupported annotation.
  The planner creates a remediation action before interpretation.
- `warning`: interpretation remains possible with a named limitation and
  sensitivity analysis.
- `info`: retained provenance or descriptive context.

Revisions must identify the failed gate, affected hypotheses, replacement
actions, and whether prior results are invalidated or merely supplemented.
Threshold changes after viewing group labels are marked as outcome-informed and
require a sensitivity analysis. Conflicting RNA and ATAC results trigger checks
for timing, power, peak-gene assignment, cell-state mixtures, and annotation
before a biological contradiction is claimed.

## Cross-Modal Evidence Chains

Mechanistic candidate claims require a linked chain such as:

`condition -> TF motif accessibility -> TF activity -> peak-gene link -> target
expression -> cell-state or phenotype`

Every edge records its method, effect, uncertainty, sample scope, and known
alternative explanations. Missing edges remain visible. A complete chain is
stronger than one isolated association but is still not automatically causal.

## Manuscript and Review Loop

Each candidate claim must link to:

- one or more result records;
- a figure or table location;
- the biological-sample denominator;
- effect size and uncertainty;
- the analysis and sensitivity checks;
- conflicting evidence and limitations;
- the permitted language strength.

Results sections follow the evidence DAG rather than analysis chronology.
Review generates separate technical, significance, and presentation findings
from the same fact base. Revisions update claims and figures first, then prose,
and rerun the claim-evidence audit before delivery.

## Error Handling

Input contract violations fail before a state transition. Scientific failures
produce structured findings and a recoverable state. Unexpected capability
errors expose the failed action ID and safe error class without secrets or
machine paths. Completed upstream actions are never discarded when a later
branch fails.

## Verification Strategy

The workflow requires four evidence levels:

1. Unit tests for contracts, DAG ordering, hypothesis transitions, quality
   gates, state digests, and manuscript readiness.
2. Contract tests proving every action result is schema-valid and replayable.
3. End-to-end synthetic paired and unpaired RNA/ATAC projects that include a
   supported hypothesis, a refuted hypothesis, a confounded contrast, a failed
   QC branch, plan revision, and final manuscript package.
4. Release tests proving one public entry, no source paths, no infrastructure
   ownership, complete capability coverage, and deterministic state replay.

The synthetic cases test orchestration and scientific decisions with compact
matrices and summaries. Established external engines receive separate adapter
contract tests and are not replaced by toy implementations.

## Acceptance Criteria

The feature is complete only when:

- one request initializes a valid paired or unpaired project;
- the returned DAG contains every required analysis and publication stage;
- RNA and ATAC branches run in parallel where dependencies permit;
- sample-level design gates prevent pseudoreplicated inference;
- new results cause deterministic hypothesis and plan transitions;
- conflicting evidence creates corrective actions rather than a forced claim;
- a refuted hypothesis remains in the audit lineage;
- publication cannot proceed with unsupported claims;
- review findings generate linked revision actions and can be reassessed;
- the final package is reproducible from canonical state and manifests;
- all tests and Codex plugin release validators pass.
