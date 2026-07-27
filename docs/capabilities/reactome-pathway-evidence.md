# Reactome Pathway Identity

`reactome-pathway-evidence` retrieves one exact, stable Reactome pathway
record. It anchors a declared pathway identifier to curated reference context;
it does not run pathway activity or enrichment analysis.

## What it returns

- Stable pathway ID and its returned version.
- Display name, species, and release date when available.
- Disease and inferred-pathway flags when supplied by Reactome.
- Linked Gene Ontology biological-process context when present.
- Retrieval provenance or an explicit `found: false` result.

## Use it for

- Checking the identity and species scope of a pathway already named in a
  research question, figure, or analysis plan.
- Preserving the curated pathway version before connecting it to gene-set,
  expression, or literature evidence.
- Linking a stable Reactome concept to its declared GO biological process
  without turning either record into a project-level biological conclusion.

## It does not do

- Free-text pathway search, event expansion, pathway activity scoring, or
  enrichment testing.
- Project-gene membership inference, disease interpretation, mechanism
  validation, or causal inference.

Use a canonical stable ID such as `R-HSA-109581`. A not-found response is a
service outcome, not evidence that a related pathway or biological process is
absent.
