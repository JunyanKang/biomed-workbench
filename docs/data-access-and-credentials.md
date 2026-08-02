# Public data access and credentials

Version: `2026.08.02`
Scope: public service endpoints currently implemented and allow-listed by Biomed Workbench.

Credential requirements belong to a service endpoint, not to an entire database brand. A resource may combine anonymous retrieval, signed-in personal features, paid APIs, and private deployments. The workbench therefore documents only the endpoints it actually calls.

## Current status

- No current public-database module requires an API key to reach its implemented endpoint.
- `NCBI_API_KEY` is optional for both NCBI E-utilities and NCBI Datasets. Anonymous access remains available; the key raises official request capacity.
- AlphaFold Server is a browser-authenticated analysis service, not an anonymous database API. It uses interactive Google sign-in and documents no public submission API. The workbench prepares official JSON for user-reviewed manual upload and stores only an access state—never a password, OAuth token, cookie, or browser session.
- Crossref Metadata Plus tokens and private cBioPortal OAuth/tokens are outside the current public clients and are not silently accepted.
- Other implemented clients use anonymous official endpoints and remain subject to service terms, rate limits, schema changes, and data licenses.

The service inventory covers NCBI E-utilities and Datasets, Crossref, Europe PMC, bioRxiv, ClinicalTrials.gov, UniProt, Ensembl, Reactome, Open Targets, gnomAD, public cBioPortal, PubChem, RCSB PDB, AlphaFold DB, QuickGO, Enrichr, ARCHS4, HPO, and IUPred2A.

Notable endpoint rules:

- NCBI documents 3 requests per second without an E-utilities key and 10 with a key; NCBI Datasets documents 5 and 10 respectively.
- Crossref's public REST API does not require authentication; a contact email enables polite-pool identification, while Metadata Plus uses a paid token not used by the current client.
- The public cBioPortal API requires no authentication; private deployments may use OAuth or tokens.
- PubChem PUG REST states that it does not issue API keys or whitelist clients and applies dynamic request throttling.
- AlphaFold Server requires official-page Google sign-in, is restricted to non-commercial use, may retain submitted sequences and outputs for an extended period, and prohibits use of Server outputs with automated ligand/peptide binding or interaction prediction systems.

Official references: [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25497/), [NCBI Datasets API keys](https://www.ncbi.nlm.nih.gov/datasets/docs/v2/api/api-keys/), [Crossref access and authentication](https://crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/), [Europe PMC REST](https://europepmc.org/RestfulWebService), [ClinicalTrials.gov API](https://clinicaltrials.gov/data-api/api), [UniProt programmatic access](https://www.uniprot.org/help/programmatic_access), [Reactome Content Service](https://reactome.org/dev/content-service), [Open Targets GraphQL](https://platform-docs.opentargets.org/data-access/graphql-api), [public cBioPortal API](https://www.cbioportal.org/api/swagger-ui/index.html), [private cBioPortal token authentication](https://docs.cbioportal.org/deployment/authorization-and-authentication/authenticating-users-via-tokens/), [PubChem PUG REST](https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest), [AlphaFold Server](https://alphafoldserver.com/), [Server output terms](https://alphafoldserver.com/output-terms), and [Server privacy notice](https://alphafoldserver.com/privacy).

## Agent-guided configuration

The preferred interface is a natural-language request:

> Check which public databases this project will use and whether any credential is needed. If higher NCBI request capacity is justified, guide me through hidden NCBI API-key entry. Do not ask me to paste the key into chat, project files, or reports; report only whether it is active and where it is sourced.

> Check AlphaFold Server access. If access is unconfigured, authentication failed, the session expired, access was denied, quota is exhausted, or terms remain unreviewed, report that exact state and open the official sign-in page. Never store or repeat my Google password. Prepare the package first; I will review and submit it manually.

An agent should explain why a credential is needed before opening hidden input. Google authentication for AlphaFold Server must occur on the official page; the agent records only an actionable state and check time. Users do not need to write commands.

Supported operating modes are:

1. task-scoped secret or environment injection for clusters and automation;
2. persistent per-user storage outside the project, entered through a hidden prompt;
3. institution-approved secret-manager injection.

Task-scoped injection takes precedence over local storage. Status output reports presence and source, never the value. Rotation, removal, and repository-leak audits can also be requested in natural language.

Credentials must never enter chat text, Git, project JSON, sample sheets, run logs, figures, reports, or scientific evidence maps. Passwords, OAuth tokens, browser cookies, and recovery data must also remain outside interactive-access records. A newly authenticated service requires an allow-list change, bilingual documentation, module declarations, and leak-prevention tests before use.
