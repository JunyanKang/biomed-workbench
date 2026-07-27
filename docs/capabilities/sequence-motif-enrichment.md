# Known Sequence Motif Enrichment

`sequence-motif-enrichment` tests a declared collection of known DNA PWMs against already extracted foreground and background FASTA sequences. It scans both strands, makes one hit decision per sequence at a frozen normalized PWM score threshold, performs one-sided Fisher exact enrichment, and applies Benjamini-Hochberg correction across the supplied motif collection.

Inputs must declare the same genome build and sequence extraction policy for foreground and background. The module will not silently fetch a genome, generate a background set, or resolve a motif database release. The CLI template accepts a JSON PWM collection with `A`, `C`, `G`, and `T` rows for every motif and emits an immutable, reload-checked evidence report.

An enriched PWM is sequence-level evidence only. It does not show transcription-factor expression, accessibility, occupancy, direct binding, enhancer activity, target-gene regulation, or causality. De novo motif discovery, positional bias analysis, and matched-background construction remain separate workflows.
