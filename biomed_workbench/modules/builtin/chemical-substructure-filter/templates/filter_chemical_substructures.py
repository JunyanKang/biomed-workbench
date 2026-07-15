#!/usr/bin/env python3
"""Apply validated SMARTS filters with complete chemical-record accounting."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import platform
import tempfile
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

from rdkit import Chem


MODULE_ID = "chemical-substructure-filter"
MODULE_VERSION = "1.0.0"


@dataclass
class ChemicalRecord:
    ordinal: int
    identifier: str
    source_text: str | None
    molecule: Any | None
    parse_error: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--format", required=True, choices=("smi", "csv", "sdf"))
    parser.add_argument("--smiles-column", default="smiles")
    parser.add_argument("--identifier-column", default="compound_id")
    parser.add_argument("--include-smarts", action="append", default=[])
    parser.add_argument("--exclude-smarts", action="append", default=[])
    parser.add_argument("--report-output", required=True, type=Path)
    parser.add_argument("--records-output", required=True, type=Path)
    return parser.parse_args()


def stable_input(path: Path) -> tuple[Path, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("chemical input must be a stable regular file")
    content = path.read_bytes()
    if not content:
        raise ValueError("chemical input is empty")
    return path.resolve(), hashlib.sha256(content).hexdigest()


def unsanitized_smiles(value: str) -> tuple[Any | None, str | None]:
    try:
        molecule = Chem.MolFromSmiles(value, sanitize=False)
    except Exception as exc:
        return None, f"smiles_parse_exception:{type(exc).__name__}"
    if molecule is None:
        return None, "smiles_parse_failed"
    return molecule, None


def read_csv_records(path: Path, smiles_column: str, identifier_column: str) -> list[ChemicalRecord]:
    records = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or smiles_column not in reader.fieldnames or identifier_column not in reader.fieldnames:
            raise ValueError("CSV header does not contain the declared SMILES and identifier columns")
        for ordinal, row in enumerate(reader, start=1):
            identifier = (row.get(identifier_column) or "").strip()
            smiles = (row.get(smiles_column) or "").strip()
            molecule, error = unsanitized_smiles(smiles) if smiles else (None, "missing_smiles")
            records.append(ChemicalRecord(ordinal, identifier, smiles or None, molecule, error))
    return records


def read_smiles_records(path: Path) -> list[ChemicalRecord]:
    records = []
    for ordinal, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        smiles = fields[0]
        identifier = fields[1] if len(fields) > 1 else f"record_{ordinal}"
        molecule, error = unsanitized_smiles(smiles)
        records.append(ChemicalRecord(ordinal, identifier, smiles, molecule, error))
    return records


def read_sdf_records(path: Path) -> list[ChemicalRecord]:
    supplier = Chem.SDMolSupplier(str(path), sanitize=False, removeHs=False, strictParsing=True)
    records = []
    for ordinal, molecule in enumerate(supplier, start=1):
        if molecule is None:
            records.append(ChemicalRecord(ordinal, f"record_{ordinal}", None, None, "sdf_parse_failed"))
            continue
        identifier = molecule.GetProp("_Name").strip() if molecule.HasProp("_Name") else f"record_{ordinal}"
        records.append(ChemicalRecord(ordinal, identifier, None, molecule, None))
    return records


def read_records(path: Path, input_format: str, smiles_column: str, identifier_column: str) -> list[ChemicalRecord]:
    if input_format == "csv":
        records = read_csv_records(path, smiles_column, identifier_column)
    elif input_format == "smi":
        records = read_smiles_records(path)
    else:
        records = read_sdf_records(path)
    if not records:
        raise ValueError("no chemical records were observed")
    identifiers = [record.identifier for record in records]
    if any(not identifier for identifier in identifiers):
        raise ValueError("every chemical record requires a nonempty identifier")
    duplicates = sorted({identifier for identifier in identifiers if identifiers.count(identifier) > 1})
    if duplicates:
        raise ValueError(f"chemical record identifiers are not unique: {', '.join(duplicates[:10])}")
    return records


def compile_queries(values: list[str], role: str) -> list[tuple[str, str, Any]]:
    compiled = []
    for index, value in enumerate(values, start=1):
        query = Chem.MolFromSmarts(value)
        if query is None:
            raise ValueError(f"invalid {role} SMARTS at position {index}: {value}")
        compiled.append((f"{role}_{index:03d}", value, query))
    return compiled


def sanitize_molecule(molecule) -> str | None:
    try:
        Chem.SanitizeMol(molecule)
        Chem.AssignStereochemistry(molecule, cleanIt=True, force=True)
    except Exception as exc:
        return f"sanitization_failed:{type(exc).__name__}"
    return None


def inspect_record(record: ChemicalRecord, include_queries, exclude_queries) -> dict[str, Any]:
    base = {
        "ordinal": record.ordinal,
        "identifier": record.identifier,
        "status": "rejected",
        "reason": record.parse_error,
        "canonical_isomeric_smiles": None,
        "heavy_atom_count": None,
        "fragment_count": None,
        "formal_charge": None,
        "include_matches": {},
        "exclude_matches": {},
    }
    if record.molecule is None:
        return base
    molecule = Chem.Mol(record.molecule)
    error = sanitize_molecule(molecule)
    if error:
        base["reason"] = error
        return base
    base["canonical_isomeric_smiles"] = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    base["heavy_atom_count"] = molecule.GetNumHeavyAtoms()
    base["fragment_count"] = len(Chem.GetMolFrags(molecule))
    base["formal_charge"] = Chem.GetFormalCharge(molecule)
    for query_id, _smarts, query in include_queries:
        base["include_matches"][query_id] = [list(match) for match in molecule.GetSubstructMatches(query, uniquify=True)]
    for query_id, _smarts, query in exclude_queries:
        base["exclude_matches"][query_id] = [list(match) for match in molecule.GetSubstructMatches(query, uniquify=True)]
    missing_includes = [query_id for query_id, matches in base["include_matches"].items() if not matches]
    present_excludes = [query_id for query_id, matches in base["exclude_matches"].items() if matches]
    if missing_includes:
        base["reason"] = "missing_required_queries:" + ",".join(missing_includes)
    elif present_excludes:
        base["reason"] = "matched_excluded_queries:" + ",".join(present_excludes)
    else:
        base["status"] = "accepted"
        base["reason"] = "passed_all_queries"
    return base


def encode_table(rows: list[dict[str, Any]]) -> str:
    fields = [
        "ordinal", "identifier", "status", "reason", "canonical_isomeric_smiles", "heavy_atom_count",
        "fragment_count", "formal_charge", "include_matches", "exclude_matches",
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, delimiter="\t")
    writer.writeheader()
    for row in rows:
        encoded = dict(row)
        encoded["include_matches"] = json.dumps(row["include_matches"], sort_keys=True, separators=(",", ":"))
        encoded["exclude_matches"] = json.dumps(row["exclude_matches"], sort_keys=True, separators=(",", ":"))
        writer.writerow(encoded)
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
    records = read_records(input_path, args.format, args.smiles_column, args.identifier_column)
    include_queries = compile_queries(args.include_smarts, "include")
    exclude_queries = compile_queries(args.exclude_smarts, "exclude")
    if not include_queries and not exclude_queries:
        raise ValueError("at least one inclusion or exclusion SMARTS query is required")
    rows = [inspect_record(record, include_queries, exclude_queries) for record in records]
    if len(rows) != len(records) or len({row["identifier"] for row in rows}) != len(rows):
        raise ValueError("chemical record accounting failed")
    table = encode_table(rows)
    report = {
        "schema_version": 1,
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "input": {"sha256": input_digest, "format": args.format, "record_count": len(records)},
        "queries": {
            "include": [{"id": query_id, "smarts": smarts} for query_id, smarts, _query in include_queries],
            "exclude": [{"id": query_id, "smarts": smarts} for query_id, smarts, _query in exclude_queries],
        },
        "summary": {
            "input_count": len(rows),
            "accepted_count": sum(row["status"] == "accepted" for row in rows),
            "rejected_count": sum(row["status"] == "rejected" for row in rows),
            "parse_or_sanitization_failure_count": sum(bool(row["reason"]) and ("parse" in row["reason"] or "sanitization" in row["reason"]) for row in rows),
        },
        "records_output": {"row_count": len(rows), "sha256": hashlib.sha256(table.encode()).hexdigest()},
        "quality_status": "passed",
        "versions": {"python": platform.python_version(), "rdkit": version("rdkit")},
        "interpretation_boundary": "SMARTS matches are representation-dependent and do not imply tautomeric, protonation, salt, stereochemical, activity, safety, or binding equivalence.",
    }
    if report["summary"]["accepted_count"] + report["summary"]["rejected_count"] != report["summary"]["input_count"]:
        raise ValueError("accepted and rejected counts do not reconcile")
    report["result_digest"] = hashlib.sha256(json.dumps(report, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return report, table


def main() -> int:
    args = parse_args()
    report, table = build_report(args)
    atomic_write(args.records_output, table)
    atomic_write(args.report_output, json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
