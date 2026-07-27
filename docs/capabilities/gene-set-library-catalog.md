# Public Gene-Set Library Catalog

`gene-set-library-catalog` reads bounded metadata from Enrichr's public `datasetStatistics` service: library name, category, term count, and gene coverage. It is the resource-selection step before enrichment, not the enrichment calculation itself.

Use it to choose a candidate library, then record its retrieval provenance, species and identifier scope, and the final gene-set membership used by a project. The workbench's local enrichment functions and project workflows must only run after those choices are frozen.

Catalog metadata can change over time and does not prove that a term is enriched, that its genes are appropriate for a project, or that a library's annotation is current.
