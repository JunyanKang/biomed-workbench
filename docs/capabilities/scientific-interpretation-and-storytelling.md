# Scientific Interpretation, Research Story, And Result Decisions

Languages: [English](scientific-interpretation-and-storytelling.md) · [中文](scientific-interpretation-and-storytelling.zh-CN.md)

Biomed Workbench places data analysis within one continuous research path: the scientific question determines the analysis, observed results correct the interpretation, and reviewed evidence determines the next analysis, experiment, or writing task. A method list is not treated as a research plan, and successful computation is not treated as a scientific conclusion.

## From Question To Decision

| Stage | What the workbench handles | What the user sees first |
| --- | --- | --- |
| Understand the question | Research object, experimental unit, comparison, controls, temporal and spatial context, central hypothesis, and competing explanations | The question that presently needs an answer |
| Select analyses | Resolve assay, target, control, normalisation, and biological relation separately; favour one primary analysis and one necessary orthogonal validation | Why each method was chosen and which decision it can change |
| Execute and review | Run with project inputs, reopen results, and examine effect magnitude, uncertainty, sample hierarchy, quality measures, and negative findings | The principal observation and its reliable scope |
| Interpret biology | Separate observation, calculation, inference, and hypothesis; review organism, tissue, stage, disease state, and cellular compartment | What the evidence supports and which alternatives remain |
| Make a research decision | Retain, qualify, rerun, replace, or stop a branch and identify an observation that distinguishes competing explanations | What to do next and why |
| Build figures and prose | Give every panel a scientific role and connect conclusions to plot data, figures, captions, prose, and references | A progressive research story rather than a stack of analyses |

## Minimal Sufficient Analysis

By default, each scientific question receives one primary analysis that answers it directly and one validation with a distinct assumption, data layer, or error structure. Another method must state which current analysis it replaces or which decision information it contributes that the existing pair cannot supply.

Necessary sensitivity analyses remain available. Parameter, algorithm, and alternative-model dependence can be retained, but they are identified as sensitivity results rather than presented as independent evidence.

## How Interpretation Corrects Itself

Each major conclusion first receives a compact observation summary: experimental unit, direction, effect estimate or the reason it cannot be estimated, uncertainty, independent replication, and current status. Review then asks:

- whether the conclusion exceeds the study design or measurement;
- whether technical quality, batch, sample composition, or analytical assumptions support another explanation;
- whether negative, discordant, or missing evidence changes the conclusion;
- whether the evidence is associative, predictive, spatial, mechanistic-candidate, or directly functional;
- which new observation or experiment most strongly distinguishes the leading explanation from an alternative.

When a problem is found, the workbench revises the interpretation, narrows the claim, uses a registered alternative, acquires evidence, or excludes the result. It does not merely append a fault list to the end of the report.

## How Domain Context Enters The Review

A project may register versioned organism, tissue, developmental stage, disease state, cell type, and subcellular compartment context. Knowledge supported by original studies remains separate from observations made in the current project. Established statements can link to their DOI, while project observations link to actual data or figures. Domain context checks biological plausibility and inference boundaries; it does not turn literature consensus into a result of the current project.

## How A Research Story Is Built

Every manuscript panel should have a distinct scientific job: discover the main phenomenon, locate its temporal, spatial, or cellular origin, establish mechanistic consistency, provide orthogonal validation, show a boundary or negative result, or integrate data layers. The workbench checks whether the figure progresses logically, removes panels that merely repeat the same contribution, and retains negative or discordant evidence that genuinely constrains the conclusion.

Once panel roles are set, each panel is connected to its statistical unit, plot data, analysis code, renderer, final PDF/SVG/PNG, caption, allowed claim, and original research. Final reports read these relationships from the same version of the [Scientific Evidence Map](../scientific-evidence-map.md).

## Routine View And Complete Record

The default result page answers five questions: scientific question, main observation, interpretation boundary, current progress, and next decision. Method versions, environment identity, parameters, file digests, and complete provenance remain in the reproducibility record and are expanded only when they affect interpretation, block progress, or are requested.

A concise answer may remain in the conversation. Once the user asks to generate or save a project analysis report, result-interpretation report, or scientific report, the formal reading entry must be HTML. It includes navigation, observations, scientific interpretations, experimental or statistical units, evidence boundaries, next decisions, and working links to data, figures, analysis code, or literature. Markdown may be saved alongside it for search and compatibility, but it cannot be the sole or primary deliverable. Tool-native FastQC or MultiQC quality reports and backend JSON records retain their own declared formats and are not misclassified as project interpretation reports.

Projects can move among exploration, formalisation, and submission preparation. Existing projects can first be scanned without modification, then let the researcher confirm proposed links among figures, source data, scripts, and captions. See [Project Organisation And Working Modes](../project-governance.md) and [Using Biomed Workbench](../using-biomed-workbench.md).
