# Single-Cell ATAC Regulatory Analysis

The `single-cell-atac-regulatory` module keeps peak, motif, chromVAR, and
peak-to-gene evidence distinct while preserving fragments and paired source
counts.

## Executable workflow

- Validates every five-column 10x fragment record, fragment multiplicity,
  barcode allow-list, genome build, and coordinate convention.
- Executes MACS3 in explicit FRAG mode and reloads narrowPeak, summit, and
  parameter evidence.
- Matches named motifs against exact supplied peak sequences.
- Builds fixed-seed GC and accessibility-matched chromVAR backgrounds and
  retains matches, backgrounds, deviations, and z scores.
- Executes Signac LinkPeaks on exact paired RNA and ATAC cells with explicit
  gene coordinates, distance, support, background, score, and p-value rules.

## Public evidence

The [10x PBMC1k ATAC case](../cases/pbmc1k-atac-macs3.md) validates real 10x
fragment parsing, filtered-cell accounting, MACS3 execution, peak and summit
reload, and immutable sources. The complete executable fixture separately
validates sequence-backed motifmatchr, chromVAR, and paired-cell LinkPeaks.

## Interpretation boundary

The public source is ATAC-only and therefore is not used to fabricate motif or
paired-RNA evidence. Aggregate peaks are not donor-level differential
accessibility. Motif matches, deviations, and peak-to-gene correlations do not
establish direct TF binding or causal enhancer regulation.
