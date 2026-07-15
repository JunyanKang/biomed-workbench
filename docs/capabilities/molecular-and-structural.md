# Molecular And Structural Biology

## Scientific Role

This capability area connects sequence, chemical, and structural observations to testable molecular hypotheses. It keeps design calculations, database evidence, predicted structures, experimental structures, docking outputs, and validation plans distinct so that confidence in one layer is not mistaken for evidence in another.

## Sequence And Construct Design

- Inspect DNA, RNA, or protein sequences and preserve declared alphabet and orientation.
- Back-translate proteins under explicit codon choices.
- Discover CRISPR guide candidates and PCR primer candidates for subsequent review.
- Map restriction sites and audit Golden Gate assembly plans.
- Scan protein glycosylation contexts and summarize steady-state enzyme kinetics.

Representative modules include `sequence-inspect`, `sequence-back-translate`, `crispr-design`, `primer-design`, `restriction-plan`, `golden-gate-plan`, `glycosylation-scan`, and `enzyme-kinetics`.

## Molecular Evidence

- Resolve compound identity and descriptors from PubChem with namespace and ambiguity checks.
- Retrieve RCSB entry, polymer-entity, and ligand evidence while preserving deposited identifiers.
- Retrieve AlphaFold DB model records, sequence coverage, provider version, release date, and confidence resources without treating predicted structures as experiments.

Representative modules include `chemical-evidence`, `structure-search`, `structure-evidence`, `structure-polymer-entities`, `structure-ligands`, and `alphafold-structure-evidence`.

## Structure Analysis

- Assess coordinate completeness, alternate locations, occupancy, and B-factor or pLDDT semantics.
- Compare structures with explicit chain maps, sequence correspondence, coverage, identity, rigid transform, and independently checked RMSD.
- Assign residue-level secondary structure through observed DSSP execution.
- Create provenance-bound interactive molecular views for inspection rather than analytical substitution.

These capabilities are implemented by `structure-quality-assessment`, `structure-chain-comparison`, `protein-secondary-structure`, and `structure-interactive-visualization`.

## Docking And Chemical Review

- Validate receptor, ligand, configuration, and complete pose inventories before interpretation.
- Review pose identity, geometry, clashes, diversity, and malformed records while retaining failures.
- Filter SMILES, CSV, or SDF records through validated inclusion and exclusion SMARTS with complete accepted and rejected ledgers.

These capabilities are implemented by `docking-pose-review` and `chemical-substructure-filter`.

## Quality Gates

The workbench does not equate docking confidence with affinity, pLDDT with experimental certainty, B-factor with predicted confidence, structural similarity with functional equivalence, or a computational design with experimental success. Missing atoms, chain mismatches, low correspondence, invalid chemistry, incomplete pose directories, and unsupported score semantics remain visible and can block downstream claims.

## Typical Deliverables

Sequence and construct plans, target dossiers, structure inventories, quality reports, chain-comparison tables, secondary-structure tracks, docking-review ledgers, chemical-filter results, molecular figures, mechanistic hypotheses, and prioritized experimental validation plans.
