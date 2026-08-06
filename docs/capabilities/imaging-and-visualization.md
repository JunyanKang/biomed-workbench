# Imaging And Visualization

Languages: [English](imaging-and-visualization.md) · [中文](imaging-and-visualization.zh-CN.md)

## Scientific Role

- Register equal-shape 2D images by a bounded integer translation with explicit overlap and MSE diagnostics; this is a baseline alignment check, not affine or deformable registration.

This capability area supports quantitative image analysis and faithful scientific communication. Analytical image outputs remain tied to source arrays and declared measurement semantics; communication assets are explicitly separated from evidence-generating analysis.

## Quantitative Imaging

- Profile scientific image arrays and summarize dimensions, channels, and intensity behaviour.
- Segment image components using explicit parameters and return measurable component outputs.
- Measure two-channel colocalization while retaining the assumptions and channel pairing.
- Track declared points across frames and preserve trajectory-level results.
- Convert calibrated trajectories into path length, net displacement, speed, and directionality while retaining track-length exclusions and claim boundaries.

Representative modules include `image-profile`, `image-segment`, `image-colocalization`, `point-tracking`, and `cell-migration-metrics`.

## Scientific Visualization

- Define a scientific figure from claims, panels, data sources, visual encodings, and validation needs.
- Generate or edit bounded scientific illustrations through Codex-native image generation with a machine-readable brief and observed-output check.
- Create provenance-bound interactive protein structure views.
- Remove a deliberately uniform chroma-key background from a static communication asset with format and matte-quality validation.

Representative modules include `figure-specification`, `scientific-illustration-generation`, `structure-interactive-visualization`, and `image-chroma-key-remove`.

## Quality Gates

Rendered communication assets cannot replace primary measurements. Chroma-key output is not accepted as evidence for segmentation, morphology, localization, intensity, or colocalization. Image generation cannot invent scientific observations. Figure specifications must preserve the direction, uncertainty, statistical unit, and source of each plotted claim.

The current registry provides general image analysis and scientific visualization modules; for spatial transcriptomics analysis, see the dedicated omics workflow in `single-cell-spatial-analysis` (documented under [spatial-analysis.md](spatial-analysis.md)). The microscopy-file workflow itself remains scoped: we focus on robust assay-specific evidence pipelines (profiles, masks, co-localization, trajectories, and figures) and do not claim to fully own native microscopy-reader vendor ecosystems.

## Typical Deliverables

Image profiles, masks and component tables, colocalization statistics, point trajectories, molecular viewers, figure specifications, illustration briefs, validated communication assets, and figure-to-claim audit records.
