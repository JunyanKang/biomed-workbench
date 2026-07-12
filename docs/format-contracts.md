# Scientific Format Contracts

Biomed Workbench format profiles separate file-format truth from tool-specific module manifests. External profiles use the exact version named by their governing specification. Formats without a formal universal semantic schema use a project-owned profile instead of pretending that a file extension is sufficient.

## Project-Owned Profiles

### `count-matrix@1.0.0`

A count matrix is accepted only with explicit feature and observation axes, value semantics, identifier namespace, sample-manifest digest, processing level, and orientation. The matrix, feature table, and observation table are separate required payload roles so axis identity can be audited independently of storage representation.

### `tabular@1.0.0`

A scientific table is accepted only with an explicit delimiter, header policy, column schema, missing-value policy, row-order policy, processing level, and sample-manifest digest. Coordinate-bearing tables must use a specialized BED, GTF, GFF3, VCF, fragments, or other coordinate-aware profile rather than this generic profile.

## Static Raster Profiles

`png@3.0`, `jpeg@T.81`, and `webp@riff-container-2025` identify the governing W3C, ITU-T, and WebP container specifications. A raster artifact must also declare its decoded pixel dimensions, color space, frame count, purpose, compression family, top-left raster orientation, processing level, and image payload role. The profile does not infer these properties from a filename extension.

The chroma-key module narrows these broad interchange profiles further to one static 8-bit image, canonical orientation, explicit sRGB handling, bounded dimensions, and a communication-only purpose. Animated PNG/WebP, embedded profiles requiring color management, and quantitative scientific images do not silently enter that narrower compatibility row.

## Validation Rule

Profiles are exact contracts, not extension detectors. Unknown profile versions, incompatible compression, missing companion indexes, undeclared sorting, coordinate mismatches, absent reference digests, missing annotation or identifier metadata, absent sample manifests, and incomplete payload roles block execution before a scientific tool is invoked.
