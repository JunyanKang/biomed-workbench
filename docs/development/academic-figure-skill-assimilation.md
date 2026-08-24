# academic-figure-skill capability assimilation

Biomed Workbench reviewed every tracked file in `TingxiYu/academic-figure-skill` at commit `1df9940dd01ac939f072b12fe28d6353b79b90f9` before implementing the publication-figure package. The source repository is Apache-2.0 licensed. Its source tree, previews, installation adapters, and example data are not runtime dependencies of the Workbench.

## What was retained

The implementation retains five useful design principles: define the scientific claim before choosing a plot; evaluate typography and strokes at final display size; deliver editable vector and high-resolution raster files together; preserve panel-level plotting data; and review both source logic and the rendered output.

These principles are expressed through the existing versioned visualization standard and a new immutable renderer. They are not copied as editable templates.

## What was replaced

The source workflow depends on copying and modifying plotting scripts, includes hard-coded or simulated examples, and contains checks that may reject scientifically valid negative results because their apparent signal is weak. One A/B evaluation script does not parse, and several repository checks depend on the checkout folder retaining one exact name. The source's 29-of-29 readiness result checks selected syntax and preview presence rather than executing and reloading every implementation.

The Workbench replacement therefore requires explicit column mappings and claims, rejects silent row loss, performs no undeclared statistics, preserves null results, generates new plots only from registered input data, exports exact-size PDF/SVG/PNG files, reloads every container, records source-data and file digests, and requires visual review after automated checks.

## Acceptance comparison

The previous generic `figure-specification` capability produced a structured plotting plan but no rendered artifact. The added `publication-figure-package` capability executes a closed specification against a registered table and produces a deterministic package containing the figure, the exact source data for every panel, the frozen specification, a manifest, and an independent quality report.

The fast controlled comparison contains four panel types, including a differential-result panel with no significant hits. All four panels retain all 12 registered rows, and two independent runs produce the same package digest.

The release acceptance is deliberately more demanding. It uses the public Breast Cancer Wisconsin (Diagnostic) data through scikit-learn, with 569 cases and 30 measured features, to build a six-panel 183 × 170 mm figure. The package contains a 20 × 20 correlation heatmap, two case-level views containing 1,138 plotted points, a 30-feature effect and adjusted-P summary with eight external labels, a two-group trend, and a 20-feature ranked display. The combined plotting table contains 1,228 registered records. Every record is assigned, automated text-box overlap is zero, and the PDF, SVG, 600-dpi PNG, editable vector text, and panel source tables all reopen successfully. The observed comparison is recorded in `reports/publication-figure-complex-acceptance.json`. These checks validate the rendering and delivery slice only and do not promote the fixture to biological or diagnostic evidence.

The complete per-file classification, digest, and disposition is recorded in `reports/source-assimilation-academic-figure-skill.json` and can be rebuilt with `tools/audit_academic_figure_source.py` against the audited source commit.
