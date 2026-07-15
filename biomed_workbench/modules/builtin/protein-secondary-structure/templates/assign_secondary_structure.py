#!/usr/bin/env python3
"""Run mkdssp and retain residue-level secondary structure and accessibility."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from importlib.metadata import version
from pathlib import Path
from typing import Any

from Bio.PDB import DSSP, MMCIFIO, MMCIFParser, PDBIO, PDBParser, is_aa


MODULE_ID = "protein-secondary-structure"
MODULE_VERSION = "1.0.0"
DSSP_CODES = ("H", "B", "E", "G", "I", "T", "S", "-")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--format", required=True, choices=("pdb", "mmcif"))
    parser.add_argument("--model-index", required=True, type=int)
    parser.add_argument("--chains", required=True, help="Comma-separated protein chain identifiers")
    parser.add_argument("--dssp-executable", required=True)
    parser.add_argument("--dssp-data-directory", required=True, type=Path)
    parser.add_argument("--report-output", required=True, type=Path)
    parser.add_argument("--residue-output", required=True, type=Path)
    return parser.parse_args()


def stable_input(path: Path) -> tuple[Path, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("coordinate input must be a stable regular file")
    content = path.read_bytes()
    if not content:
        raise ValueError("coordinate input is empty")
    return path.resolve(), hashlib.sha256(content).hexdigest()


def resolve_executable(value: str) -> tuple[str, str]:
    candidate = Path(value)
    executable = str(candidate.resolve()) if candidate.exists() else shutil.which(value)
    if not executable or not os.access(executable, os.X_OK):
        raise ValueError("declared mkdssp executable is unavailable or not executable")
    completed = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=10, check=False)
    observed = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
    match = re.search(r"([0-9]+(?:\.[0-9]+)+)", observed)
    if completed.returncode != 0 or match is None:
        raise ValueError("mkdssp version probe failed")
    return executable, match.group(1)


def validate_dssp_data(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_dir():
        raise ValueError("DSSP data directory must be a stable directory")
    resources = {}
    for name in ("components.cif", "mmcif_pdbx.dic", "mmcif_ma.dic"):
        resource = path / name
        if resource.is_symlink() or not resource.is_file() or resource.stat().st_size == 0:
            raise ValueError(f"DSSP data directory lacks required resource: {name}")
        resources[name] = hashlib.sha256(resource.read_bytes()).hexdigest()
    return resources


def load_structure(path: Path, structure_format: str):
    parser = PDBParser(QUIET=True) if structure_format == "pdb" else MMCIFParser(QUIET=True)
    try:
        return parser.get_structure("input", str(path))
    except Exception as exc:
        raise ValueError(f"unable to parse declared {structure_format} coordinate input") from exc


def select_scope(structure, model_index: int, requested_chains: list[str]):
    models = list(structure.get_models())
    if model_index < 0 or model_index >= len(models):
        raise ValueError(f"model index {model_index} is absent from {len(models)} observed models")
    if not requested_chains or len(requested_chains) != len(set(requested_chains)):
        raise ValueError("one or more unique protein chain identifiers are required")
    model = models[model_index]
    observed_chains = {chain.id: chain for chain in model}
    missing = sorted(set(requested_chains) - set(observed_chains))
    if missing:
        raise ValueError(f"requested chains are absent: {', '.join(missing)}")
    selected_residues = {
        (chain_id, residue.id)
        for chain_id in requested_chains
        for residue in observed_chains[chain_id]
        if is_aa(residue, standard=False)
    }
    if not selected_residues:
        raise ValueError("selected chains contain no amino-acid residues")
    return models, model, observed_chains, selected_residues


def run_dssp(model, structure_format: str, executable: str):
    file_type = "PDB" if structure_format == "pdb" else "MMCIF"
    suffix = ".pdb" if structure_format == "pdb" else ".cif"
    with tempfile.TemporaryDirectory(prefix="dssp-selected-model-") as temporary:
        selected_path = Path(temporary) / f"selected_model{suffix}"
        writer = PDBIO() if structure_format == "pdb" else MMCIFIO()
        writer.set_structure(model)
        writer.save(str(selected_path))
        try:
            return DSSP(model, str(selected_path), dssp=executable, file_type=file_type)
        except Exception as exc:
            raise ValueError("observed mkdssp execution failed for the declared coordinate model") from exc


def residue_identifier(residue_id) -> dict[str, Any]:
    hetero_flag, residue_number, insertion_code = residue_id
    return {
        "hetero_flag": str(hetero_flag).strip(),
        "residue_number": int(residue_number),
        "insertion_code": str(insertion_code).strip(),
    }


def dssp_rows(dssp, requested_chains: list[str]) -> list[dict[str, Any]]:
    rows = []
    for chain_id, residue_id in dssp.keys():
        if chain_id not in requested_chains:
            continue
        record = dssp[(chain_id, residue_id)]
        code = str(record[2]).strip() or "-"
        if code not in DSSP_CODES:
            raise ValueError(f"mkdssp emitted an unsupported secondary-structure code: {code}")
        identity = residue_identifier(residue_id)
        rows.append({
            "chain_id": chain_id,
            **identity,
            "dssp_index": int(record[0]),
            "amino_acid": str(record[1]),
            "secondary_structure": code,
            "relative_accessibility": float(record[3]),
            "phi_degrees": float(record[4]),
            "psi_degrees": float(record[5]),
        })
    rows.sort(key=lambda row: (requested_chains.index(row["chain_id"]), row["residue_number"], row["insertion_code"]))
    if not rows:
        raise ValueError("mkdssp produced no assignments for the selected chains")
    return rows


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
    input_path, input_digest = stable_input(args.input)
    executable, dssp_version = resolve_executable(args.dssp_executable)
    dssp_resources = validate_dssp_data(args.dssp_data_directory)
    os.environ["LIBCIFPP_DATA_DIR"] = str(args.dssp_data_directory.resolve())
    structure = load_structure(input_path, args.format)
    requested_chains = [value.strip() for value in args.chains.split(",") if value.strip()]
    models, model, observed_chains, selected_residues = select_scope(structure, args.model_index, requested_chains)
    dssp = run_dssp(model, args.format, executable)
    rows = dssp_rows(dssp, requested_chains)
    assigned_keys = {
        (row["chain_id"], (row["hetero_flag"], row["residue_number"], row["insertion_code"] or " "))
        for row in rows
    }
    selected_normalized = {
        (chain_id, (str(residue_id[0]).strip(), int(residue_id[1]), str(residue_id[2]).strip() or " "))
        for chain_id, residue_id in selected_residues
    }
    unresolved = [
        {"chain_id": chain_id, **residue_identifier(residue_id)}
        for chain_id, residue_id in sorted(selected_residues, key=lambda item: (requested_chains.index(item[0]), item[1][1], item[1][2]))
        if (chain_id, (str(residue_id[0]).strip(), int(residue_id[1]), str(residue_id[2]).strip() or " ")) not in assigned_keys
    ]
    if len(rows) + len(unresolved) != len(selected_normalized):
        raise ValueError("selected, assigned, and unresolved residue accounting does not reconcile")
    table = encode_table(rows)
    counts = {code: sum(row["secondary_structure"] == code for row in rows) for code in DSSP_CODES}
    report = {
        "schema_version": 1,
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "input": {
            "sha256": input_digest,
            "format": args.format,
            "model_index": args.model_index,
            "model_count": len(models),
            "selected_chains": requested_chains,
            "all_chain_ids_in_selected_model": sorted(observed_chains),
        },
        "summary": {
            "selected_amino_acid_residue_count": len(selected_residues),
            "assigned_residue_count": len(rows),
            "unresolved_residue_count": len(unresolved),
            "dssp_code_counts": counts,
        },
        "unresolved_residues": unresolved,
        "residue_output": {"row_count": len(rows), "sha256": hashlib.sha256(table.encode()).hexdigest()},
        "quality_status": "passed_with_unresolved_residues" if unresolved else "passed",
        "versions": {"python": platform.python_version(), "biopython": version("biopython"), "mkdssp": dssp_version},
        "dssp_resources": dssp_resources,
        "interpretation_boundary": "DSSP assignment describes the supplied coordinate model and does not establish solution-state occupancy, dynamics, stability, or biological function.",
    }
    report["result_digest"] = hashlib.sha256(json.dumps(report, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return report, table


def main() -> int:
    args = parse_args()
    report, table = build_report(args)
    atomic_write(args.residue_output, table)
    atomic_write(args.report_output, json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
