# 10x PBMC1k ATAC Peak Calling

This public-data case executes barcode-accounted MACS3 peak calling from the
official 10x Genomics PBMC1k ATAC Next GEM v1.1 fragments and filtered peak
matrix.

## Frozen design

1. Both official files are bound to expected SHA-256 digests.
2. Three hundred filtered barcodes are selected by stable hash without peak or
   cell labels.
3. Every source fragment record and multiplicity is parsed and reconciled.
4. MACS3 runs with FRAG input, human genome-size model, q-value 0.01, retained
   duplicate multiplicity, and summit calling.
5. narrowPeak, summits, parameters, versions, counts, and digests are reloaded.

## Observed result

- The filtered matrix contains 1,195 cells.
- The fragments file contains 19,703,972 records and 43,198,848 counted
  fragments across 234,716 observed barcodes.
- The 300 selected cells contribute 3,795,000 records and 8,932,258 fragments.
- Every selected barcode is observed in the fragments file.
- MACS3 returns and reloads 94,726 coordinate-valid peaks and summits.
- All source, accounting, selection, execution, and reload gates pass.

The case does not claim public-data validation of motifmatchr, chromVAR, or
LinkPeaks because the source has no paired RNA or declared motif resource.

Machine-readable evidence:
[`reports/public-case-pbmc1k-atac-macs3.json`](../../reports/public-case-pbmc1k-atac-macs3.json).
