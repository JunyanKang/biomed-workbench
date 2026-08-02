#!/usr/bin/env python3
"""Generate clean-room structural-analysis module contracts and route cases."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.contract import parse_manifest  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402


VERIFIED_AT = "2026-07-15"
PYTHON_VERSION = "3.11.15"
PYTHON_POLICY = ">=3.11,<3.15"


def _format(name: str, version: str, representation: str, orientation: str) -> dict[str, object]:
    return {
        "name": name,
        "versions": [version],
        "representations": [representation],
        "compression": ["none"],
        "required_indexes": [],
        "coordinate_systems": ["cartesian-angstrom"] if name in {"pdb", "mmcif", "sdf"} else [],
        "genome_build_policy": "not_applicable",
        "genome_builds": [],
        "annotation_releases": [],
        "orientations": [orientation],
    }


def _tool(
    name: str,
    identity: str,
    version: str,
    allowed: str,
    source: str,
    probe: list[str],
    description: str,
    action: str,
    *,
    ecosystem: str = "python",
) -> dict[str, object]:
    return {
        "name": name,
        "ecosystem": ecosystem,
        "identity": identity,
        "required": True,
        "tested_versions": [version],
        "allowed_versions": [allowed],
        "version_source": source,
        "verified_at": VERIFIED_AT,
        "version_probe": probe,
        "version_probe_kind": "command",
        "version_probe_timeout_seconds": 30,
        "version_pattern": "([0-9]+(?:\\.[0-9]+)+)",
        "mismatch_policy": "block",
        "version_differences": [
            {
                "id": f"{name}-validated-api",
                "affected_versions": [allowed],
                "category": "api",
                "description": description,
                "compatibility_effect": "requires-parser",
                "required_action": action,
                "source": source,
            }
        ],
        "platforms": ["any"],
    }


TOOLS = {
    "biopython": _tool(
        "biopython",
        "Bio.PDB",
        "1.87",
        ">=1.87,<1.88",
        "https://biopython.org/docs/latest/api/Bio.PDB.html",
        ["python3", "-c", "import Bio; print(Bio.__version__)"],
        "Bio.PDB parser, aligner, superposition, DSSP adapter, and writer APIs are used with explicit model and chain selection.",
        "Validate parser behavior, residue identity, chain mapping, coordinate counts, and serialized outputs before admitting results.",
    ),
    "rdkit": _tool(
        "rdkit",
        "rdkit",
        "2025.09.6",
        ">=2025.9,<2026",
        "https://www.rdkit.org/docs/",
        ["python3", "-c", "import rdkit; print(rdkit.__version__)"],
        "RDKit molecule parsing, sanitization, SMARTS matching, stereochemical identity, conformer, and distance APIs are version-sensitive.",
        "Retain every invalid molecule, query, match, stereochemical identity, and coordinate-quality state instead of silently dropping records.",
    ),
    "mkdssp": _tool(
        "mkdssp",
        "mkdssp",
        "4.6.1",
        ">=4.6,<4.7",
        "https://github.com/PDB-REDO/dssp",
        ["mkdssp", "--version"],
        "DSSP 4.6 emits residue-level secondary structure and accessibility from an explicit coordinate model through the mkdssp executable.",
        "Require observed mkdssp execution, preserve DSSP codes, reconcile chain and residue identifiers, and block invented fallback assignments.",
        ecosystem="system",
    ),
    "py3dmol": _tool(
        "py3dmol",
        "py3Dmol",
        "2.5.3",
        ">=2.5,<2.6",
        "https://3dmol.csb.pitt.edu/doc/py3Dmol.html",
        ["python3", "-c", "import py3Dmol; print(py3Dmol.__version__)"],
        "py3Dmol serializes molecular coordinates, selections, styles, colors, and views into an interactive HTML representation.",
        "Validate structure format, selection scope, confidence semantics, nonblank HTML, and source and output digests; do not treat rendering as analysis.",
    ),
    "matplotlib": _tool(
        "matplotlib",
        "matplotlib",
        "3.11.0",
        ">=3.11,<3.12",
        "https://matplotlib.org/stable/api/index.html",
        ["python3", "-c", "import matplotlib; print(matplotlib.__version__)"],
        "Matplotlib SVG rendering and patch geometry create a deterministic secondary-structure track from validated DSSP rows.",
        "Require complete residue accounting, explicit segment boundaries, a nonblank parseable SVG, and a digest-bound diagram manifest.",
    ),
}


def _python_dependency() -> dict[str, object]:
    return {
        "name": "python",
        "ecosystem": "runtime",
        "identity": "python-runtime",
        "required": True,
        "tested_versions": [PYTHON_VERSION],
        "allowed_versions": [PYTHON_POLICY],
        "version_source": "https://www.python.org/downloads/",
        "verified_at": VERIFIED_AT,
        "version_probe": ["biomed_workbench.modules.compatibility:probe_python_runtime"],
        "version_probe_kind": "python_callable",
        "version_probe_timeout_seconds": 5,
        "version_pattern": "([0-9]+(?:\\.[0-9]+)+)",
        "purpose": "Execute the project-adapted structural-analysis template and emit versioned provenance.",
        "conflicts": [],
        "platforms": ["any"],
    }


COMMON_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "handoff_type": {"type": "string", "enum": ["packaged_parameterized_project_analysis"]},
        "module": {"type": "object"},
        "request_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "request_fields": {"type": "array"},
        "languages": {"type": "array"},
        "code_plan": {"type": "array"},
        "parameter_rules": {"type": "array"},
        "preflight_checks": {"type": "array"},
        "postflight_checks": {"type": "array"},
        "provenance_fields": {"type": "array"},
        "forbidden_actions": {"type": "array"},
        "tool_profiles": {"type": "array"},
        "dependency_profiles": {"type": "array"},
        "quality_gate_ids": {"type": "array"},
        "execution_policy": {"type": "object"},
    },
    "required": [
        "handoff_type", "module", "request_digest", "request_fields", "languages", "code_plan",
        "parameter_rules", "preflight_checks", "postflight_checks", "provenance_fields",
        "forbidden_actions", "tool_profiles", "dependency_profiles", "quality_gate_ids", "execution_policy",
    ],
}


SPECS: dict[str, dict[str, object]] = {
    "structure-quality-assessment": {
        "title": "Assess coordinate and confidence quality without conflating B-factor and pLDDT",
        "description": "Inspect PDB or mmCIF coordinates by model and chain, reconcile atoms and residues, diagnose occupancy, alternate locations, missing backbone atoms and coordinate anomalies, and interpret B-factor as pLDDT only when explicitly declared for an AlphaFold-style prediction.",
        "intents": ["assess protein structure quality", "validate PDB or mmCIF coordinates and confidence", "检查蛋白结构质量并区分B因子和pLDDT"],
        "question": "Are the selected coordinates structurally parseable and scientifically interpretable under their declared experimental or predicted confidence semantics?",
        "tools": ["biopython"],
        "template": "templates/assess_structure_quality.py",
        "input_artifacts": [("structure_coordinates", "structure_coordinates", ["pdb", "mmcif"])],
        "output_artifacts": [("structure_quality_report", "structure_quality_report", ["tabular", "inline-json"])],
        "input_schema": {
            "objective": {"type": "string", "minLength": 12, "maxLength": 4000},
            "structure_path": {"type": "string", "minLength": 1, "maxLength": 4096},
            "structure_format": {"type": "string", "enum": ["pdb", "mmcif"]},
            "confidence_semantics": {"type": "string", "enum": ["experimental-b-factor", "alphafold-plddt", "unknown"]},
            "model_index": {"type": "integer", "minimum": 0},
            "selected_chains": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 8}, "uniqueItems": True},
        },
        "required": ["objective", "structure_path", "structure_format", "confidence_semantics", "model_index", "selected_chains"],
        "gates": [
            ("structure-quality-input-integrity", "Block unreadable, mutable, empty, unsupported, multi-model-ambiguous, or non-finite coordinate input."),
            ("structure-quality-coordinate-accounting", "Require model, chain, residue, atom, alternate-location, occupancy, and missing-backbone accounting to reconcile."),
            ("structure-quality-confidence-semantics", "Interpret coordinate B values as pLDDT only for explicitly declared compatible predicted structures; otherwise retain them as experimental B-factor or unknown."),
            ("structure-quality-output-integrity", "Require reloadable reports with source digest, versions, parameters, warnings, gate states, and output digest."),
        ],
        "parameter": ("select-structure-quality-scope", "model-and-chains", ["structure-format", "model-count", "chain-identifiers", "confidence-semantics"], "Select one observed model and explicit chains before calculating quality summaries.", "Block missing chains, implicit model selection, or confidence semantics inferred only from numeric range."),
        "preflight": ["Hash and parse the immutable coordinate file with the declared PDB or mmCIF parser.", "List models and chains before selecting analysis scope.", "Declare experimental B-factor, AlphaFold pLDDT, or unknown confidence semantics from provenance."],
        "postflight": ["Reconcile selected residues and atoms with every reported denominator.", "Confirm occupancy, alternate-location, missing-backbone, finite-coordinate, and confidence summaries are internally consistent.", "Reload JSON and tabular outputs and verify source and output digests."],
        "forbidden": ["Do not label arbitrary B-factor columns as pLDDT.", "Do not silently select the first model or chain when the request is ambiguous.", "Do not repair coordinates or overwrite source files inside this assessment."],
        "sources": ["https://biopython.org/docs/latest/api/Bio.PDB.html", "https://www.wwpdb.org/documentation/file-format"],
        "case": {"objective": "Assess one declared AlphaFold coordinate model before downstream comparison.", "structure_path": "inputs/AF-P04637-F1-model_v6.cif", "structure_format": "mmcif", "confidence_semantics": "alphafold-plddt", "model_index": 0, "selected_chains": ["A"]},
    },
    "structure-chain-comparison": {
        "title": "Compare protein structures with explicit chain and sequence correspondence",
        "description": "Align declared chain pairs by sequence, map residue correspondence, superpose matched C-alpha coordinates, report identity, coverage and RMSD, and leave TM-score explicitly uncomputed unless an independently validated TM-align result is supplied.",
        "intents": ["compare protein structures", "chain-aware structural alignment and RMSD", "按链和序列对应关系比较蛋白结构"],
        "question": "How similar are the declared chain pairs after sequence-aware coordinate correspondence, and which unmatched or low-coverage regions limit interpretation?",
        "tools": ["biopython"],
        "template": "templates/compare_structure_chains.py",
        "input_artifacts": [("reference_coordinates", "structure_coordinates", ["pdb", "mmcif"]), ("moving_coordinates", "structure_coordinates", ["pdb", "mmcif"])],
        "output_artifacts": [("structure_comparison_report", "structure_comparison_report", ["inline-json"]), ("superposed_coordinates", "structure_coordinates", ["pdb", "mmcif"])],
        "input_schema": {
            "objective": {"type": "string", "minLength": 12, "maxLength": 4000},
            "reference_path": {"type": "string", "minLength": 1, "maxLength": 4096},
            "moving_path": {"type": "string", "minLength": 1, "maxLength": 4096},
            "structure_format": {"type": "string", "enum": ["pdb", "mmcif"]},
            "chain_map": {"type": "object", "minProperties": 1},
            "reference_model_index": {"type": "integer", "minimum": 0},
            "moving_model_index": {"type": "integer", "minimum": 0},
            "minimum_aligned_residues": {"type": "integer", "minimum": 3},
        },
        "required": ["objective", "reference_path", "moving_path", "structure_format", "chain_map", "reference_model_index", "moving_model_index", "minimum_aligned_residues"],
        "gates": [
            ("structure-comparison-input-integrity", "Require immutable parseable inputs, source digests, explicit models, and one-to-one chain mapping."),
            ("structure-comparison-correspondence", "Require sequence-derived residue correspondence with identity, coverage, gaps, unresolved residues, and matched C-alpha counts."),
            ("structure-comparison-superposition", "Require finite rigid-body transform, sufficient matched atoms, independently recomputed RMSD, and unmodified reference coordinates."),
            ("structure-comparison-score-semantics", "Do not report approximate RMSD-derived values as TM-score; retain TM-score as not computed unless produced by a validated TM-align backend."),
            ("structure-comparison-output-integrity", "Require reloadable reports and superposed coordinates with complete provenance and digests."),
        ],
        "parameter": ("select-chain-correspondence", "chain-map", ["reference-chains", "moving-chains", "sequence-identity", "biological-construct"], "Declare a one-to-one reference-to-moving chain map from the biological construct and observed sequences.", "Block duplicated chains, absent chains, insufficient matched C-alpha atoms, or chain-agnostic whole-file pairing."),
        "preflight": ["Hash and parse both structures and enumerate models, chains, residue identifiers, and sequences.", "Validate a one-to-one chain map against observed chain identifiers.", "Freeze alignment scoring and minimum matched-residue requirements before superposition."],
        "postflight": ["Recompute sequence identity, chain coverage, matched C-alpha count, transform determinant, and RMSD.", "Retain unmatched residues and low-coverage chain pairs as explicit limitations.", "Reload the transformed PDB and ensure the reference remained unchanged."],
        "forbidden": ["Do not pair residues only by list position across chains.", "Do not report an approximate or invented TM-score.", "Do not hide chain pairs with poor identity, coverage, or unresolved coordinates."],
        "sources": ["https://biopython.org/docs/latest/api/Bio.Align.html", "https://biopython.org/docs/latest/api/Bio.PDB.Superimposer.html"],
        "case": {"objective": "Compare a predicted monomer against an experimental reference with declared chain correspondence.", "reference_path": "inputs/reference.pdb", "moving_path": "inputs/predicted.pdb", "structure_format": "pdb", "chain_map": {"A": "A"}, "reference_model_index": 0, "moving_model_index": 0, "minimum_aligned_residues": 30},
    },
    "docking-pose-review": {
        "title": "Prepare and review docking workflows with complete chemical and coordinate checks",
        "description": "Validate and serialize DiffDock-style batch inputs and bounded inference parameters, then inventory pose outputs, preserve producer version and rank/confidence semantics, sanitize every ligand with RDKit, verify identity and 3D coordinates, quantify receptor clashes and pose diversity, and retain invalid or missing poses instead of ranking them away.",
        "intents": ["review DiffDock results", "validate docking poses and clashes", "复核分子对接构象排名身份和空间冲突"],
        "question": "Which docking poses remain chemically and geometrically reviewable after complete result accounting, and what prevents any pose from being interpreted as binding evidence?",
        "tools": ["rdkit", "biopython"],
        "template": ["templates/prepare_docking_batch.py", "templates/review_docking_poses.py"],
        "input_artifacts": [("docking_batch_manifest", "docking_batch_manifest", ["csv"]), ("docking_inference_config", "docking_inference_config", ["json"]), ("receptor_coordinates", "structure_coordinates", ["pdb"]), ("docking_results", "docking_pose_collection", ["sdf"])],
        "output_artifacts": [("validated_docking_batch", "docking_batch_manifest", ["csv"]), ("validated_docking_config", "docking_inference_config", ["yaml"]), ("docking_preparation_report", "docking_preparation_report", ["inline-json"]), ("docking_review_report", "docking_review_report", ["tabular", "inline-json"])],
        "input_schema": {
            "objective": {"type": "string", "minLength": 12, "maxLength": 4000},
            "receptor_path": {"type": "string", "minLength": 1, "maxLength": 4096},
            "results_directory": {"type": "string", "minLength": 1, "maxLength": 4096},
            "diffdock_version": {"type": "string", "minLength": 1, "maxLength": 128},
            "ligand_identity": {"type": "string", "minLength": 1, "maxLength": 2048},
            "severe_clash_distance": {"type": "number", "exclusiveMinimum": 0},
            "contact_distance": {"type": "number", "exclusiveMinimum": 0},
            "batch_manifest_path": {"type": "string", "minLength": 1, "maxLength": 4096},
            "inference_config": {"type": "object"},
        },
        "required": ["objective", "receptor_path", "results_directory", "diffdock_version", "ligand_identity", "severe_clash_distance", "contact_distance", "batch_manifest_path", "inference_config"],
        "gates": [
            ("docking-preparation-manifest", "Require the exact four-column DiffDock batch contract, unique safe complex names, exclusive protein path or sequence, and complete row accounting."),
            ("docking-preparation-identity", "Require stable in-boundary PDB or SDF files, parseable finite protein coordinates, bounded protein sequences, and RDKit-validated ligand identity."),
            ("docking-preparation-parameters", "Require a closed configuration schema, explicit model-family flags, bounded diffusion and sampling parameters, and internally consistent step counts."),
            ("docking-review-result-accounting", "Inventory every expected and observed pose, duplicate rank, parse failure, confidence value, and source digest."),
            ("docking-review-chemical-identity", "Require RDKit sanitization, declared ligand identity reconciliation, stereochemical SMILES, heavy-atom count, fragment count, and finite 3D coordinates."),
            ("docking-review-geometry", "Require receptor coordinate parsing, distance thresholds fixed before review, severe-clash and close-contact counts, and pose-diversity accounting."),
            ("docking-review-score-semantics", "Treat DiffDock confidence as producer-specific ranking evidence, never affinity, thermodynamics, kinetics, or experimental binding."),
            ("docking-review-output-integrity", "Require reloadable per-pose and summary outputs with versions, parameters, warnings, and digests."),
        ],
        "parameter": ("select-docking-review-thresholds", "distance-thresholds", ["coordinate-units", "receptor-preparation", "ligand-heavy-atoms", "predeclared-policy"], "Freeze severe-clash and close-contact distance thresholds in Angstrom before reading pose ranks.", "Block inverted thresholds, non-finite coordinates, unverified ligand identity, or incomplete pose inventory."),
        "preflight": ["Validate the four-column batch manifest, unique complex names, exclusive protein path or sequence, ligand identity, bounded configuration, and source digests.", "Hash receptor and every pose file and preserve the declared DiffDock producer version.", "Inventory ranks and confidence values before filtering or sorting and freeze clash thresholds."],
        "postflight": ["Reconcile every pose to one retained success or reason-coded failure record.", "Verify finite coordinates, chemical identity, rank uniqueness, clash counts, and pairwise pose RMSD where atom identity permits.", "Reload report tables and verify all source and output digests."],
        "forbidden": ["Do not treat DiffDock confidence as binding affinity or validation.", "Do not silently skip RDKit parse or sanitization failures.", "Do not select a pose only because it has the desired visual orientation."],
        "sources": ["https://github.com/gcorso/DiffDock", "https://www.rdkit.org/docs/"],
        "case": {"objective": "Prepare a bounded docking batch and review all generated poses before experimental follow-up.", "receptor_path": "inputs/receptor.pdb", "results_directory": "results/diffdock/complex_001", "diffdock_version": "declared-project-version", "ligand_identity": "CC(=O)OC1=CC=CC=C1C(=O)O", "severe_clash_distance": 1.2, "contact_distance": 2.0, "batch_manifest_path": "inputs/diffdock_batch.csv", "inference_config": {"inference_steps": 20, "actual_steps": 19, "samples_per_complex": 10, "sigma_schedule": "expbeta", "no_final_step_noise": True}},
    },
    "chemical-substructure-filter": {
        "title": "Filter chemical records with validated SMARTS and complete record accounting",
        "description": "Load SMILES, CSV, or SDF molecules, preserve record identity and failures, validate inclusion and exclusion SMARTS, retain atom-level matches and stereochemical canonical identity, and emit complete accepted and rejected ledgers.",
        "intents": ["filter molecules by SMARTS", "chemical substructure inclusion exclusion", "使用SMARTS筛选化合物并保留全部失败记录"],
        "question": "Which explicitly identified molecules satisfy every declared inclusion and exclusion SMARTS query after sanitization and complete record accounting?",
        "tools": ["rdkit"],
        "template": "templates/filter_chemical_substructures.py",
        "input_artifacts": [("chemical_records", "chemical_record_collection", ["smi", "sdf", "csv"])],
        "output_artifacts": [("substructure_filter_report", "substructure_filter_report", ["tabular", "inline-json"])],
        "input_schema": {
            "objective": {"type": "string", "minLength": 12, "maxLength": 4000},
            "input_path": {"type": "string", "minLength": 1, "maxLength": 4096},
            "input_format": {"type": "string", "enum": ["smi", "sdf", "csv"]},
            "include_smarts": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 2048}, "uniqueItems": True},
            "exclude_smarts": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 2048}, "uniqueItems": True},
            "smiles_column": {"type": "string", "minLength": 1, "maxLength": 128},
            "identifier_column": {"type": "string", "minLength": 1, "maxLength": 128},
        },
        "required": ["objective", "input_path", "input_format", "include_smarts", "exclude_smarts", "smiles_column", "identifier_column"],
        "gates": [
            ("substructure-filter-input-integrity", "Require stable input, unique record identifiers, explicit format and columns, and complete row accounting."),
            ("substructure-filter-query-validity", "Require every SMARTS query to parse and preserve query order, inclusion or exclusion role, and atom-query semantics."),
            ("substructure-filter-molecule-validity", "Require reason-coded parsing and sanitization states, canonical isomeric identity, fragments, charge, heavy atoms, and atom-level matches."),
            ("substructure-filter-output-integrity", "Require accepted and rejected records to sum to input count and reload with versions, parameters, and digests."),
        ],
        "parameter": ("select-substructure-policy", "smarts-policy", ["scientific-question", "tautomer-policy", "charge-policy", "stereochemistry", "record-format"], "Declare inclusion and exclusion SMARTS and molecular identity policy before filtering.", "Block invalid SMARTS, duplicate identifiers, silent sanitization failure, or unaccounted input records."),
        "preflight": ["Hash the input and inspect format, headers, record identifiers, molecule field, and duplicate IDs.", "Parse every SMARTS query before reading molecular outcomes.", "Freeze sanitization, stereochemistry, fragment, charge, and tautomer interpretation policy."],
        "postflight": ["Require every input record to appear exactly once as accepted or reason-coded rejected.", "Recompute atom matches and canonical isomeric SMILES for accepted records.", "Reload result JSON and TSV and verify counts and digests."],
        "forbidden": ["Do not silently drop invalid molecules or invalid SMARTS.", "Do not imply tautomer, protonation, salt, or stereochemical equivalence unless explicitly standardized.", "Do not overwrite the input molecular collection."],
        "sources": ["https://www.rdkit.org/docs/RDKit_Book.html#substructure-searching", "https://www.rdkit.org/docs/GettingStartedInPython.html"],
        "case": {"objective": "Retain molecules with the required scaffold while excluding a reactive acyl halide alert.", "input_path": "inputs/library.sdf", "input_format": "sdf", "include_smarts": ["c1ccccc1"], "exclude_smarts": ["C(=O)[Cl,Br,I]"], "smiles_column": "smiles", "identifier_column": "compound_id"},
    },
    "protein-secondary-structure": {
        "title": "Assign residue-level protein secondary structure with observed DSSP execution",
        "description": "Run mkdssp through Biopython on an explicit coordinate model, retain the full DSSP alphabet, residue identifiers, amino acids and accessibility, reconcile selected chains, and refuse to invent assignments when DSSP is unavailable or residues are unresolved.",
        "intents": ["assign protein secondary structure with DSSP", "extract helices sheets turns and accessibility", "使用DSSP提取蛋白二级结构和可及性"],
        "question": "What residue-level secondary-structure and accessibility assignments does the validated DSSP backend produce for the declared model and chains?",
        "tools": ["biopython", "mkdssp", "matplotlib"],
        "template": ["templates/assign_secondary_structure.py", "templates/render_secondary_structure_diagram.py"],
        "input_artifacts": [("structure_coordinates", "structure_coordinates", ["pdb", "mmcif"]), ("secondary_structure_rows", "secondary_structure_rows", ["tabular"])],
        "output_artifacts": [("secondary_structure_report", "secondary_structure_report", ["tabular", "inline-json"]), ("secondary_structure_diagram", "secondary_structure_diagram", ["svg"]), ("secondary_structure_diagram_manifest", "secondary_structure_diagram_manifest", ["inline-json"])],
        "input_schema": {
            "objective": {"type": "string", "minLength": 12, "maxLength": 4000},
            "structure_path": {"type": "string", "minLength": 1, "maxLength": 4096},
            "structure_format": {"type": "string", "enum": ["pdb", "mmcif"]},
            "model_index": {"type": "integer", "minimum": 0},
            "chain_ids": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 8}, "minItems": 1, "uniqueItems": True},
            "dssp_executable": {"type": "string", "minLength": 1, "maxLength": 4096},
            "dssp_data_directory": {"type": "string", "minLength": 1, "maxLength": 4096},
            "diagram_chain_id": {"type": "string", "minLength": 1, "maxLength": 8},
            "diagram_title": {"type": "string", "maxLength": 256},
            "show_residue_numbers": {"type": "boolean"},
        },
        "required": ["objective", "structure_path", "structure_format", "model_index", "chain_ids", "dssp_executable", "dssp_data_directory", "diagram_chain_id", "diagram_title", "show_residue_numbers"],
        "gates": [
            ("secondary-structure-input-integrity", "Require immutable parseable coordinates, explicit model and chains, source digest, and coordinate residue accounting."),
            ("secondary-structure-backend", "Require observed compatible mkdssp execution and recorded Biopython and DSSP versions; no heuristic fallback may masquerade as DSSP."),
            ("secondary-structure-residue-accounting", "Preserve chain, residue number, insertion code, amino acid, full DSSP code, accessibility, unresolved residues, and selected-chain denominators."),
            ("secondary-structure-diagram", "Render validated DSSP rows without bridging residue-number gaps, retain full-code to category mapping, and require a nonblank parseable SVG plus digest-bound manifest."),
            ("secondary-structure-output-integrity", "Require reloadable residue and summary outputs with parameters, warnings, versions, and digests."),
        ],
        "parameter": ("select-dssp-scope", "model-and-chains", ["model-count", "chain-identifiers", "coordinate-completeness", "dssp-version"], "Select one observed coordinate model and explicit protein chains for DSSP.", "Block absent chains, unavailable or incompatible mkdssp, empty assignments, or unreconciled residue identifiers."),
        "preflight": ["Hash and parse the coordinate file and enumerate models and chains.", "Probe the declared mkdssp executable and record its observed version.", "Freeze selected chains and residue-accounting policy before execution."],
        "postflight": ["Reconcile every DSSP row to an observed chain and residue identifier.", "Retain H, B, E, G, I, T, S, and blank codes without collapsing the source table.", "Split diagram segments at category changes and residue-number or insertion-code discontinuities.", "Reload row, summary, SVG, and diagram-manifest outputs and verify counts and digests."],
        "forbidden": ["Do not infer DSSP assignments when mkdssp did not run.", "Do not collapse the full DSSP alphabet before retaining source-level rows.", "Do not imply unresolved residues are coil."],
        "sources": ["https://github.com/PDB-REDO/dssp", "https://biopython.org/docs/latest/api/Bio.PDB.DSSP.html", "https://matplotlib.org/stable/api/index.html"],
        "case": {"objective": "Assign and visualize residue-level secondary structure for the declared experimental chain.", "structure_path": "inputs/reference.pdb", "structure_format": "pdb", "model_index": 0, "chain_ids": ["A"], "dssp_executable": "mkdssp", "dssp_data_directory": "environment/share/libcifpp", "diagram_chain_id": "A", "diagram_title": "Chain A secondary structure", "show_residue_numbers": True},
    },
    "structure-interactive-visualization": {
        "title": "Create a provenance-bound interactive molecular structure view",
        "description": "Render selected PDB or mmCIF coordinates with py3Dmol using explicit chain, style and color semantics, distinguish chain and confidence coloring, and emit a nonblank HTML artifact and manifest without treating visual appearance as structural evidence.",
        "intents": ["visualize protein structure interactively", "render PDB or mmCIF with py3Dmol", "生成可追溯的交互式蛋白结构可视化"],
        "question": "Can the declared coordinate model and selection be rendered into a reproducible interactive view whose colors and labels have explicit non-analytical semantics?",
        "tools": ["py3dmol", "biopython"],
        "template": "templates/render_structure_view.py",
        "input_artifacts": [("structure_coordinates", "structure_coordinates", ["pdb", "mmcif"])],
        "output_artifacts": [("interactive_structure_view", "interactive_structure_view", ["html"]), ("visualization_manifest", "visualization_manifest", ["inline-json"])],
        "input_schema": {
            "objective": {"type": "string", "minLength": 12, "maxLength": 4000},
            "structure_path": {"type": "string", "minLength": 1, "maxLength": 4096},
            "structure_format": {"type": "string", "enum": ["pdb", "mmcif"]},
            "model_index": {"type": "integer", "minimum": 0},
            "selected_chains": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 8}, "uniqueItems": True},
            "style": {"type": "string", "enum": ["cartoon", "stick", "sphere", "line"]},
            "color_semantics": {"type": "string", "enum": ["chain", "alphafold-plddt", "uniform"]},
            "confidence_provenance": {"type": "string", "enum": ["alphafold-b-column-plddt", "not-applicable", "unknown"]},
        },
        "required": ["objective", "structure_path", "structure_format", "model_index", "selected_chains", "style", "color_semantics", "confidence_provenance"],
        "gates": [
            ("structure-view-input-integrity", "Require immutable parseable coordinates, explicit model and chain selection, and source digest."),
            ("structure-view-semantic-integrity", "Require declared style and color semantics; pLDDT coloring is allowed only for provenance-confirmed compatible predicted coordinates."),
            ("structure-view-output-integrity", "Require nonblank reloadable HTML and manifest with selections, versions, source and output digests, and a non-analytical-use boundary."),
        ],
        "parameter": ("select-structure-view-style", "style-and-color", ["scientific-purpose", "chain-count", "confidence-provenance", "coordinate-format"], "Choose a familiar molecular style and explicit chain, uniform, or provenance-confirmed pLDDT color semantics.", "Block absent chains, unsupported style, ambiguous confidence semantics, blank HTML, or missing digests."),
        "preflight": ["Hash and parse coordinates and enumerate models and chains.", "Confirm selected chains exist and color semantics are justified by provenance.", "Freeze style, background, labels, dimensions, and output paths."],
        "postflight": ["Require generated HTML to contain the molecular viewer payload and nonzero coordinate content.", "Verify source, HTML, and manifest digests and recorded versions.", "Retain a visible legend or manifest description for every color mapping."],
        "forbidden": ["Do not infer structural quality, binding, or function from appearance.", "Do not color arbitrary B-factor columns as pLDDT.", "Do not embed local absolute paths or credentials in HTML or manifests."],
        "sources": ["https://3dmol.csb.pitt.edu/doc/py3Dmol.html", "https://biopython.org/docs/latest/api/Bio.PDB.html"],
        "case": {"objective": "Render a selected AlphaFold model with confidence colors for scientific inspection.", "structure_path": "inputs/AF-P04637-F1-model_v6.pdb", "structure_format": "pdb", "model_index": 0, "selected_chains": ["A"], "style": "cartoon", "color_semantics": "alphafold-plddt", "confidence_provenance": "alphafold-b-column-plddt"},
    },
}


def _artifact(name: str, artifact_type: str, formats: list[str], *, output: bool) -> dict[str, object]:
    profiles = []
    for value in formats:
        version = {"pdb": "3.3", "mmcif": "5", "sdf": "v2000", "smi": "1", "csv": "1", "json": "RFC8259", "yaml": "1.2", "tabular": "1", "html": "5", "svg": "2", "inline-json": "1"}[value]
        representation = "structured" if value in {"json", "yaml", "tabular", "inline-json"} else "text"
        profiles.append(_format(value, version, representation, "module-output" if output else "coordinate-or-record-input"))
    return {
        "name": name,
        "artifact_type": artifact_type,
        "formats": profiles,
        "processing_levels": ["derived"] if output else ["declared", "source-preserved"],
        "required_metadata": ["module-version", "compatibility-row-id", "artifact-digest"] if output else ["input-artifact-digest", "format-version", "producer-version"],
    }


def _manifest(module_id: str, spec: dict[str, object]) -> dict[str, object]:
    gates = [{"id": gate_id, "severity": "fatal", "description": description, "blocks_interpretation": True} for gate_id, description in spec["gates"]]
    input_artifacts = [_artifact(name, artifact_type, formats, output=False) for name, artifact_type, formats in spec["input_artifacts"]]
    output_artifacts = [
        _artifact(name, artifact_type, formats if isinstance(formats, list) else [formats], output=True)
        for name, artifact_type, formats in spec["output_artifacts"]
    ]
    tools = [deepcopy(TOOLS[name]) for name in spec["tools"]]
    tool_versions = {tool["name"]: list(tool["allowed_versions"]) for tool in tools}
    input_versions = {artifact["name"]: [f"{fmt['name']}@{fmt['versions'][0]}" for fmt in artifact["formats"]] for artifact in input_artifacts}
    output_versions = {artifact["name"]: [f"{fmt['name']}@{fmt['versions'][0]}" for fmt in artifact["formats"]] for artifact in output_artifacts}
    parameter_id, parameter, decision_inputs, selection_rule, validation_rule = spec["parameter"]
    template_value = spec["template"]
    templates = list(template_value) if isinstance(template_value, list) else [str(template_value)]
    gate_ids = [item["id"] for item in gates]
    output_types = [item["artifact_type"] for item in output_artifacts]
    return {
        "schema_version": 1,
        "id": module_id,
        "version": "1.0.0",
        "title": spec["title"],
        "description": spec["description"],
        "module_type": "analysis",
        "domains": ["molecular_design"],
        "intents": spec["intents"],
        "questions": [spec["question"]],
        "entrypoint": "agent-generated-analysis",
        "execution": {"kind": "workflow", "timeout_seconds": 30, "max_output_bytes": 2_000_000},
        "maturity": "validated",
        "input_artifacts": input_artifacts,
        "output_artifacts": output_artifacts,
        "preconditions": ["Codex can inspect immutable project inputs and an existing compatible scientific environment; outputs are new and no compute-infrastructure management is required."],
        "assumptions": ["Coordinate units, molecular identity, producer provenance, model and chain scope, and scientific interpretation boundaries are declared rather than guessed."],
        "quality_gates": gates,
        "limitations": ["These computational checks support structural interpretation but do not establish experimental state, biological relevance, binding affinity, dynamics, function, or causal mechanism."],
        "evidence_effects": [f"produces-{module_id}-evidence", "blocks-unsupported-structural-claims"],
        "alternatives": [],
        "complements": ["alphafold-structure-evidence", "structure-evidence", "structure-polymer-entities", "structure-ligands"],
        "tool_requirements": tools,
        "dependencies": [_python_dependency()],
        "compatibility_matrix": [{
            "id": f"structure-analysis-2026-07-15-{module_id}",
            "module_version": "1.0.0",
            "tool_versions": tool_versions,
            "dependency_versions": {"python": [PYTHON_POLICY]},
            "input_formats": input_versions,
            "output_formats": output_versions,
            "platforms": ["any"],
            "regression_evidence_ids": [f"{module_id}-regression-v1"],
            "end_to_end_evidence_ids": [f"{module_id}-e2e-v1"],
            "verified_at": VERIFIED_AT,
        }],
        "access": "agent_generated",
        "mutability": "writes_output",
        "credentials": [],
        "input_schema": {"type": "object", "additionalProperties": False, "properties": spec["input_schema"], "required": spec["required"]},
        "output_schema": COMMON_OUTPUT_SCHEMA,
        "kernel_compatibility": [">=0.2.0,<0.3.0"],
        "provenance": {"license": "Apache-2.0", "concept_sources": list(spec["sources"]) + ["Project-owned clean-room structural-analysis implementation and scientific validation contract."]},
        "code_templates": [
            {"path": template, "language": "python", "purpose": f"Execute {spec['title'].lower()} against real project files with complete quality and provenance checks.", "quality_gate_ids": gate_ids, "requires_adaptation": False}
            for template in templates
        ],
        "agent_protocol": {
            "schema_version": 1,
            "mode": "packaged_parameterized_workflow",
            "languages": ["python"],
            "template_sections": [
                {"id": f"inspect-{module_id}", "purpose": "Inspect project inputs, provenance, scientific scope, and compatibility before execution.", "required_logic": list(spec["preflight"]), "output_artifact_types": output_types, "template_files": templates},
                {"id": f"execute-{module_id}", "purpose": "Adapt and execute the packaged template, then admit only gate-passing outputs.", "required_logic": list(spec["postflight"]), "output_artifact_types": output_types, "template_files": templates},
            ],
            "parameter_rules": [{"id": parameter_id, "parameter": parameter, "decision_inputs": decision_inputs, "selection_rule": selection_rule, "validation_rule": validation_rule}],
            "preflight_checks": list(spec["preflight"]),
            "postflight_checks": list(spec["postflight"]),
            "provenance_fields": ["module-version", "compatibility-row-id", "source-artifact-digests", "input-format-and-producer-version", "tool-and-dependency-versions", "model-chain-and-record-scope", "parameters", "quality-gate-results", "output-artifact-digests"],
            "forbidden_actions": list(spec["forbidden"]) + ["Do not install or manage dependency environments, execution infrastructure, remote job systems, or model-hosting infrastructure from inside an analysis template."],
            "requires_observed_execution": True,
        },
    }


def _case(module_id: str, spec: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "cases": [{
            "name": f"prepare-{module_id}",
            "input": spec["case"],
            "expected_subset": {"handoff_type": "packaged_parameterized_project_analysis", "module": {"id": module_id, "version": "1.0.0"}, "languages": ["python"]},
        }],
    }


def generate(*, check: bool = False) -> list[str]:
    changed = []
    for module_id, spec in SPECS.items():
        manifest = _manifest(module_id, spec)
        parse_manifest(manifest)
        files = {"module.json": manifest, "tests/cases.json": _case(module_id, spec)}
        for relative, payload in files.items():
            path = BUILTIN_ROOT / module_id / relative
            encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
            if not path.exists() or path.read_text(encoding="utf-8") != encoded:
                if module_id not in changed:
                    changed.append(module_id)
                if not check:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(encoded, encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    changed = generate(check=args.check)
    print(json.dumps({"changed_modules": changed, "count": len(changed)}, sort_keys=True))
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
