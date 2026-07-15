#!/usr/bin/env python3
"""Review every DiffDock-style SDF pose without treating confidence as affinity."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import platform
import re
import tempfile
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

from rdkit import Chem
from rdkit.Chem import rdMolAlign


MODULE_ID = "docking-pose-review"
MODULE_VERSION = "1.0.0"
POSE_NAME_RE = re.compile(r"^rank(?P<rank>[1-9][0-9]*)(?:_confidence(?P<confidence>[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)))?\.sdf$", re.IGNORECASE)


@dataclass
class PoseRecord:
    relative_path: str
    sha256: str
    rank: int | None
    confidence: float | None
    molecule: Any | None
    error: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receptor", required=True, type=Path)
    parser.add_argument("--results-directory", required=True, type=Path)
    parser.add_argument("--diffdock-version", required=True)
    parser.add_argument("--ligand-smiles", required=True)
    parser.add_argument("--severe-clash-distance", required=True, type=float)
    parser.add_argument("--contact-distance", required=True, type=float)
    parser.add_argument("--report-output", required=True, type=Path)
    parser.add_argument("--pose-output", required=True, type=Path)
    return parser.parse_args()


def stable_file(path: Path, label: str) -> tuple[Path, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a stable regular file")
    content = path.read_bytes()
    if not content:
        raise ValueError(f"{label} is empty")
    return path.resolve(), hashlib.sha256(content).hexdigest()


def load_receptor(path: Path):
    molecule = Chem.MolFromPDBFile(str(path), sanitize=False, removeHs=False, proximityBonding=False)
    if molecule is None or molecule.GetNumConformers() != 1:
        raise ValueError("receptor PDB could not be parsed into one coordinate conformer")
    conformer = molecule.GetConformer()
    coordinates = []
    for atom in molecule.GetAtoms():
        if atom.GetAtomicNum() <= 1:
            continue
        position = conformer.GetAtomPosition(atom.GetIdx())
        xyz = (float(position.x), float(position.y), float(position.z))
        if not all(math.isfinite(value) for value in xyz):
            raise ValueError("receptor contains non-finite heavy-atom coordinates")
        coordinates.append(xyz)
    if not coordinates:
        raise ValueError("receptor contains no heavy-atom coordinates")
    return molecule, coordinates


def expected_ligand(smiles: str) -> tuple[Any, str]:
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise ValueError("declared ligand identity is not a valid SMILES molecule")
    Chem.AssignStereochemistry(molecule, cleanIt=True, force=True)
    canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    return molecule, canonical


def load_pose(path: Path, root: Path) -> PoseRecord:
    _stable_path, digest = stable_file(path, "pose SDF")
    relative = path.relative_to(root).as_posix()
    match = POSE_NAME_RE.fullmatch(path.name)
    rank = int(match.group("rank")) if match else None
    confidence = float(match.group("confidence")) if match and match.group("confidence") is not None else None
    supplier = Chem.SDMolSupplier(str(path), sanitize=False, removeHs=False, strictParsing=True)
    molecules = list(supplier)
    if len(molecules) != 1:
        return PoseRecord(relative, digest, rank, confidence, None, f"expected_one_sdf_record_observed_{len(molecules)}")
    molecule = molecules[0]
    if molecule is None:
        return PoseRecord(relative, digest, rank, confidence, None, "sdf_parse_failed")
    try:
        Chem.SanitizeMol(molecule)
        Chem.AssignStereochemistry(molecule, cleanIt=True, force=True)
    except Exception as exc:
        return PoseRecord(relative, digest, rank, confidence, None, f"sanitization_failed:{type(exc).__name__}")
    if molecule.GetNumConformers() != 1 or not molecule.GetConformer().Is3D():
        return PoseRecord(relative, digest, rank, confidence, None, "missing_single_3d_conformer")
    return PoseRecord(relative, digest, rank, confidence, molecule, None)


def discover_poses(root: Path) -> list[PoseRecord]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("results directory must be a stable directory")
    paths = sorted(path for path in root.rglob("*.sdf") if path.is_file() and not path.is_symlink())
    if not paths:
        raise ValueError("results directory contains no stable SDF pose files")
    if len(paths) > 500:
        raise ValueError("pose collection exceeds the bounded 500-file review limit")
    records = [load_pose(path, root) for path in paths]
    ranks = [record.rank for record in records if record.rank is not None]
    duplicates = sorted({rank for rank in ranks if ranks.count(rank) > 1})
    if duplicates:
        raise ValueError(f"duplicate pose ranks are present: {duplicates[:20]}")
    return records


def ligand_coordinates(molecule) -> list[tuple[int, tuple[float, float, float]]]:
    conformer = molecule.GetConformer()
    coordinates = []
    for atom in molecule.GetAtoms():
        if atom.GetAtomicNum() <= 1:
            continue
        position = conformer.GetAtomPosition(atom.GetIdx())
        xyz = (float(position.x), float(position.y), float(position.z))
        if not all(math.isfinite(value) for value in xyz):
            raise ValueError("pose contains non-finite heavy-atom coordinates")
        coordinates.append((atom.GetIdx(), xyz))
    if not coordinates:
        raise ValueError("pose contains no heavy atoms")
    return coordinates


def distance_summary(ligand_coordinates_value, receptor_coordinates, severe_distance: float, contact_distance: float) -> dict[str, Any]:
    minimum_distance = math.inf
    severe_atoms = 0
    contact_atoms = 0
    severe_squared = severe_distance * severe_distance
    contact_squared = contact_distance * contact_distance
    for _atom_index, ligand_xyz in ligand_coordinates_value:
        atom_minimum_squared = math.inf
        for receptor_xyz in receptor_coordinates:
            squared = sum((ligand_xyz[index] - receptor_xyz[index]) ** 2 for index in range(3))
            atom_minimum_squared = min(atom_minimum_squared, squared)
        minimum_distance = min(minimum_distance, math.sqrt(atom_minimum_squared))
        severe_atoms += atom_minimum_squared < severe_squared
        contact_atoms += atom_minimum_squared < contact_squared
    return {
        "minimum_receptor_distance_angstrom": minimum_distance,
        "ligand_heavy_atoms_with_severe_clash": severe_atoms,
        "ligand_heavy_atoms_with_close_contact": contact_atoms,
        "severe_clash_fraction": severe_atoms / len(ligand_coordinates_value),
        "close_contact_fraction": contact_atoms / len(ligand_coordinates_value),
    }


def rmsd_to_reference(molecule, reference) -> float | None:
    if reference is None or molecule.GetNumAtoms() != reference.GetNumAtoms():
        return None
    molecule_identity = Chem.MolToSmiles(Chem.RemoveHs(molecule), canonical=True, isomericSmiles=True)
    reference_identity = Chem.MolToSmiles(Chem.RemoveHs(reference), canonical=True, isomericSmiles=True)
    if molecule_identity != reference_identity:
        return None
    try:
        return float(rdMolAlign.GetBestRMS(Chem.Mol(molecule), Chem.Mol(reference)))
    except Exception:
        return None


def inspect_pose(record: PoseRecord, expected_canonical: str, receptor_coordinates, severe_distance: float, contact_distance: float, top_pose) -> dict[str, Any]:
    row: dict[str, Any] = {
        "relative_path": record.relative_path,
        "sha256": record.sha256,
        "rank": record.rank,
        "confidence": record.confidence,
        "status": "invalid",
        "reason": record.error,
        "canonical_isomeric_smiles": None,
        "identity_matches_declared_ligand": False,
        "heavy_atom_count": None,
        "fragment_count": None,
        "formal_charge": None,
        "minimum_receptor_distance_angstrom": None,
        "ligand_heavy_atoms_with_severe_clash": None,
        "ligand_heavy_atoms_with_close_contact": None,
        "severe_clash_fraction": None,
        "close_contact_fraction": None,
        "rmsd_to_top_pose_angstrom": None,
    }
    if record.rank is None:
        row["reason"] = "unrecognized_pose_filename"
        return row
    if record.molecule is None:
        return row
    molecule = record.molecule
    canonical = Chem.MolToSmiles(Chem.RemoveHs(molecule), canonical=True, isomericSmiles=True)
    row["canonical_isomeric_smiles"] = canonical
    row["identity_matches_declared_ligand"] = canonical == expected_canonical
    row["heavy_atom_count"] = molecule.GetNumHeavyAtoms()
    row["fragment_count"] = len(Chem.GetMolFrags(molecule))
    row["formal_charge"] = Chem.GetFormalCharge(molecule)
    if not row["identity_matches_declared_ligand"]:
        row["reason"] = "ligand_identity_mismatch"
        return row
    try:
        geometry = distance_summary(ligand_coordinates(molecule), receptor_coordinates, severe_distance, contact_distance)
    except ValueError as exc:
        row["reason"] = str(exc)
        return row
    row.update(geometry)
    row["rmsd_to_top_pose_angstrom"] = rmsd_to_reference(molecule, top_pose)
    row["status"] = "reviewable"
    row["reason"] = "passed_identity_and_coordinate_checks"
    return row


def encode_table(rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), delimiter="\t")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise ValueError(f"refusing to overwrite output: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(temporary_name, path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def build_report(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    if not math.isfinite(args.severe_clash_distance) or not math.isfinite(args.contact_distance):
        raise ValueError("distance thresholds must be finite")
    if args.severe_clash_distance <= 0 or args.contact_distance <= args.severe_clash_distance:
        raise ValueError("contact distance must be greater than a positive severe-clash distance")
    receptor_path, receptor_digest = stable_file(args.receptor, "receptor PDB")
    _receptor, receptor_coordinates = load_receptor(receptor_path)
    _expected_molecule, expected_canonical = expected_ligand(args.ligand_smiles)
    if args.results_directory.is_symlink() or not args.results_directory.is_dir():
        raise ValueError("results directory must be a stable directory")
    records = discover_poses(args.results_directory.resolve())
    ordered_valid = sorted((record for record in records if record.molecule is not None and record.rank is not None), key=lambda item: item.rank)
    top_pose = ordered_valid[0].molecule if ordered_valid else None
    rows = [inspect_pose(record, expected_canonical, receptor_coordinates, args.severe_clash_distance, args.contact_distance, top_pose) for record in records]
    if len(rows) != len(records) or len({row["relative_path"] for row in rows}) != len(rows):
        raise ValueError("pose accounting failed")
    table = encode_table(rows)
    reviewable = [row for row in rows if row["status"] == "reviewable"]
    report = {
        "schema_version": 1,
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "inputs": {
            "receptor_sha256": receptor_digest,
            "receptor_heavy_atom_count": len(receptor_coordinates),
            "declared_ligand_canonical_isomeric_smiles": expected_canonical,
            "diffdock_version": args.diffdock_version,
        },
        "parameters": {"severe_clash_distance_angstrom": args.severe_clash_distance, "contact_distance_angstrom": args.contact_distance},
        "summary": {
            "observed_pose_file_count": len(rows),
            "reviewable_pose_count": len(reviewable),
            "invalid_pose_count": len(rows) - len(reviewable),
            "reviewable_poses_with_severe_clashes": sum(row["ligand_heavy_atoms_with_severe_clash"] > 0 for row in reviewable),
            "confidence_present_count": sum(row["confidence"] is not None for row in rows),
        },
        "pose_output": {"row_count": len(rows), "sha256": hashlib.sha256(table.encode()).hexdigest()},
        "quality_status": "passed_with_invalid_poses" if len(reviewable) != len(rows) else "passed",
        "versions": {"python": platform.python_version(), "rdkit": version("rdkit")},
        "score_semantics": "DiffDock confidence is retained as producer-specific pose-ranking evidence and is not affinity, free energy, kinetics, or experimental binding.",
        "interpretation_boundary": "A chemically reviewable, unclashed pose remains a computational hypothesis requiring preparation review, alternative-state analysis, orthogonal scoring, and experimental validation.",
    }
    if report["summary"]["reviewable_pose_count"] + report["summary"]["invalid_pose_count"] != report["summary"]["observed_pose_file_count"]:
        raise ValueError("pose summary counts do not reconcile")
    report["result_digest"] = hashlib.sha256(json.dumps(report, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return report, table


def main() -> int:
    args = parse_args()
    report, table = build_report(args)
    atomic_write(args.pose_output, table)
    atomic_write(args.report_output, json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
