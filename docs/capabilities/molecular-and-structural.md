# Molecular And Structural Biology

## Scientific Role

This capability area connects sequence, chemical, and structural observations to testable molecular hypotheses. It keeps design calculations, database evidence, predicted structures, experimental structures, docking outputs, and validation plans distinct so that confidence in one layer is not mistaken for evidence in another.

## Unified Molecular Program

For broad molecular-design requests, the workbench stages the plan from sequence and record inspection to design, verification, structural assessment, docking review, and chemical filtering. PCR workflows keep primer candidate selection upstream of finite-panel specificity screening and amplicon simulation. Structure workflows keep deposited or predicted coordinate evidence separate from quality assessment, chain comparison, visualization, docking interpretation, and chemical identity filtering.

The staged plan is a design and review program, not experimental confirmation. It exposes the selected module contracts, template sections, compatibility evidence, and quality gates so Codex can execute the correct packaged workflow and keep unsupported molecular claims out of downstream manuscripts or patent materials.

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

## Protein Interaction Networks

`protein-interaction-network-evidence` resolves identifiers through STRING 12.0, keeps functional-association and physical-subnetwork semantics separate, records identifier losses and evidence-channel scores, and tests whether the submitted protein set is more connected than expected. The output includes node and edge tables, a Cytoscape style, PDF/SVG/600-dpi PNG figures and a digest-bound replot manifest. STRING evidence prioritizes candidates and network context; it does not establish direct binding.

## Complex Prediction And Docking

- `protein-complex-docking` executes a closed HADDOCK3 workflow with declared restraints and distinct integration-test and production sampling profiles. It preserves all ranked models and clusters, keeps HADDOCK score, reference-backed DockQ metrics and PRODIGY affinity estimates semantically separate, and exports interface contacts, residue coordinates, normalized model scores, editable PyMOL instructions and publication figures.
- `alphafold3-complex-prediction` defaults to an official AlphaFold Server import package with chain mapping and manual-submission instructions. Codex checks the interactive-access state; the user signs in with Google on the official page, reviews every entity, and submits manually. A complete downloaded result can be reloaded into ranking, PAE, pLDDT, pTM, ipTM, chain and chain-pair confidence tables plus PDF/SVG/600-dpi PNG figures. The workbench stores no password, token, cookie, or browser session and calls no undocumented interface. Server-origin results are tagged and cannot flow to automated ligand/peptide docking or interaction prediction. The optional local official AlphaFold 3 entry requires compatible Linux/NVIDIA hardware, approved weights and complete databases, a live CPU/available-memory/free-disk/free-GPU gate that leaves at least half of current headroom unused, and explicit user permission.

AlphaFold 3 and docking answer different questions. AlphaFold 3 proposes a co-folded biomolecular arrangement with model confidence; HADDOCK3 samples complexes under explicit physical or experimental restraints. Agreement may strengthen prioritization, but neither method demonstrates interaction, affinity or function without independent evidence.

## Metascape, MSBio2 And Cytoscape

`metascape-msbio-network-analysis` executes a licensed local MSBio2 wrapper when available or audits an existing complete Metascape result bundle. It reconciles enrichment workbooks, GO and PPI XGMML networks, MCODE components, reports and figures. The paired Cytoscape renderer imports the admitted XGMML through CyREST, applies recorded publication styling and layout, and exports an editable session plus PDF/SVG/PNG. Local licenses, private paths and result data remain outside the public package. When the task launches Cytoscape, it must save the session, request a normal exit after validating every export, and verify that the task-owned process has terminated; a Cytoscape session already owned by the user is left running.

## Pose And Chemical Review

- Validate receptor, ligand, configuration, and complete pose inventories before interpretation.
- Review pose identity, geometry, clashes, diversity, and malformed records while retaining failures.
- Filter SMILES, CSV, or SDF records through validated inclusion and exclusion SMARTS with complete accepted and rejected ledgers.

These focused downstream capabilities are implemented by `docking-pose-review` and `chemical-substructure-filter`; they complement rather than replace the full complex-docking workflow.

## Publication-Grade Structural Figures

Structure and docking modules follow the shared final-size figure contract: color-blind-safe chain colors, 5–7 pt text, strokes of at least 0.5 pt, explicit coordinate and confidence units, legends outside molecular views, editable vector text, PDF/SVG primary exports and 600-dpi PNG. A standard complex bundle includes a chain-colored overview, interface residue-contact map, complete model-quality summary when comparable metrics exist, and confidence or PAE panels when available. Every figure is paired with the exact replot tables, source digests, style version and an editable molecular-view scene or session. Users may re-render from those tables; the workbench also produces the standard figure set directly.

## Quality Gates

The workbench does not equate docking confidence with affinity, pLDDT with experimental certainty, B-factor with predicted confidence, structural similarity with functional equivalence, or a computational design with experimental success. Missing atoms, chain mismatches, low correspondence, invalid chemistry, incomplete pose directories, and unsupported score semantics remain visible and can block downstream claims.

## Typical Deliverables

Sequence and construct plans, target dossiers, STRING node/edge evidence, structure inventories, quality reports, chain-comparison tables, secondary-structure tracks, AlphaFold 3 confidence audits, HADDOCK3 model and interface ledgers, Metascape enrichment and Cytoscape sessions, chemical-filter results, publication-ready molecular figures with replot tables, mechanistic hypotheses, and prioritized experimental validation plans.
