# GenBank Coding Sequence Extraction

The genbank-coding-sequence-extraction module turns one supplied GenBank
flatfile into a bounded, annotation-linked CDS result. It is intended to
follow a record-retrieval step such as ncbi-fetch, rather than silently
searching or guessing a sequence source.

## What It Returns

- Every CDS with an exact match to the requested gene, locus_tag, or
  protein_id.
- Zero-based half-open feature intervals, strand, coding sequence, codon
  start, and declared NCBI translation table.
- A local retranslation when the extracted coding sequence is in frame.
- The supplied GenBank translation and an explicit agreement or disagreement
  state when it is present.

## Use It For

- Extracting a defined coding sequence from an accession-bound GenBank record.
- Checking that a record's CDS sequence and annotated translation agree before
  primer, variant, construct, or protein-analysis work.
- Preserving the identifier and coordinate contract passed to downstream
  molecular-design modules.

## Boundaries

The module does not search NCBI, resolve aliases, infer an ORF, choose a
transcript isoform, validate an assembly, or establish gene function. A
no-match or translation disagreement is preserved for review rather than
silently repaired.
