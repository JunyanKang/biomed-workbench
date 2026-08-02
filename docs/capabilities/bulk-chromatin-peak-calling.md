# Bulk Chromatin Peak Calling

`bulk-chromatin-peak-calling` is separate from the single-cell ATAC workflow. It is for bulk ChIP-seq, CUT&RUN, and CUT&Tag evidence where assay design, treatment/control handling, peak shape, and replicate semantics must be explicit.

The contract separates fields that answer different scientific questions:

- **assay:** ChIP-seq, CUT&RUN, or CUT&Tag;
- **target or antibody:** for example a histone mark, transcription factor, or S9.6;
- **background or specificity control:** matched input, IgG, RNase H-treated material, or another declared control;
- **normalization strategy:** library-size, internal-reference/spike-in, or another justified method.

S9.6, spike-in and RNase H are therefore not peer assay classes. For an S9.6-targeted CUT&Tag study, RNase H-treated material is specificity evidence and an exogenous internal reference is an optional normalization strategy whose suitability must be demonstrated from the experiment.

The bundled Python template validates stable treatment and optional control files, forbids a ChIP-seq run without a matched input/control, detects MACS3, executes a declared narrow or broad peak policy, reloads the peak records and statistical fields, requires summits for narrow peaks, and records digests, command arguments, detected version, and output accounting. No fallback peak set is generated if MACS3 fails.

For CUT&RUN or CUT&Tag, a no-control run is technically possible but must remain explicitly labeled as such. A called peak is assay-specific enrichment evidence, not proof of direct binding, enhancer activity, differential binding, target-gene regulation, or causal function. Replicate-aware reproducibility, differential analysis, [known PWM motif enrichment](sequence-motif-enrichment.md), chromatin interaction evidence, and experimental validation remain separate steps.
