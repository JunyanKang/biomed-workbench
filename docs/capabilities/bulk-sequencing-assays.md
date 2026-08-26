# Bulk Sequencing Analysis

Languages: [English](bulk-sequencing-assays.md) · [中文](bulk-sequencing-assays.zh-CN.md)

Bulk, single-cell, and spatial describe the scale of observation. Labels such as transcriptomics and epigenomics describe what is measured and therefore belong at a different level. Biomed Workbench records three aspects separately:

1. **Data scale:** bulk, single-cell, spatial, or a method that applies across scales;
2. **Measurement family and assay:** for example, chromatin accessibility measured by ATAC-seq;
3. **Method role:** assay-specific analysis, a method shared within a measurement family, or a general statistical and research method.

The antibody, target, spike-in or internal reference, RNase H treatment, peak recall, and normalisation strategy are experimental or analytical choices rather than new assay classes. For example:

`bulk → protein- or mark-associated chromatin enrichment → CUT&Tag → S9.6 target/antibody → optional internal-reference normalisation → RNase H specificity evidence`

## Current Bulk Assay Families

| Measurement family | Assays | Main analysis | Important design and interpretation points |
| --- | --- | --- | --- |
| Steady-state transcription and expression | bulk RNA-seq | RNA quantification, expression QC, differential expression, and downstream statistics | Expression is not transcription rate; the replicate unit is the sample |
| RNA processing and isoform usage | Short-read bulk RNA-seq and long-read RNA-seq | [Event-level splicing, exon usage, transcript usage, full-length isoforms, and cross-assay evidence integration](rna-processing-alternative-splicing.md) | rMATS, DEXSeq, DRIMSeq–stageR, and FLAIR test different objects; their conclusions are not interchangeable |
| Protein- or mark-associated chromatin enrichment | ChIP-seq, CUT&RUN, CUT&Tag | Alignment, quality control, peak detection, differential analysis, and annotation | Assay, target or antibody, control, internal reference, and specificity treatment are recorded separately |
| RNA:DNA hybrids and R-loops | DRIP-seq, DRIPc-seq, sDRIP/ssDRIP-seq, qDRIP-seq, R-ChIP, MapR, and sensor-declared CUT&Tag | Assay-specific preprocessing, signal detection, specificity review, and cross-method comparison | R-loop is the measured object, not the assay; sensor, sample treatment, strandedness, internal reference, and RNase H control affect interpretation |
| Chromatin accessibility | ATAC-seq, DNase-seq | Alignment, quality control, accessible regions, and footprinting | Accessibility is not transcription-factor occupancy; footprinting requires enzyme-bias correction |
| RNA–protein association or binding sites | RIP-seq, eCLIP, iCLIP, HITS-CLIP, PAR-CLIP, LACE-seq | Enrichment or binding-region detection, control comparison, and annotation | RIP supports transcript enrichment; UMI, crosslinking, and reverse-transcription-stop models differ among CLIP and LACE assays |
| Translation | Ribo-seq | P-site placement, periodicity, translation efficiency, and ORF detection | P-site placement and triplet periodicity are checked before ORF inference; results from different callers remain separate |
| Nascent transcription | GRO-seq, PRO-seq, TT-seq, NET-seq | Assay-specific preprocessing, quantification, and kinetic interpretation | Strand, run-on design, pulse labelling, or polymerase position determines the signal model |
| Cytosine modification | WGBS, RRBS, EM-seq | Conversion, coverage, methylation quantification, and regional comparison | Conversion efficiency and coverage are prerequisites; conventional bisulfite data generally do not distinguish 5mC from 5hmC |
| Three-dimensional genome organisation | Hi-C, Micro-C, Capture-C, HiChIP, PLAC-seq, ChIA-PET | Contact matrices, quality control, compartments, domains, and interaction analysis | Resolution, background, and anchoring vary by assay; contact frequency is not direct binding |
| RNA modification enrichment | MeRIP-seq, m6A-seq | Enriched-region detection, differential analysis, and functional annotation | Antibody enrichment gives a regional signal, not a single-base site or modification fraction |

Ribo-seq checks P-site placement and triplet periodicity before retaining the outputs of Ribo-TISH, Ribotricer, or other ORF callers separately. Additional tools such as RiboCode can provide sensitivity analyses; their union is not automatically a set of true ORFs.

LACE-seq starts from FASTQ and handles adapters, poly(A), pre-rRNA, strand information, and multimapping according to the experimental design, then uses the matched IgG control to identify binding regions. RIP-seq uses explicitly paired RIP and input or IgG controls and preserves binning, strand policy, multimapping treatment, model choice, and significance settings. Both workflows expose meaningful parameters without requiring users to edit analysis templates.

Disagreement among R-loop assays is expected. DRIP-family methods, R-ChIP, MapR, and CUT&Tag differ in sensor, sample context, sequenced material, resolution, and bias. Shared signal, method-specific signal, and RNase H sensitivity are therefore reported separately and interpreted within the scope of each assay.

Representative acceptance includes nf-core/riboseq, nf-core/nascent, nf-core/clipseq, nf-core/methylseq, nf-core/hic, ENCODE ATAC-seq, RLPipes, exomePeak2, and dedicated TT-seq, NET-seq, RIPSeeker, and LACE-seq workflows. Every project still records the observed software versions, parameters, and inputs and reopens the resulting intervals, matrices, tracks, models, and quality reports. See [Public-Data Cases](../cases/README.md) and [Release Notes](../releases/README.md) for the current acceptance scope.
