# Open Targets Target-Disease Evidence

`opentargets-target-disease-evidence` retrieves a bounded, source-resolved
Open Targets evidence page for one Ensembl gene and one disease ontology ID.
It preserves the database association context without turning a score into a
mechanistic or clinical conclusion.

## What it returns

- The exact target and disease identifiers, plus disease name when found.
- The service-published total evidence count and an explicit page truncation
  state.
- Returned data source, datatype, score, study ID, and literature IDs.
- Retrieval provenance and the mode of any declared datatype selection.

## Important boundary

The current Open Targets API no longer accepts the historical server-side
datatype filter for this operation. When datatype values are requested, the
workbench filters only the returned bounded page and labels that fact in the
provenance. It never presents that output as an exhaustive datatype-specific
count.

Association evidence and aggregate scores remain integrated reference context.
They do not prove a mechanism, clinical validity, actionability, treatment
response, or causality. Review each contributing source and study design before
using a record in a scientific or translational claim.
