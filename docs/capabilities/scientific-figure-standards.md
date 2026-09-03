# Scientific Figure Standards And Delivery

Languages: [English](scientific-figure-standards.md) · [中文](scientific-figure-standards.zh-CN.md)

## Scientific Role

Scientific figures are project-wide support. Bulk, single-cell, spatial, structural, clinical, experimental, and quantitative-imaging work share figure definition, visual hierarchy, source-data traceability, and delivery checks while retaining plots that are scientifically native to each method. This capability is not quantitative image analysis and does not create new measurements from pixels.

## What Must Be Defined Before Rendering

Each figure part first records its upstream result, the conclusion it supports, the strongest allowed conclusion, source data and content fingerprint, experimental unit, biological sample size, statistical test, multiplicity policy, effect size, uncertainty, plot form, caption, story position, and original-research DOI. It then defines:

- final dimensions and the size hierarchy for titles, axes, ticks, labels, annotations, and legends;
- widths and sizes for data lines, error bars, axes, borders, connectors, and markers;
- the variable encoded by each colour, cross-figure consistency, colour-vision accessibility, and grayscale readability;
- legend content, order, size, and placement, including when direct labels communicate more clearly;
- figure labels, statistical annotations, scale bars, orientation marks, and necessary experimental-schematic elements;
- alignment, whitespace, reading order, and visual hierarchy across figure parts;
- delivery requirements for PDF, SVG, PNG, source data, captions, and quality reports.

These decisions are preserved in a versioned figure specification bound to the analysis result, plot-ready data, and renderer identity and version. Every layout cell must contain actual content; empty panels and exact repetitions of source data, plot form, and allowed conclusion are rejected. This prevents both visual drift and unnoticed separation of a figure from its underlying analysis.

For a multi-panel figure, every panel also states its scientific job: discovery, source or context, mechanistic consistency, orthogonal validation, boundary or null result, or integration. Panels are retained for a distinct biological contribution rather than statistical significance alone. A repeated conclusion from the same evidence type is removed even when it is visually attractive, and the figure is not considered a complete story until discovery and integration are connected through explicit upstream relations.

## Method-Native Plots And Shared Standards

Shared standards define common visual and evidentiary requirements; they do not force every analysis into the same chart. Differential analysis retains effect-size and significance views, enrichment retains ranking and gene-set information, WGCNA retains module–trait relationships, single-cell work retains embeddings, composition, markers, and sample-level results, trajectory and velocity retain direction and uncertainty, spatial work retains tissue coordinates and neighbourhoods, structural work retains confidence, interfaces, and three-dimensional views, and quantitative imaging retains source images, masks, trajectories, and scale bars.

A method-native plot must first satisfy that method's diagnostic purpose and then adopt the shared rules for typography, strokes, colour, annotation, layout, and export. A general renderer handles only its declared plot grammar; it does not replace method-native renderers or infer column meanings from names.

## Source Data And Delivery

Scatter, line, precomputed bar, box, violin, heatmap, and volcano panels can be rendered from explicitly registered CSV or TSV data and a closed figure specification. The delivery package contains final-size PDF, editable SVG, 600-dpi PNG, source data for each figure part, the frozen specification, renderer identity, file digests, and a quality report created after reopening the outputs.

A formal project figure must use the active project lock and every upstream result must be `FORMAL`. Controlled renderer acceptance remains explicitly candidate or sensitivity material and cannot become a project result merely because the output files reopen successfully.

Complex method-native plots, microscopy images, three-dimensional structure views, and mechanism schematics are created by their corresponding modules and then enter the same delivery review. Explanatory illustrations and graphical abstracts communicate established research content; they are not experimental observations or quantitative evidence.

## Rendered-Output Review

Automated checks cover file reopening, dimensions and resolution, editable vector text, source-row coverage, label collision, and required elements. When an established panel is redrawn, the reference and candidate renderings are also compared for aspect-ratio drift, occupied-content movement, regional information-density change, retained vector labels and palette changes. The actual final-size output is still reviewed for plot-family preservation, UMAP or spatial geometry, colour meaning, clipping, occlusion, axes and units, uncertainty and sample-size reporting, legend proportion, and whether each panel still supports its declared conclusion.

Figures, captions, Results prose, and original research sources read the same version of the [Scientific Evidence Map](../scientific-evidence-map.md). When source data, analysis, or conclusions change, affected figures are regenerated and reviewed rather than being reconciled only through caption or prose edits.

## Typical Deliverables

An analysis-specific figure inventory, versioned figure specifications, typography and colour rules, source data, method-native plots, arranged PDF/SVG/PNG files, captions, figure-level quality reports, and traceable links between figures and the scientific evidence map.
