# Public UCSC Coordinate Liftover Case

The acceptance case uses the public hg19-to-hg38 UCSC chain header and its
first mapping block. A source interval inside that block maps to hg38; a source
interval outside the retained block is written to CrossMap's unmapped sidecar.
The case establishes record accounting and chain provenance handling only.

The full chain release is documented at
`https://hgdownload.soe.ucsc.edu/goldenPath/hg19/liftOver/hg19ToHg38.over.chain.gz`.
The compact fixture is intentionally limited to the public header and one
mapping block, so it is a deterministic regression input rather than a genome-
wide conversion resource.
