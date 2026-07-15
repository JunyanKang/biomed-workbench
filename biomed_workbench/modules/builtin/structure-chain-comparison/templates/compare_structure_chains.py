#!/usr/bin/env python3
"""Compare declared protein-chain pairs by sequence-aware C-alpha superposition."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import tempfile
from importlib.metadata import version
from pathlib import Path
from typing import Any

from Bio.Align import PairwiseAligner
from Bio.Data.PDBData import protein_letters_3to1_extended
from Bio.PDB import MMCIFIO, MMCIFParser, PDBIO, PDBParser, Superimposer, is_aa


MODULE_ID = "structure-chain-comparison"
MODULE_VERSION = "1.0.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--moving", required=True, type=Path)
    parser.add_argument("--format", required=True, choices=("pdb", "mmcif"))
    parser.add_argument("--reference-model-index", required=True, type=int)
    parser.add_argument("--moving-model-index", required=True, type=int)
    parser.add_argument("--chain-map", required=True, help="Comma-separated reference:moving chain pairs")
    parser.add_argument("--minimum-aligned-residues", required=True, type=int)
    parser.add_argument("--report-output", required=True, type=Path)
    parser.add_argument("--coordinate-output", required=True, type=Path)
    return parser.parse_args()


def stable_file(path: Path) -> tuple[Path, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("each coordinate input must be a stable regular file")
    content = path.read_bytes()
    if not content:
        raise ValueError("coordinate input is empty")
    return path.resolve(), hashlib.sha256(content).hexdigest()


def parse_structure(path: Path, structure_format: str, label: str):
    parser = PDBParser(QUIET=True) if structure_format == "pdb" else MMCIFParser(QUIET=True)
    try:
        return parser.get_structure(label, str(path))
    except Exception as exc:
        raise ValueError(f"unable to parse {label} as declared {structure_format}") from exc


def get_model(structure, model_index: int, label: str):
    models = list(structure.get_models())
    if model_index < 0 or model_index >= len(models):
        raise ValueError(f"{label} model index {model_index} is absent from {len(models)} observed models")
    return models, models[model_index]


def parse_chain_map(value: str) -> list[tuple[str, str]]:
    pairs = []
    for token in value.split(","):
        fields = [field.strip() for field in token.split(":")]
        if len(fields) != 2 or not all(fields):
            raise ValueError("chain map must contain comma-separated reference:moving pairs")
        pairs.append((fields[0], fields[1]))
    if not pairs:
        raise ValueError("at least one chain pair is required")
    if len({pair[0] for pair in pairs}) != len(pairs) or len({pair[1] for pair in pairs}) != len(pairs):
        raise ValueError("chain map must be one-to-one")
    return pairs


def chain_residues(chain) -> list[Any]:
    return [residue for residue in chain if is_aa(residue, standard=False)]


def residue_letter(residue) -> str:
    return protein_letters_3to1_extended.get(residue.resname.strip().upper(), "X")


def alignment_pairs(reference_residues: list[Any], moving_residues: list[Any]) -> tuple[list[tuple[int, int]], float]:
    reference_sequence = "".join(residue_letter(residue) for residue in reference_residues)
    moving_sequence = "".join(residue_letter(residue) for residue in moving_residues)
    if not reference_sequence or not moving_sequence:
        raise ValueError("mapped chains must each contain at least one amino-acid residue")
    aligner = PairwiseAligner(mode="global")
    aligner.match_score = 2.0
    aligner.mismatch_score = -1.0
    aligner.open_gap_score = -10.0
    aligner.extend_gap_score = -0.5
    alignment = aligner.align(reference_sequence, moving_sequence)[0]
    pairs = []
    reference_blocks, moving_blocks = alignment.aligned
    for reference_block, moving_block in zip(reference_blocks, moving_blocks, strict=True):
        reference_start, reference_end = map(int, reference_block)
        moving_start, moving_end = map(int, moving_block)
        if reference_end - reference_start != moving_end - moving_start:
            raise ValueError("sequence alignment emitted unequal aligned blocks")
        pairs.extend(zip(range(reference_start, reference_end), range(moving_start, moving_end), strict=True))
    return pairs, float(alignment.score)


def inspect_chain_pair(reference_chain, moving_chain) -> tuple[dict[str, Any], list[Any], list[Any]]:
    reference_residues = chain_residues(reference_chain)
    moving_residues = chain_residues(moving_chain)
    pairs, alignment_score = alignment_pairs(reference_residues, moving_residues)
    exact = sum(residue_letter(reference_residues[i]) == residue_letter(moving_residues[j]) for i, j in pairs)
    reference_atoms = []
    moving_atoms = []
    unresolved_pairs = []
    for reference_index, moving_index in pairs:
        reference_residue = reference_residues[reference_index]
        moving_residue = moving_residues[moving_index]
        if "CA" not in reference_residue or "CA" not in moving_residue:
            unresolved_pairs.append({
                "reference_residue": list(reference_residue.id),
                "moving_residue": list(moving_residue.id),
            })
            continue
        reference_atoms.append(reference_residue["CA"])
        moving_atoms.append(moving_residue["CA"])
    aligned_count = len(pairs)
    report = {
        "reference_chain": reference_chain.id,
        "moving_chain": moving_chain.id,
        "reference_amino_acid_residues": len(reference_residues),
        "moving_amino_acid_residues": len(moving_residues),
        "aligned_sequence_positions": aligned_count,
        "identical_sequence_positions": exact,
        "sequence_identity": exact / aligned_count if aligned_count else 0.0,
        "reference_sequence_coverage": aligned_count / len(reference_residues),
        "moving_sequence_coverage": aligned_count / len(moving_residues),
        "matched_ca_atoms": len(reference_atoms),
        "unresolved_aligned_pairs": unresolved_pairs,
        "alignment_score": alignment_score,
        "alignment_parameters": {"match": 2.0, "mismatch": -1.0, "open_gap": -10.0, "extend_gap": -0.5},
    }
    return report, reference_atoms, moving_atoms


def determinant(matrix) -> float:
    a, b, c = [[float(value) for value in row] for row in matrix]
    return a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])


def transformed_rmsd(reference_atoms: list[Any], moving_atoms: list[Any], rotation, translation) -> float:
    squared = []
    for reference_atom, moving_atom in zip(reference_atoms, moving_atoms, strict=True):
        transformed = moving_atom.coord @ rotation + translation
        difference = reference_atom.coord - transformed
        squared.append(float(difference @ difference))
    return math.sqrt(sum(squared) / len(squared))


def write_structure(structure, structure_format: str, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise ValueError(f"refusing to overwrite coordinate output: {path}")
    suffix = ".pdb" if structure_format == "pdb" else ".cif"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=suffix, dir=path.parent)
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        writer = PDBIO() if structure_format == "pdb" else MMCIFIO()
        writer.set_structure(structure)
        writer.save(str(temporary_path))
        if temporary_path.stat().st_size == 0:
            raise ValueError("coordinate writer produced an empty structure")
        output_digest = hashlib.sha256(temporary_path.read_bytes()).hexdigest()
        os.replace(temporary_path, path)
        return output_digest
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise ValueError(f"refusing to overwrite report output: {path}")
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary_name, path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def build_report(args: argparse.Namespace) -> tuple[dict[str, Any], Any]:
    if args.minimum_aligned_residues < 3:
        raise ValueError("minimum aligned residues must be at least three")
    reference_path, reference_digest = stable_file(args.reference)
    moving_path, moving_digest = stable_file(args.moving)
    if reference_digest == moving_digest:
        raise ValueError("reference and moving inputs are byte-identical")
    reference_structure = parse_structure(reference_path, args.format, "reference")
    moving_structure = parse_structure(moving_path, args.format, "moving")
    reference_models, reference_model = get_model(reference_structure, args.reference_model_index, "reference")
    moving_models, moving_model = get_model(moving_structure, args.moving_model_index, "moving")
    chain_map = parse_chain_map(args.chain_map)
    reference_chains = {chain.id: chain for chain in reference_model}
    moving_chains = {chain.id: chain for chain in moving_model}
    missing_reference = sorted({pair[0] for pair in chain_map} - set(reference_chains))
    missing_moving = sorted({pair[1] for pair in chain_map} - set(moving_chains))
    if missing_reference or missing_moving:
        raise ValueError(f"mapped chains are absent; reference={missing_reference}, moving={missing_moving}")
    pair_reports = []
    reference_atoms = []
    moving_atoms = []
    for reference_id, moving_id in chain_map:
        pair_report, pair_reference_atoms, pair_moving_atoms = inspect_chain_pair(reference_chains[reference_id], moving_chains[moving_id])
        pair_reports.append(pair_report)
        reference_atoms.extend(pair_reference_atoms)
        moving_atoms.extend(pair_moving_atoms)
    if len(reference_atoms) < args.minimum_aligned_residues:
        raise ValueError(f"only {len(reference_atoms)} matched C-alpha atoms remain; minimum is {args.minimum_aligned_residues}")
    superimposer = Superimposer()
    superimposer.set_atoms(reference_atoms, moving_atoms)
    rotation, translation = superimposer.rotran
    independent_rmsd = transformed_rmsd(reference_atoms, moving_atoms, rotation, translation)
    if not math.isfinite(independent_rmsd) or abs(independent_rmsd - float(superimposer.rms)) > 1e-6:
        raise ValueError("superposition RMSD failed independent recomputation")
    rotation_determinant = determinant(rotation)
    if abs(rotation_determinant - 1.0) > 1e-5:
        raise ValueError("superposition rotation is not a proper rigid-body rotation")
    superimposer.apply(list(moving_model.get_atoms()))
    report = {
        "schema_version": 1,
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "inputs": {
            "reference_sha256": reference_digest,
            "moving_sha256": moving_digest,
            "format": args.format,
            "reference_model_index": args.reference_model_index,
            "moving_model_index": args.moving_model_index,
            "reference_model_count": len(reference_models),
            "moving_model_count": len(moving_models),
        },
        "chain_map": [{"reference": reference, "moving": moving} for reference, moving in chain_map],
        "chain_results": pair_reports,
        "superposition": {
            "matched_ca_atoms": len(reference_atoms),
            "rmsd_angstrom": independent_rmsd,
            "rotation": [[float(value) for value in row] for row in rotation],
            "translation": [float(value) for value in translation],
            "rotation_determinant": rotation_determinant,
        },
        "tm_score": {"status": "not_computed", "value": None, "reason": "No independently validated TM-align backend was executed; RMSD is not converted into a pseudo TM-score."},
        "quality_status": "passed",
        "versions": {"python": platform.python_version(), "biopython": version("biopython")},
        "interpretation_boundary": "Sequence-aware RMSD and coverage do not establish biological equivalence, conformational-state relevance, dynamics, or functional conservation.",
    }
    return report, moving_model


def main() -> int:
    args = parse_args()
    report, transformed_structure = build_report(args)
    report["superposed_coordinates"] = {
        "format": args.format,
        "sha256": write_structure(transformed_structure, args.format, args.coordinate_output),
    }
    report["result_digest"] = hashlib.sha256(json.dumps(report, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    atomic_json(args.report_output, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
