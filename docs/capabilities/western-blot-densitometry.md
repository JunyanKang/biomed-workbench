# Reviewed Western Blot Densitometry

## Purpose

The western-blot-densitometry module turns reviewed lane and ROI measurements into background-corrected target signal, optional matched loading-control normalization, and fold change relative to declared reference lanes. It retains every lane and the stated technical or biological replicate level.

## Input Boundary

It requires a unique lane identifier, condition, target integrated intensity, background per pixel, and ROI area. Loading-control values are used only when integrated intensity, background, and area are all supplied for that lane. The user must retain the original blot, ROI overlay, exposure and saturation review, antibody identity, sample provenance, and reference-lane rationale.

## Scientific Boundary

The module intentionally does not discover bands, select ROIs, or decide whether a loading control is valid. It reports a descriptive reviewed-ROI normalization, not protein abundance, mechanism, or condition-level significance. Technical lanes remain technical observations rather than biological replicates.

## Execution Contract

The generated Python template is bound to the versioned module contract and preserves request and output provenance. It was verified with Python 3.14.3.
