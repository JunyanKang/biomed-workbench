# Public Life-Science Evidence Discovery And Synthesis

[English](public-research-evidence.md) · [中文](public-research-evidence.zh-CN.md) · [Capability map](README.md)

The workbench accesses public databases through a declared scientific question. The new common entry covers GWAS Catalog, ChEMBL, PRIDE, BioStudies, ENCODE, Human Protein Atlas and MGnify, complementing the existing NCBI, Ensembl, UniProt, Open Targets, gnomAD, cBioPortal, Reactome, QuickGO, PubChem, RCSB PDB and AlphaFold DB capabilities.

Only registered source operations are available. GWAS Catalog can discover studies by trait or associations by mapped gene; ChEMBL can find compounds or retrieve activity records for a compound; PRIDE, BioStudies, ENCODE and MGnify support dataset discovery; and Human Protein Atlas supplies human expression context. Callers cannot provide an arbitrary host or API path.

Each result retains the database, query operation, returned records, truncation state, official interface documentation and scientific evidence role. `public-evidence-synthesis` then checks entity consistency and keeps genetic association, expression context, perturbation, structure, pharmacology and mechanistic evidence distinct rather than reducing heterogeneous records to one apparently precise score.

Public records primarily support candidate discovery, context checks, dataset selection and complementary evidence. Before formal interpretation, review species, genome release, cohort and study design, chemical identity, database version, original publication or data files, and the relationship to project observations. A query that returns no record usually establishes only that no evidence was returned under that query; it does not establish biological absence.
