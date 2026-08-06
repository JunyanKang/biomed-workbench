# Trajectory and spatial analysis capability contract

Languages: [English](trajectory-spatial-complete-analysis.md) · [中文](trajectory-spatial-complete-analysis.zh-CN.md)

## Scope and evidence levels

The workbench separates a registered method, an executable project template,
and an observed end-to-end execution.  A backend is not called validated merely
because its command, parameters, or output schema exists.

| Capability | Registered implementation | Required evidence before biological use |
|---|---|---|
| Visium / Visium HD | official SpatialData-IO reader; Space Ranger geometry and image provenance | representative vendor bundle, spot/bin accounting, tissue assignment, image-transform reload |
| Stereo-seq | official SpatialData-IO `stereoseq` reader | representative vendor bundle, bin size/unit, matrix and coordinate reconciliation |
| Slide-seq | coordinate-explicit AnnData adapter | bead-location provenance, physical unit, bead/matrix identifier reconciliation |
| Xenium | official SpatialData-IO `xenium` reader | cell/transcript/boundary reconciliation, negative controls, unassigned transcripts and image transforms |
| CosMx | official SpatialData-IO `cosmx` reader | cell/transcript/boundary reconciliation, negative controls, panel detection and image transforms |
| MERFISH / MERSCOPE | official SpatialData-IO `merscope` reader or coordinate-explicit adapter | cell/transcript/boundary reconciliation, blank/negative controls and panel detection |
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

## Unified trajectory and spatial figure inventories

`biomed_workbench.visualization` version 1.2.0 defines final-size typography,
strokes, symbols, axes, legends, colors and export rules plus mandatory plot
inventories for:

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

The R renderer refuses complete-profile status when a mandatory plot ID lacks
source data.  It exports individual and combined PDF/SVG and a 600-dpi LZW TIFF,
and records style version, input manifest digest and every output digest.

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

## Current observed execution boundary

On 2026-08-02 Tangram 1.0.4 cluster-mode reference mapping was executed on the
complete official repository test pair: 26,431 reference cells, 18 reference
classes, 9,852 spatial locations, and 249 shared genes. The current template,
RNA-count-based density prior, fixed seed, normalized projection and native
mapping object are checksum-bound and were reloaded before acceptance. The
generic coordinate-explicit H5AD platform path, the complete R spatial
figure package, the missing-panel blocking gate, and a nonsingular cross-sample
hierarchical model were executed and reloaded.  The selected machine runtime
also executed spacexr/RCTD 2.2.1 on its official Slide-seq vignette data. Other
native backends retain their own compatibility and public-data evidence status;
Tangram or RCTD acceptance is not transferred to a different method.
