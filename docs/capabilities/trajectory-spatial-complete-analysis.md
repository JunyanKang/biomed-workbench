# Trajectory And Spatial Analysis

Languages: [English](trajectory-spatial-complete-analysis.md) · [中文](trajectory-spatial-complete-analysis.zh-CN.md)

## Platform And Method Coverage

The workbench distinguishes a method listed in the capability range, a runnable workflow, and representative data that have actually run and passed review. A command or parameter description alone does not establish validation.

| Capability | Registered implementation | Required evidence before biological use |
|---|---|---|
| Visium / Visium HD | official SpatialData-IO reader; Space Ranger geometry and image provenance | representative vendor bundle, spot/bin accounting, tissue assignment, image-transform reload |
| Stereo-seq | official SpatialData-IO `stereoseq` reader | representative vendor bundle, bin size/unit, matrix and coordinate reconciliation |
| Slide-seq | AnnData import with explicit coordinates | bead-location source, physical unit, and bead/matrix identifier reconciliation |
| Xenium | official SpatialData-IO `xenium` reader | cell/transcript/boundary reconciliation, negative controls, unassigned transcripts and image transforms |
| CosMx | official SpatialData-IO `cosmx` reader | cell/transcript/boundary reconciliation, negative controls, panel detection and image transforms |
| MERFISH / MERSCOPE | official SpatialData-IO `merscope` reader or data import with explicit coordinates | cell, transcript, and boundary reconciliation; blank or negative controls; detection-panel review |
| Image segmentation | existing boundaries, Squidpy watershed or explicit Cellpose | overlay review, boundary validity, morphology and transcript assignment |
| Image registration | SpatialData named transforms/landmarks or VALIS | pre/post overlay, target registration error, round-trip and deformation diagnostics |
| Deconvolution / mapping | cell2location, RCTD, Tangram and SPOTlight as separate native arms | reference signatures, shared genes, uncertainty/residuals, held-out genes, reference subsampling and method discordance |
| Spatial domains | BayesSpace, SpaGCN and STAGATE as separate benchmark arms | at least three seeds, label-blind stability, coherence, fragmentation, runtime and discordant regions |
| Spatial communication | COMMOT with a mandatory physical-distance cutoff; spatial CellChat may be an independent sensitivity arm | zero cross-sample edges, database/version, heteromeric policy, distance sensitivity, global multiplicity and biological-sample support |
| Multislice / 3D | PASTE for broad overlap, PASTE2 for partial overlap; image-based STalign/VALIS when justified | order/spacing provenance, couplings/transforms, overlap/error diagnostics, calibrated xyz and order sensitivity |
| Cross-sample spatial inference | `lme4` model with section nested within biological sample | replication per condition, convergence, nonsingularity, effect uncertainty and multiplicity |

No deconvolution or domain method is automatically selected by agreement with
reviewed anatomical labels.  Method-native outputs remain separate.  A
consensus, when scientifically justified, must be labelled as a derived
sensitivity summary and cannot replace discordance reporting.

## Unified Trajectory And Spatial Figures

The workbench defines final-size typography, strokes, symbols, axes, legends, colours, and export formats and prepares appropriate standard figure sets for:

- trajectory topology;
- velocity;
- fate mapping;
- regulatory velocity;
- platform QC;
- core spatial statistics;
- spatial deconvolution;
- spatial-domain benchmarking;
- distance-constrained communication;
- image/segmentation/registration analysis;
- multislice and 3D analysis.

A figure set is not marked complete when required plot data are missing. A complete set includes individual and combined PDF/SVG files and a 600-dpi LZW TIFF, with the style version and relationship between plot data and output files retained.

## Primary implementation authorities

- SpatialData-IO readers: <https://spatialdata.scverse.org/projects/io/en/stable/api.html>
- 10x Space Ranger: <https://www.10xgenomics.com/support/software/space-ranger/latest>
- 10x Xenium outputs: <https://www.10xgenomics.com/support/software/xenium-ranger/latest/tutorials/outputs/XR-output-overview>
- Squidpy segmentation: <https://squidpy.readthedocs.io/en/stable/api/squidpy.im.segment.html>
- SpatialData transformations: <https://spatialdata.scverse.org/en/latest/api/transformations.html>
- cell2location: <https://www.nature.com/articles/s41587-021-01139-4>
- RCTD: <https://www.nature.com/articles/s41587-021-00830-w>
- Tangram: <https://www.nature.com/articles/s41592-021-01264-7>
- SPOTlight manual: <https://www.bioconductor.org/packages/devel/bioc/manuals/SPOTlight/man/SPOTlight.pdf>
- BayesSpace: <https://www.nature.com/articles/s41587-021-00935-2>
- SpaGCN code: <https://github.com/jianhuupenn/SpaGCN>
- STAGATE: <https://www.nature.com/articles/s41467-022-29439-6>
- spatial-domain benchmark: <https://www.nature.com/articles/s41592-024-02215-8>
- COMMOT: <https://doi.org/10.1038/s41592-022-01728-4>
- VALIS: <https://www.nature.com/articles/s41467-023-40218-9>
- PASTE: <https://www.nature.com/articles/s41592-022-01459-6>
- PASTE2 code: <https://github.com/raphael-group/paste2>
- SPACEL: <https://www.nature.com/articles/s41467-023-43220-3>
- STalign: <https://www.nature.com/articles/s41467-023-43915-7>
- GPSA: <https://www.nature.com/articles/s41592-023-01972-2>
- Nature figure construction guide: <https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/>

## Representative Acceptance

Tangram has completed reference mapping on its full official test data, and RCTD has completed execution and output review on the official Slide-seq example. Coordinate-explicit H5AD import, standard spatial figure sets, and cross-sample hierarchical modelling also have representative execution records. Acceptance of one method does not transfer to another. Exact versions, data scale, and observed results are recorded in [Public-Data Cases](../cases/README.md) and [Release Notes](../releases/README.md).
