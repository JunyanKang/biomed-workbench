# Multi-Database Live Evidence Case

This acceptance case executes nine registered modules against authoritative
public services and preserves each provider's identifiers, schemas, version
semantics, counts, truncation behavior, and scientific context.

The checked report covers:

- Crossref and Europe PMC citation identity reconciliation;
- bioRxiv preprint version history;
- PubChem compound identity and stereochemistry context;
- ClinicalTrials.gov protocol and results context;
- RCSB PDB entry, search, polymer, and ligand records;
- AlphaFold DB model-version and confidence metadata.

Every check is bound to the current module package, service contract, output
digest, and registry digest. The case confirms live retrieval and schema
handling for the recorded requests. It does not prove that a retrieved record
supports a user's scientific claim; claim support still requires source-content
review and claim-evidence adjudication.

See
[`reports/public-database-live-verification.json`](../../reports/public-database-live-verification.json)
for the machine-readable evidence.
