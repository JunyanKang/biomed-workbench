# Database Connector Index

OpenScience database connectors are indexed in `tools/catalog.json` as portable evidence-search patterns. The original TypeScript connector files are not copied because this project is an independent Codex plugin, not an OpenScience application checkout.

Use these entries as connector metadata:

- `kind`: `database_connector`
- `run_policy`: `source_reference`
- `path`: this reference file
- `source_path`: upstream relative connector path

Connector families covered by the catalog include:

- Chemistry: BindingDB, ChEBI, ChEMBL, Guide to Pharmacology, PubChem, SureChEMBL
- Genomics: ClinVar, dbSNP, Ensembl, gnomAD, MyGene, MyVariant, NCBI Gene, UCSC
- Literature: arXiv, bioRxiv, Crossref, Europe PMC, OpenAlex, PubMed, Semantic Scholar
- Omics: ArrayExpress, DepMap, Expression Atlas, GEO, GTEx, Human Protein Atlas, Single Cell Expression Atlas
- Pathways and interactions: BioGRID, IntAct, KEGG, Open Targets, Reactome, STRING, WikiPathways
- Proteins and structures: AlphaFold, InterPro, Pfam, PDBe, RCSB PDB, SIFTS, UniProt

Execution rule:

1. Treat connector entries as evidence-search routes unless a native local connector implementation is added later.
2. Prefer existing Codex life-science tools or direct public APIs for live queries.
3. Keep connector source names as metadata only; do not expose OpenScience paths as the user-facing workflow.
