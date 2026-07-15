# Imaging And Visualization

## Scientific Role

This capability area supports quantitative image analysis and faithful scientific communication. Analytical image outputs remain tied to source arrays and declared measurement semantics; communication assets are explicitly separated from evidence-generating analysis.

## Quantitative Imaging

- Profile scientific image arrays and summarize dimensions, channels, and intensity behaviour.
- Segment image components using explicit parameters and return measurable component outputs.
- Measure two-channel colocalization while retaining the assumptions and channel pairing.
- Track declared points across frames and preserve trajectory-level results.

Representative modules include `image-profile`, `image-segment`, `image-colocalization`, and `point-tracking`.

## Scientific Visualization

- Define a scientific figure from claims, panels, data sources, visual encodings, and validation needs.
- Generate or edit bounded scientific illustrations through Codex-native image generation with a machine-readable brief and observed-output check.
- Create provenance-bound interactive protein structure views.
- Remove a deliberately uniform chroma-key background from a static communication asset with format and matte-quality validation.

Representative modules include `figure-specification`, `scientific-illustration-generation`, `structure-interactive-visualization`, and `image-chroma-key-remove`.

## Quality Gates

Rendered communication assets cannot replace primary measurements. Chroma-key output is not accepted as evidence for segmentation, morphology, localization, intensity, or colocalization. Image generation cannot invent scientific observations. Figure specifications must preserve the direction, uncertainty, statistical unit, and source of each plotted claim.

The current registry provides general image analysis and scientific visualization modules; it does not yet claim a dedicated spatial-transcriptomics analysis stack or complete microscopy-file ecosystem. Those capabilities require dedicated input contracts, templates, and quality evidence before they can be advertised as implemented.

## Typical Deliverables

Image profiles, masks and component tables, colocalization statistics, point trajectories, molecular viewers, figure specifications, illustration briefs, validated communication assets, and figure-to-claim audit records.
