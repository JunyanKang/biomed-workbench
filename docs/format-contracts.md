# File And Data Requirements

Languages: [English](format-contracts.md) · [中文](format-contracts.zh-CN.md)

Biomed Workbench does not infer data content from a filename extension alone. Before analysis, it checks the file format, reference version, and required metadata for the relevant data type.

## Common Checks

- representation and compression;
- required indices and sorting;
- coordinate system, reference sequence, and genome build;
- annotation release and gene or variant identifier system;
- sample information, orientation, processing level, and the file's role in the analysis.

BAM/CRAM, VCF, BED, GTF/GFF3, single-cell fragments, expression matrices, and general tables have different requirements. A general table cannot replace a specialised format with genomic-coordinate meaning.

An expression matrix must identify its feature and observation axes, state whether values are raw counts or processed measurements, name the feature-identifier system, and provide matching feature and sample information.

PNG, JPEG, and WebP are suitable for ordinary static-image exchange. Images used for quantitative analysis also require bit depth, pixel size, colour space, channels, and measurement meaning; a display-processed image alone is insufficient.

## Problems That Stop Analysis

An unknown or unsupported format version, missing required index, coordinate or reference mismatch, incomplete sample information, unclear matrix axes, or an undefined file role is reported before scientific software runs. The workbench does not choose a nearest version or proceed merely because a filename extension matches.

Individual methods may require additional fields or companion files. These are checked against the user's project before the analysis begins.
