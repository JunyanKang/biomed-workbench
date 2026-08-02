# Privacy

Biomed Workbench processes project data in the user-controlled workspace unless the user selects an external database, literature, model-service, or other networked capability. Implemented public clients include NCBI, Europe PMC, Crossref, UniProt, Ensembl, Reactome, Open Targets, public cBioPortal, PubChem, STRING and other services listed in the versioned [data-access inventory](docs/data-access-and-credentials.md).

Each external request is limited to the declared identifiers or query payload required by that capability and is governed by the destination service's terms and privacy policy. Project files, prompts, clinical records and credentials are not sent to the plugin author. Local MSBio2, Cytoscape, HADDOCK3 and approved AlphaFold 3 runtimes operate on user-selected local artifacts; their licenses and any separately chosen external services remain under the user's control.

Credential requirements are endpoint-specific. `NCBI_API_KEY` is optional for the implemented NCBI E-utilities and Datasets endpoints. Credential values are read through the credential service or task-scoped environment, excluded from structured inputs and outputs, and must not be stored in the repository, reports, logs or scientific evidence maps.

Sensitive human data must be de-identified or processed in an appropriately governed environment. Before external access, users and Codex—or an explicitly configured interoperability adapter—must confirm that the requested identifiers and metadata can be transmitted under the applicable consent, institutional policy and law.
