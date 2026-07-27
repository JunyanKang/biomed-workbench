# Molecular And Structural Biology

## Scientific Role

This capability area connects sequence, chemical, and structural observations to testable molecular hypotheses. It keeps design calculations, database evidence, predicted structures, experimental structures, docking outputs, and validation plans distinct so that confidence in one layer is not mistaken for evidence in another.

## Unified Molecular Program

For broad molecular-design requests, the workbench stages the plan from sequence and record inspection to design, verification, structural assessment, docking review, and chemical filtering. PCR workflows keep primer candidate selection upstream of finite-panel specificity screening and amplicon simulation. Structure workflows keep deposited or predicted coordinate evidence separate from quality assessment, chain comparison, visualization, docking interpretation, and chemical identity filtering.

The staged plan is a design and review program, not experimental confirmation. It exposes the selected module contracts, template sections, compatibility evidence, and quality gates so Codex can adapt the correct project-owned code and keep unsupported molecular claims out of downstream manuscripts or patent materials.

## Sequence And Construct Design

- Inspect DNA, RNA, or protein sequences and preserve declared alphabet and orientation.
- Align two unambiguous DNA, RNA, or protein sequences with a declared global or local scoring contract, exact Biopython version, zero-based half-open aligned blocks, identity, coverage, and gap accounting.
- Find complete start-to-stop ORFs on one or both unambiguous DNA strands under an explicit NCBI genetic code, retaining coding orientation and forward-sequence coordinates.
- Localize descriptive substitutions, insertions, and deletions from a real global alignment while retaining its scoring contract and reference-coordinate offset; this remains distinct from genomic VCF calling.
- Enumerate exact-match PCR products on declared linear or circular templates, retaining binding sites, topology, complete candidate amplicons and any result cap.
- Bind one explicit ranked primer-design candidate to a PCR request before simulation; candidate selection remains a traceable decision rather than an implicit downstream default.
- Screen a chosen primer pair across a declared finite reference panel, retaining all exact-match products and blocking unsupported general-specificity claims.
- Plan linear Sanger-verification coverage with each selected primer's binding interval, orientation, expected read reach, merged target coverage, and explicit uncovered intervals.
- Validate and summarize supplied RNA dot-bracket structures with base-pair, stem and optional sequence-pair-class accounting; it does not replace folding prediction or experimental structure determination.
- Summarize per-column coverage, consensus and diversity from a declared pre-aligned protein sequence set while retaining the upstream alignment as part of the evidence contract.
- Summarize a processed circular-dichroism thermal transition with interpolated midpoint, width and monotonicity diagnostics, without treating it as structural deconvolution or thermodynamic fitting.
- Fit one declared series of integrated ITC heats to a dilution-aware one-site model, retaining thermodynamic parameters, residuals, uncertainty, convergence and boundary diagnostics; see [one-site ITC binding](itc-single-site-binding.md).
- Back-translate proteins under explicit codon choices.
- Discover Primer3 thermodynamics-ranked PCR primer candidates and CRISPR guide candidates for subsequent review.
- Map restriction sites, predict supported exact-motif restriction digest fragments, and audit Golden Gate assembly plans.
- Scan protein glycosylation contexts and summarize steady-state enzyme kinetics.

Representative modules include `sequence-inspect`, `sequence-pairwise-alignment`, `sequence-variant-localization`, `open-reading-frame-annotation`, `rna-secondary-structure-summary`, `aligned-protein-conservation`, `cd-thermal-transition-summary`, `primer-design`, `pcr-primer-pair-selection`, `pcr-amplicon-simulation`, `primer-pair-specificity-screen`, `sanger-verification-coverage`, `sequence-back-translate`, `crispr-design`, `restriction-plan`, `golden-gate-plan`, `glycosylation-scan`, and `enzyme-kinetics`.

- Extract annotation-bound CDS sequences from one declared GenBank record, retaining exact matching qualifiers, feature coordinates, strand, translation table, and translation agreement. See [GenBank coding sequence extraction](genbank-coding-sequence-extraction.md).

## Molecular Evidence

- Resolve compound identity and descriptors from PubChem with namespace and ambiguity checks.
- Retrieve RCSB entry, polymer-entity, and ligand evidence while preserving deposited identifiers.
- Retrieve AlphaFold DB model records, sequence coverage, provider version, release date, and confidence resources without treating predicted structures as experiments.
- Retrieve accession-bound IUPred2A residue-level disorder tendency profiles and declared score-threshold spans without treating a prediction as structural or functional validation.

Representative modules include `chemical-evidence`, `structure-search`, `structure-evidence`, `structure-polymer-entities`, `structure-ligands`, `alphafold-structure-evidence`, and `protein-disorder-evidence`.

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
