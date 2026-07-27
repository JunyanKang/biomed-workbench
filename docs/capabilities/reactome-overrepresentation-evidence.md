# Reactome Overrepresentation Context

`reactome-overrepresentation-evidence` submits a declared identifier set to
the official Reactome Analysis Service and retains its returned mapping and
pathway statistics as bounded reference context.

## What it returns

- The complete submitted identifier set and its size.
- Reactome's reported count of unmapped identifiers.
- FDR-ordered pathway records with stable IDs, names, species, matched and
  pathway identifier counts, p-values, FDR, and disease flags when supplied.
- Explicit truncation when the requested output cap is reached.
- The returned analysis token and transport provenance.

## Use it for

- Rapid, source-preserved context around a small, explicitly defined gene or
  protein identifier list.
- Checking whether Reactome's own identifier mapping loses a material part of
  the input before interpreting a pathway label.
- Connecting reviewed pathway records to follow-up literature, GO terminology,
  or a separately designed project-level enrichment workflow.

## It does not do

- Define a project-specific background, ranked test, contrast, or experimental
  unit.
- Replace donor-aware differential analysis, multiplicity planning, or local
  enrichment with a declared universe.
- Establish pathway activity, a mechanism, disease relevance, or causality.

The service controls identifier mapping and its effective reference universe.
Treat the result as exploratory external context and retain the mapping-loss
count, token, and retrieval provenance alongside every downstream claim.
