# Molecular And Structural Biology

Languages: [English](molecular-and-structural.md) · [中文](molecular-and-structural.zh-CN.md)

## Scientific Role

This capability area connects sequence, chemistry, interaction networks, and three-dimensional structures to testable molecular hypotheses. Design calculations, database records, predicted structures, experimental structures, docking results, and validation experiments remain distinct so that confidence at one level is not presented as evidence at another.

## Sequence, Constructs, And Molecular Evidence

The workbench covers sequence inspection and alignment, ORF analysis, primer and PCR design, CRISPR, restriction enzymes and Golden Gate assembly, GenBank CDS extraction, glycosylation sites, enzyme kinetics, ITC, UniProt, PubChem, RCSB PDB, AlphaFold DB, and protein-disorder tendency. Each result retains molecular identity, orientation, coordinates, method version, parameters, and conditions of interpretation.

## Structural Quality And Comparison

Structural analysis checks coordinate completeness, alternate conformations, occupancy, and the correct meaning of B-factor or pLDDT. Comparisons record chain correspondence, sequence coverage, rigid transformation, and independently checked RMSD. Secondary structure is assigned with DSSP, and provenance-linked interactive views can be created. Structural similarity can motivate a hypothesis but does not establish functional equivalence.

## Protein Interaction Networks

Protein interaction analysis uses STRING to resolve identifiers, separates functional-association networks from physical-interaction subnetworks, and records unmapped proteins, evidence-channel scores, and enrichment of interactions in the submitted set. Deliverables include node and edge tables, a Cytoscape style, PDF/SVG/600-dpi PNG figures, and the data needed to reproduce them. STRING is useful for candidate prioritisation and systems context; it cannot establish direct binding by itself.

## Complex Prediction And Molecular Docking

- HADDOCK3 performs restraint-guided complex docking with research-level sampling kept separate from small integration tests. Ranked models, clusters, HADDOCK scores, reference-dependent DockQ metrics, PRODIGY affinity estimates, interface contacts, residue coordinates, editable PyMOL scenes, and publication figures retain their distinct meanings.
- AlphaFold 3 support prepares the official AlphaFold Server import package, chain mapping, and manual-submission guidance. An agent may check access and open the official page, but the user completes Google sign-in, entity review, and final submission. Biomed Workbench stores no password, token, cookie, or browser session and does not call an undocumented submission interface.
- Downloaded Server results are checked so that the request, structures, and confidence files form a consistent model set. All models enter ranking and confidence tables; the top-ranked model is used for structure coordinates, residue pLDDT, PAE, cross-chain profiles, candidate contacts, and PDF/SVG/600-dpi PNG figures with replot data.
- AlphaFold Server import and figure generation have completed representative acceptance, but a successful prediction is not evidence that two molecules interact in vivo. Exact versions and acceptance scope are recorded in the [Release Notes](../releases/README.md).
- Server results retain their source and follow the official output terms. Local official AlphaFold 3 is considered only with a compatible Linux/NVIDIA environment, approved model weights, complete databases, sufficient resources, and explicit user permission.

AlphaFold 3 and docking answer different questions. AlphaFold 3 proposes a co-folded arrangement and reports model confidence. HADDOCK3 samples binding modes under physical or experimental restraints. Agreement can strengthen prioritisation, but interaction, affinity, and function still require biochemical, biophysical, or cellular evidence.

## MSBio2, Metascape, And Cytoscape

The workbench can use a locally licensed MSBio2 installation or review an existing complete Metascape result directory. It checks enrichment workbooks, GO and PPI networks, MCODE components, reports, and figures; Cytoscape then imports XGMML, applies a consistent style and layout, and exports an editable `.cys` session with PDF/SVG/PNG figures. Cytoscape started by the workbench exits normally after files are saved and checked; a session already opened by the user is left running.

## Publication-Grade Figures And Independent Replotting

Structure and docking outputs follow shared final-size guidance: colour-blind-safe chain colours, 5–7 pt text, lines of at least 0.5 pt, explicit distance and confidence units, legends outside molecular views, editable vector text, PDF/SVG primary exports, and 600-dpi PNG. A standard figure set includes a complex overview, interface residue-contact map, model-quality summary, and confidence or PAE views when supported by the data. Replot data and an editable molecular scene accompany each figure.

## Interpretation Boundaries

A docking score is not affinity, pLDDT is not experimental certainty, B-factor and predicted confidence are not interchangeable, a network edge does not automatically mean direct interaction, and an attractive complex image is not mechanistic evidence. Missing atoms, incorrect chain mapping, non-standard residues, incompatible reference structures, insufficient sampling, unclear score meaning, or incomplete results can prevent the corresponding conclusion from entering the project's evidence map.

## Typical Deliverables

Sequence and construct designs, molecular identity records, STRING node and edge evidence, structure inventories and quality reports, chain comparisons, AlphaFold 3 confidence review, HADDOCK3 models and interface tables, Metascape enrichment and Cytoscape sessions, publication figures and replot data, mechanistic hypotheses, and prioritised validation experiments.
