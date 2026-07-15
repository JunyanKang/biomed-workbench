#!/usr/bin/env python3
"""Assess PDB or mmCIF coordinate quality with explicit confidence semantics."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import tempfile
from importlib.metadata import version
from pathlib import Path
from statistics import fmean, median
from typing import Any

from Bio.PDB import MMCIFParser, PDBParser, is_aa


MODULE_ID = "structure-quality-assessment"
MODULE_VERSION = "1.0.0"
BACKBONE_ATOMS = frozenset({"N", "CA", "C", "O"})
CONFIDENCE_SEMANTICS = frozenset({"experimental-b-factor", "alphafold-plddt", "unknown"})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--format", required=True, choices=("pdb", "mmcif"))
    parser.add_argument("--confidence-semantics", required=True, choices=sorted(CONFIDENCE_SEMANTICS))
    parser.add_argument("--model-index", required=True, type=int)
    parser.add_argument("--chains", required=True, help="Comma-separated chain identifiers")
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--residue-output", required=True, type=Path)
    return parser.parse_args()


def stable_input(path: Path) -> tuple[Path, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("input must be a stable regular coordinate file")
    data = path.read_bytes()
    if not data:
        raise ValueError("coordinate input is empty")
    return path.resolve(), hashlib.sha256(data).hexdigest()


def load_structure(path: Path, structure_format: str):
    parser = PDBParser(QUIET=True) if structure_format == "pdb" else MMCIFParser(QUIET=True)
    try:
        return parser.get_structure("input", str(path))
    except Exception as exc:
        raise ValueError(f"coordinate parser rejected the declared {structure_format} input") from exc


def selected_model_and_chains(structure, model_index: int, requested: list[str]):
    models = list(structure.get_models())
    if model_index < 0 or model_index >= len(models):
        raise ValueError(f"model index {model_index} is absent; observed model count is {len(models)}")
    if not requested or len(requested) != len(set(requested)):
        raise ValueError("one or more unique chain identifiers are required")
    model = models[model_index]
    observed = {chain.id: chain for chain in model}
    missing = sorted(set(requested) - set(observed))
    if missing:
        raise ValueError(f"requested chains are absent from model {model_index}: {', '.join(missing)}")
    return models, model, [observed[name] for name in requested], sorted(observed)


def confidence_class(value: float) -> str:
    if value < 50:
        return "very_low"
    if value < 70:
        return "low"
    if value < 90:
        return "confident"
    return "very_high"


def inspect_residue(chain_id: str, residue, confidence_semantics: str) -> dict[str, Any]:
    atoms = list(residue.get_atoms())
    coordinates = [float(component) for atom in atoms for component in atom.coord]
    if any(not math.isfinite(value) for value in coordinates):
        raise ValueError(f"non-finite coordinates occur at chain {chain_id} residue {residue.id}")
    occupancies = [float(atom.occupancy) for atom in atoms if atom.occupancy is not None]
    b_values = [float(atom.bfactor) for atom in atoms if atom.bfactor is not None]
    if any(not math.isfinite(value) for value in occupancies + b_values):
        raise ValueError(f"non-finite occupancy or B value occurs at chain {chain_id} residue {residue.id}")
    residue_mean_b = fmean(b_values) if b_values else None
    is_protein = bool(is_aa(residue, standard=False))
    observed_atom_names = {atom.get_name().strip() for atom in atoms}
    missing_backbone = sorted(BACKBONE_ATOMS - observed_atom_names) if is_protein else []
    hetero_flag, residue_number, insertion_code = residue.id
    return {
        "chain_id": chain_id,
        "hetero_flag": str(hetero_flag).strip(),
        "residue_number": int(residue_number),
        "insertion_code": str(insertion_code).strip(),
        "residue_name": residue.resname.strip(),
        "is_amino_acid": is_protein,
        "atom_count": len(atoms),
        "alternate_location_atom_count": sum(bool(atom.is_disordered()) for atom in atoms),
        "missing_occupancy_count": sum(atom.occupancy is None for atom in atoms),
        "occupancy_out_of_range_count": sum(value < 0 or value > 1 for value in occupancies),
        "mean_occupancy": fmean(occupancies) if occupancies else None,
        "mean_b_or_confidence": residue_mean_b,
        "confidence_class": confidence_class(residue_mean_b) if confidence_semantics == "alphafold-plddt" and residue_mean_b is not None else None,
        "missing_backbone_atoms": missing_backbone,
    }


def summarize(rows: list[dict[str, Any]], confidence_semantics: str) -> dict[str, Any]:
    atom_count = sum(row["atom_count"] for row in rows)
    b_values = [row["mean_b_or_confidence"] for row in rows if row["mean_b_or_confidence"] is not None]
    summary = {
        "residue_count": len(rows),
        "amino_acid_residue_count": sum(row["is_amino_acid"] for row in rows),
        "hetero_residue_count": sum(not row["is_amino_acid"] for row in rows),
        "atom_count": atom_count,
        "alternate_location_atom_count": sum(row["alternate_location_atom_count"] for row in rows),
        "missing_occupancy_atom_count": sum(row["missing_occupancy_count"] for row in rows),
        "occupancy_out_of_range_atom_count": sum(row["occupancy_out_of_range_count"] for row in rows),
        "residues_missing_backbone": sum(bool(row["missing_backbone_atoms"]) for row in rows),
        "mean_residue_b_or_confidence": fmean(b_values) if b_values else None,
        "median_residue_b_or_confidence": median(b_values) if b_values else None,
        "confidence_semantics": confidence_semantics,
        "plddt_class_counts": None,
    }
    if confidence_semantics == "alphafold-plddt":
        outside = [value for value in b_values if value < 0 or value > 100]
        if outside:
            raise ValueError("declared AlphaFold pLDDT values must remain within 0 through 100")
        summary["plddt_class_counts"] = {
            name: sum(row["confidence_class"] == name for row in rows)
            for name in ("very_low", "low", "confident", "very_high")
        }
    return summary


def atomic_write_text(path: Path, text: str) -> None:
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


def encode_residue_table(rows: list[dict[str, Any]]) -> str:
    fields = list(rows[0])
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for row in rows:
            encoded = dict(row)
            encoded["missing_backbone_atoms"] = ",".join(row["missing_backbone_atoms"])
            writer.writerow(encoded)
        handle.seek(0)
        return handle.read()


def build_report(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    input_path, input_digest = stable_input(args.input)
    structure = load_structure(input_path, args.format)
    requested_chains = [value.strip() for value in args.chains.split(",") if value.strip()]
    models, model, chains, observed_chains = selected_model_and_chains(structure, args.model_index, requested_chains)
    rows = [inspect_residue(chain.id, residue, args.confidence_semantics) for chain in chains for residue in chain]
    if not rows:
        raise ValueError("selected model and chains contain no residues")
    summary = summarize(rows, args.confidence_semantics)
    warnings = []
    if args.confidence_semantics == "unknown":
        warnings.append("B-value semantics are unknown; no pLDDT or experimental-displacement interpretation is admitted.")
    if summary["residues_missing_backbone"]:
        warnings.append("One or more amino-acid residues lack at least one N, CA, C, or O atom.")
    residue_text = encode_residue_table(rows)
    residue_digest = hashlib.sha256(residue_text.encode("utf-8")).hexdigest()
    report = {
        "schema_version": 1,
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "input": {"sha256": input_digest, "format": args.format, "model_index": args.model_index, "selected_chains": requested_chains},
        "observed": {"model_count": len(models), "all_chain_ids_in_selected_model": observed_chains},
        "summary": summary,
        "warnings": warnings,
        "quality_status": "passed_with_warnings" if warnings else "passed",
        "residue_table": {"row_count": len(rows), "sha256": residue_digest},
        "versions": {"python": platform.python_version(), "biopython": version("biopython")},
        "interpretation_boundary": "Coordinate quality and confidence context do not establish biological state, function, dynamics, interfaces, or experimental validity.",
    }
    report["result_digest"] = hashlib.sha256(json.dumps(report, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return report, residue_text


def main() -> int:
    args = parse_args()
    report, residue_text = build_report(args)
    atomic_write_text(args.residue_output, residue_text)
    atomic_write_text(args.json_output, json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
