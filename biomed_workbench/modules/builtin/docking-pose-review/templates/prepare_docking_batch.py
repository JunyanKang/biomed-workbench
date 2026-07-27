#!/usr/bin/env python3
"""Validate and serialize a bounded DiffDock batch without running DiffDock."""

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
from importlib.metadata import version
from pathlib import Path
from typing import Any

from Bio.PDB import PDBParser
from rdkit import Chem


MODULE_ID = "docking-pose-review"
MODULE_VERSION = "1.0.0"
COMPATIBILITY_ROW_ID = "structure-analysis-2026-07-15-docking-pose-review"
REQUIRED_COLUMNS = ("complex_name", "protein_path", "ligand_description", "protein_sequence")
COMPLEX_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PROTEIN_ALPHABET = frozenset("ACDEFGHIKLMNPQRSTVWYX")
MAX_ROWS = 2_000
MAX_SEQUENCE_LENGTH = 20_000

CONFIG_RULES: dict[str, tuple[str, Any]] = {
    "old_score_model": ("bool", None),
    "old_filtering_model": ("bool", None),
    "inference_steps": ("int", (1, 100)),
    "actual_steps": ("int", (1, 100)),
    "no_final_step_noise": ("bool", None),
    "samples_per_complex": ("int", (1, 100)),
    "sigma_schedule": ("enum", {"expbeta"}),
    "initial_noise_std_proportion": ("float", (0.01, 10.0)),
    "temp_sampling_tr": ("float", (0.01, 20.0)),
    "temp_sampling_rot": ("float", (0.01, 20.0)),
    "temp_sampling_tor": ("float", (0.01, 20.0)),
    "temp_psi_tr": ("float", (0.01, 20.0)),
    "temp_psi_rot": ("float", (0.01, 20.0)),
    "temp_psi_tor": ("float", (0.01, 20.0)),
    "temp_sigma_data_tr": ("float", (0.01, 20.0)),
    "temp_sigma_data_rot": ("float", (0.01, 20.0)),
    "temp_sigma_data_tor": ("float", (0.01, 20.0)),
    "no_random": ("bool", None),
    "ode": ("bool", None),
    "different_schedules": ("bool", None),
    "limit_failures": ("int", (0, 100)),
}
REQUIRED_CONFIG = {
    "old_score_model",
    "old_filtering_model",
    "inference_steps",
    "actual_steps",
    "no_final_step_noise",
    "samples_per_complex",
    "sigma_schedule",
    "limit_failures",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--base-directory", required=True, type=Path)
    parser.add_argument("--config-json", required=True, type=Path)
    parser.add_argument("--batch-output", required=True, type=Path)
    parser.add_argument("--config-output", required=True, type=Path)
    parser.add_argument("--report-output", required=True, type=Path)
    return parser.parse_args()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def stable_file(path: Path, label: str) -> tuple[Path, bytes, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a stable regular file")
    content = path.read_bytes()
    if not content:
        raise ValueError(f"{label} is empty")
    return path.resolve(), content, sha256_bytes(content)


def stable_base(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise ValueError("base directory must be a stable directory")
    return path.resolve()


def resolve_input(raw: str, base: Path, label: str, suffix: str) -> tuple[Path, bytes, str, str]:
    candidate = Path(raw)
    candidate = candidate if candidate.is_absolute() else base / candidate
    resolved, content, digest = stable_file(candidate, label)
    try:
        relative = resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"{label} escapes the declared base directory") from exc
    if resolved.suffix.lower() != suffix:
        raise ValueError(f"{label} must use the {suffix} suffix")
    return resolved, content, digest, relative.as_posix()


def inspect_pdb(path: Path) -> dict[str, Any]:
    structure = PDBParser(QUIET=True, PERMISSIVE=False).get_structure("protein", str(path))
    model_count = chain_count = residue_count = atom_count = 0
    for model in structure:
        model_count += 1
        for chain in model:
            chain_count += 1
            for residue in chain:
                residue_count += 1
                for atom in residue:
                    coordinates = tuple(float(value) for value in atom.coord)
                    if not all(math.isfinite(value) for value in coordinates):
                        raise ValueError("protein PDB contains non-finite coordinates")
                    atom_count += 1
    if not model_count or not chain_count or not residue_count or not atom_count:
        raise ValueError("protein PDB contains no usable coordinate hierarchy")
    return {"model_count": model_count, "chain_count": chain_count, "residue_count": residue_count, "atom_count": atom_count}


def inspect_sequence(raw: str) -> tuple[str, dict[str, Any]]:
    sequence = re.sub(r"\s+", "", raw).upper()
    if not sequence or len(sequence) > MAX_SEQUENCE_LENGTH:
        raise ValueError(f"protein sequence length must be between 1 and {MAX_SEQUENCE_LENGTH}")
    invalid = sorted(set(sequence) - PROTEIN_ALPHABET)
    if invalid:
        raise ValueError(f"protein sequence contains unsupported residue codes: {''.join(invalid)}")
    return sequence, {
        "length": len(sequence),
        "ambiguous_x_count": sequence.count("X"),
        "sha256": sha256_bytes(sequence.encode("ascii")),
    }


def inspect_sdf(path: Path) -> dict[str, Any]:
    supplier = Chem.SDMolSupplier(str(path), sanitize=False, removeHs=False, strictParsing=True)
    molecules = list(supplier)
    if len(molecules) != 1 or molecules[0] is None:
        raise ValueError("ligand SDF must contain exactly one parseable molecule")
    molecule = molecules[0]
    Chem.SanitizeMol(molecule)
    Chem.AssignStereochemistry(molecule, cleanIt=True, force=True)
    return {
        "canonical_isomeric_smiles": Chem.MolToSmiles(Chem.RemoveHs(molecule), canonical=True, isomericSmiles=True),
        "heavy_atom_count": molecule.GetNumHeavyAtoms(),
        "fragment_count": len(Chem.GetMolFrags(molecule)),
        "formal_charge": Chem.GetFormalCharge(molecule),
        "conformer_count": molecule.GetNumConformers(),
    }


def inspect_smiles(raw: str) -> tuple[str, dict[str, Any]]:
    molecule = Chem.MolFromSmiles(raw)
    if molecule is None:
        raise ValueError("ligand_description is neither an existing in-boundary SDF nor valid SMILES")
    Chem.AssignStereochemistry(molecule, cleanIt=True, force=True)
    canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    return canonical, {
        "canonical_isomeric_smiles": canonical,
        "heavy_atom_count": molecule.GetNumHeavyAtoms(),
        "fragment_count": len(Chem.GetMolFrags(molecule)),
        "formal_charge": Chem.GetFormalCharge(molecule),
    }


def load_manifest(path: Path, base: Path) -> tuple[list[dict[str, str]], list[dict[str, Any]], str]:
    _resolved, content, digest, _relative = resolve_input(str(path), base, "batch manifest", ".csv")
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != REQUIRED_COLUMNS:
        raise ValueError(f"batch manifest columns and order must be exactly {list(REQUIRED_COLUMNS)}")
    source_rows = list(reader)
    if not source_rows or len(source_rows) > MAX_ROWS:
        raise ValueError(f"batch manifest must contain between 1 and {MAX_ROWS} rows")
    names: set[str] = set()
    normalized_rows: list[dict[str, str]] = []
    records: list[dict[str, Any]] = []
    for row_number, source in enumerate(source_rows, start=2):
        row = {name: (source.get(name) or "").strip() for name in REQUIRED_COLUMNS}
        name = row["complex_name"]
        if not COMPLEX_NAME_RE.fullmatch(name):
            raise ValueError(f"row {row_number} has an unsafe or empty complex_name")
        if name in names:
            raise ValueError(f"row {row_number} duplicates complex_name {name!r}")
        names.add(name)
        has_path = bool(row["protein_path"])
        has_sequence = bool(row["protein_sequence"])
        if has_path == has_sequence:
            raise ValueError(f"row {row_number} must provide exactly one of protein_path or protein_sequence")
        protein: dict[str, Any]
        if has_path:
            protein_path, _content, protein_digest, relative = resolve_input(row["protein_path"], base, f"row {row_number} protein PDB", ".pdb")
            protein = {"kind": "pdb", "relative_path": relative, "sha256": protein_digest, **inspect_pdb(protein_path)}
            row["protein_path"] = relative
            row["protein_sequence"] = ""
        else:
            sequence, sequence_summary = inspect_sequence(row["protein_sequence"])
            protein = {"kind": "sequence", **sequence_summary}
            row["protein_path"] = ""
            row["protein_sequence"] = sequence
        ligand_raw = row["ligand_description"]
        if not ligand_raw:
            raise ValueError(f"row {row_number} has an empty ligand_description")
        ligand_candidate = Path(ligand_raw)
        ligand_candidate = ligand_candidate if ligand_candidate.is_absolute() else base / ligand_candidate
        if ligand_candidate.exists() or ligand_raw.lower().endswith(".sdf"):
            ligand_path, _content, ligand_digest, relative = resolve_input(ligand_raw, base, f"row {row_number} ligand SDF", ".sdf")
            ligand = {"kind": "sdf", "relative_path": relative, "sha256": ligand_digest, **inspect_sdf(ligand_path)}
            row["ligand_description"] = relative
        else:
            canonical, ligand_summary = inspect_smiles(ligand_raw)
            ligand = {"kind": "smiles", "sha256": sha256_bytes(canonical.encode("utf-8")), **ligand_summary}
            row["ligand_description"] = canonical
        normalized_rows.append(row)
        records.append({"row_number": row_number, "complex_name": name, "status": "validated", "protein": protein, "ligand": ligand})
    return normalized_rows, records, digest


def validate_config(path: Path, base: Path) -> tuple[dict[str, Any], str]:
    _resolved, content, digest, _relative = resolve_input(str(path), base, "inference configuration JSON", ".json")
    try:
        config = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("inference configuration must be valid JSON") from exc
    if not isinstance(config, dict):
        raise ValueError("inference configuration must be a JSON object")
    unknown = sorted(set(config) - set(CONFIG_RULES))
    missing = sorted(REQUIRED_CONFIG - set(config))
    if unknown or missing:
        raise ValueError(f"inference configuration schema mismatch; unknown={unknown}, missing={missing}")
    validated: dict[str, Any] = {}
    for name, value in config.items():
        kind, rule = CONFIG_RULES[name]
        if kind == "bool":
            if type(value) is not bool:
                raise ValueError(f"configuration field {name} must be boolean")
        elif kind == "int":
            if type(value) is not int or not rule[0] <= value <= rule[1]:
                raise ValueError(f"configuration field {name} must be an integer in {rule}")
        elif kind == "float":
            if type(value) not in {int, float} or type(value) is bool or not math.isfinite(float(value)) or not rule[0] <= float(value) <= rule[1]:
                raise ValueError(f"configuration field {name} must be finite and in {rule}")
            value = float(value)
        elif kind == "enum" and value not in rule:
            raise ValueError(f"configuration field {name} must be one of {sorted(rule)}")
        validated[name] = value
    if validated["actual_steps"] > validated["inference_steps"]:
        raise ValueError("actual_steps may not exceed inference_steps")
    return {name: validated[name] for name in CONFIG_RULES if name in validated}, digest


def encode_csv(rows: list[dict[str, str]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(REQUIRED_COLUMNS), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def yaml_scalar(value: Any) -> str:
    if type(value) is bool:
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    return str(value)


def encode_yaml(config: dict[str, Any]) -> str:
    return "# Validated DiffDock inference parameters; paths and runtime resources are intentionally absent.\n" + "".join(
        f"{name}: {yaml_scalar(value)}\n" for name, value in config.items()
    )


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


def build(args: argparse.Namespace) -> tuple[str, str, dict[str, Any]]:
    base = stable_base(args.base_directory)
    rows, records, manifest_digest = load_manifest(args.manifest, base)
    config, config_digest = validate_config(args.config_json, base)
    batch_text = encode_csv(rows)
    config_text = encode_yaml(config)
    report = {
        "schema_version": 1,
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "compatibility_row_id": COMPATIBILITY_ROW_ID,
        "input": {
            "manifest_name": args.manifest.name,
            "manifest_sha256": manifest_digest,
            "config_name": args.config_json.name,
            "config_sha256": config_digest,
        },
        "summary": {
            "input_row_count": len(records),
            "validated_row_count": len(records),
            "path_protein_count": sum(record["protein"]["kind"] == "pdb" for record in records),
            "sequence_protein_count": sum(record["protein"]["kind"] == "sequence" for record in records),
            "sdf_ligand_count": sum(record["ligand"]["kind"] == "sdf" for record in records),
            "smiles_ligand_count": sum(record["ligand"]["kind"] == "smiles" for record in records),
        },
        "records": records,
        "validated_config": config,
        "versions": {
            "python": platform.python_version(),
            "biopython": version("biopython"),
            "rdkit": version("rdkit"),
        },
        "outputs": {
            "batch_sha256": sha256_bytes(batch_text.encode("utf-8")),
            "config_sha256": sha256_bytes(config_text.encode("utf-8")),
        },
        "quality_gates": {
            "exact_four_column_contract": True,
            "all_rows_accounted": True,
            "protein_source_exclusive": True,
            "files_confined_to_base_directory": True,
            "protein_and_ligand_parsed": True,
            "configuration_closed_and_bounded": True,
        },
        "execution_boundary": "This preparation validates scientific inputs and inference parameters; it does not run DiffDock or manage dependency environments, execution infrastructure, remote job systems, or model-hosting infrastructure.",
    }
    return batch_text, config_text, report


def main() -> int:
    args = parse_args()
    for output in (args.batch_output, args.config_output, args.report_output):
        if output.exists() or output.is_symlink():
            raise ValueError(f"refusing to overwrite output: {output}")
    batch_text, config_text, report = build(args)
    atomic_write(args.batch_output, batch_text)
    atomic_write(args.config_output, config_text)
    atomic_write(args.report_output, json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": True, "row_count": report["summary"]["input_row_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
