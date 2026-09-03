# Project Locks, Analysis Selection, And Result Status

## Working modes and established projects

Use `EXPLORE` for fast candidate checks and temporary figures; its outputs may be candidate, sensitivity, or deprecated results but cannot enter formal evidence. Use `FORMALIZE` when the experimental unit, method, parameters, source data, authoritative script, and interpretation are ready to be fixed. Use `SUBMISSION` only for the final reproducible package, where formal results, figure contracts, the evidence map, rendered visual review, privacy checks, and clean-room reproduction must agree.

For an established project, `project import-existing` scans the selected directory without changing it. It inventories likely figures, source tables, analysis scripts, renderers, captions, and existing panel registries, then proposes candidate relations with the filename or explicit reference that produced each suggestion. `project confirm-import` requires an explicit decision for every proposed relation. Only confirmed, conflict-free relations can seed a project lock; filename similarity alone never establishes data lineage.

A project may also supply a versioned biological-context profile. It keeps literature-supported knowledge separate from observations made in the current project, links established statements to their original DOI, records tissue, stage and cell-compartment context, and names forbidden inferences, competing explanations and observations that would distinguish them. This profile informs scientific review but does not certify a claim or replace a domain expert.

The ordinary result view shows the biological question, observations, interpretation boundary, current progress, and next decision. Reproducibility details and the complete project record remain available through the explicit reproducibility and audit views.

Languages: [English](project-governance.md) · [中文](project-governance.zh-CN.md)

Biomed Workbench organises long-running projects around scientific questions and decisions. An available method is not automatically added to a project, and a successful process is not automatically eligible for a formal manuscript figure.

## Interpret The Question Before Selecting Methods

The workbench resolves assay, measurement target, controls, normalisation, and the biological relation being tested as separate dimensions. Negation and ambiguous terms remain explicit. For example, a secondary transcriptional effect is a downstream expression consequence rather than RNA secondary structure; in an S9.6 experiment, spike-in supports normalisation but does not replace RNase H specificity evidence.

A complex objective becomes independently reviewable scientific branches followed by one integration decision. Each scientific question receives, by default:

- one primary analysis that directly answers the question;
- one orthogonal validation with a distinct assumption, data layer, or error structure.

A third method enters execution only when it replaces a named analysis or supplies decision information that the approved pair does not provide. This limits repeated method switching and prevents several closely related analyses from being presented as independent support.

## The Project Lock

Before formal analysis, the project freezes the sample sheet, genome and annotation releases, cell annotation, biological replicate unit, analysis-environment identity, thresholds, colour meanings, formal result directory, and manuscript-panel registry. Each file carries a version and content fingerprint. After observed execution, the environment identity stays with the execution receipt; a repeat analysis checks it first and preferentially reuses a compatible recorded environment, avoiding duplicate installation and unnoticed dependency changes.

Changing a locked item creates a new lock revision linked to its parent. Older results are not silently adapted by editing captions, moving folders, or renaming files; affected analyses and figures return to review.

## Four Result States

| Status | Meaning | Eligible for a formal manuscript figure? |
| --- | --- | --- |
| `CANDIDATE` | A result exists but still awaits sufficient review or comparison | No |
| `SENSITIVITY` | A result tests dependence on parameters, assumptions, or methods | No, unless later promoted |
| `FORMAL` | Observed execution, output reload, scientific review, retention decision, and project-lock checks are complete | Yes |
| `DEPRECATED` | The result has been replaced, excluded, or removed from the current claim | No |

Promotion from candidate or sensitivity status is not a label edit. The workbench checks the observed execution and reload chain, method-validation scope, bilingual scientific review, retained-evidence decision, experimental unit, project lock, and figure contract. A formal result still supports only the claims allowed by its design and observed evidence.

## Capability Maturity

The public project view uses four unambiguous levels: `CONTRACT_ONLY`, `EXECUTED_FIXTURE`, `PUBLIC_CASE_VALIDATED`, and `CURRENT_PROJECT_VALIDATED`. A multi-method capability shows the validated method slices separately and does not inherit public-case status from one successful slice. The full definitions and current denominators are given in [Capability maturity](maturity.md).

## Results-First Project View

Routine interaction shows the scientific conclusion, key result, evidence boundary, current status, and next decision. Versions, content fingerprints, execution records, review chains, and full history remain available in the background and are expanded for reproducibility or when a blocking issue needs attention.

Figures, captions, Results prose, and bilingual reports continue to read the same version of the [Scientific Evidence Map](scientific-evidence-map.md). Each version's HTML reports and maps include a table of contents and direct entries to files, figures, and literature, making it possible to move from a conclusion back to its data and sources while keeping project status, figure identities, and narrative sources aligned.

## Building A Research Story From Results

Formal figures are organised around the scientific argument rather than the list of analyses performed. Each panel first receives one role: discovery, temporal, spatial, or cellular context, mechanistic consistency, orthogonal validation, boundary or negative result, or integration across data layers. Adjacent panels must progress logically. A statistically significant or visually attractive result does not enter the main figure when it merely repeats an existing contribution or cannot change the interpretation.

Project-specific biological context also enters the interpretation review. Organism, tissue, developmental stage, disease state, and cellular compartment must agree with the observation; literature knowledge, current-project results, and testable hypotheses remain distinct. When an interpretation is too strong, the workbench revises the prose, narrows the claim, acquires a discriminating analysis or experiment, or excludes the result instead of adding another page of audit findings. See [Scientific Interpretation, Research Story, And Result Decisions](capabilities/scientific-interpretation-and-storytelling.md).
