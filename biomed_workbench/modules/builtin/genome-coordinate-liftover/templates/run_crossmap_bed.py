#!/usr/bin/env python3
"""Execute a chain-bound BED liftover with complete source-record accounting.

This project template expects a zero-based half-open BED file with a unique
identifier in column four. It operates only on explicitly declared source and
target assemblies and a content-addressed UCSC chain artifact. It deliberately
does not download chains, infer builds, normalize alleles, or discard failures.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any


MODULE_ID = "genome-coordinate-liftover"
MODULE_VERSION = "0.1.0"
QUALITY_GATES = (
    "liftover-coordinate-and-assembly-identity",
    "liftover-chain-integrity",
    "liftover-record-accounting",
    "liftover-downstream-claim-boundary",
)
BED_ID = re.compile(r"^[^\t\r\n ]+$")


class LiftoverError(ValueError):
    """Raised for a contract or scientific-quality failure."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_bed(path: Path) -> dict[str, list[str]]:
    """Load a regular BED file and enforce source-record identity semantics."""
    if path.is_symlink() or not path.is_file():
        raise LiftoverError("input BED must be a stable regular file")
    records: dict[str, list[str]] = {}
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    for line_number, line in enumerate(lines, start=1):
        if not line or line.startswith("#") or line.startswith("track") or line.startswith("browser"):
            continue
        fields = line.split("\t")
        if len(fields) < 4:
            raise LiftoverError(f"BED line {line_number} requires at least four tab-separated fields")
        chrom, start_text, end_text, record_id = fields[:4]
        try:
            start, end = int(start_text), int(end_text)
        except ValueError as exc:
            raise LiftoverError(f"BED line {line_number} has non-integer coordinates") from exc
        if not chrom or start < 0 or end <= start or not BED_ID.fullmatch(record_id):
            raise LiftoverError(f"BED line {line_number} violates zero-based half-open coordinate or identifier rules")
        if record_id in records:
            raise LiftoverError(f"BED identifier is not unique: {record_id}")
        records[record_id] = fields
    if not records:
        raise LiftoverError("input BED contains no data records")
    return records


def command_version(executable: str) -> str:
    result = subprocess.run([executable, "-v"], text=True, capture_output=True, check=False, timeout=30)
    text = (result.stdout + result.stderr).strip()
    if result.returncode != 0 or not re.search(r"(?:v)?0\.7\.\d+", text):
        raise LiftoverError(f"CrossMap version probe failed or is outside the validated 0.7 series: {text}")
    return text


def parse_outputs(mapped_path: Path, unmapped_path: Path, source_ids: set[str]) -> tuple[dict[str, list[list[str]]], set[str]]:
    """Reload CrossMap outputs and reconcile mapped/split/unmapped identities."""
    mapped: dict[str, list[list[str]]] = {}
    if mapped_path.is_file():
        for line_number, line in enumerate(mapped_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line:
                continue
            fields = line.split("\t")
            if len(fields) < 4:
                raise LiftoverError(f"mapped BED line {line_number} has fewer than four fields")
            try:
                start, end = int(fields[1]), int(fields[2])
            except ValueError as exc:
                raise LiftoverError(f"mapped BED line {line_number} has invalid coordinates") from exc
            if not fields[0] or start < 0 or end <= start or fields[3] not in source_ids:
                raise LiftoverError(f"mapped BED line {line_number} fails target coordinate or source identity validation")
            mapped.setdefault(fields[3], []).append(fields)
    unmapped: set[str] = set()
    if unmapped_path.is_file():
        for line_number, line in enumerate(unmapped_path.read_text(encoding="utf-8").splitlines(), start=1):
            fields = line.split("\t")
            if len(fields) < 5 or fields[-1] != "Unmap" or fields[3] not in source_ids:
                raise LiftoverError(f"unmapped sidecar line {line_number} is not a CrossMap BED unmapped record")
            unmapped.add(fields[3])
    overlap = set(mapped).intersection(unmapped)
    if overlap:
        raise LiftoverError(f"records cannot be both mapped and unmapped: {', '.join(sorted(overlap))}")
    accounted = set(mapped).union(unmapped)
    if accounted != source_ids:
        missing = sorted(source_ids - accounted)
        unknown = sorted(accounted - source_ids)
        raise LiftoverError(f"record accounting failed; missing={missing}, unknown={unknown}")
    return mapped, unmapped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-bed", required=True)
    parser.add_argument("--chain", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source-assembly", required=True)
    parser.add_argument("--target-assembly", required=True)
    parser.add_argument("--chain-sha256", required=True, help="Expected immutable SHA256 of --chain")
    parser.add_argument("--crossmap", default="CrossMap")
    parser.add_argument("--split-mapping-policy", choices=("retain-and-flag", "block-downstream", "predeclared-aggregation"), required=True)
    parser.add_argument("--unmapped-policy", choices=("retain-and-report", "block-if-any"), required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_bed, chain, output_dir = Path(args.input_bed), Path(args.chain), Path(args.output_dir)
    if not args.source_assembly.strip() or not args.target_assembly.strip() or args.source_assembly == args.target_assembly:
        raise LiftoverError("source and target assemblies must be distinct declared nonempty identifiers")
    if chain.is_symlink() or not chain.is_file():
        raise LiftoverError("chain must be a stable regular file")
    expected_chain_digest = args.chain_sha256.lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_chain_digest) or sha256(chain) != expected_chain_digest:
        raise LiftoverError("chain SHA256 does not match the declared immutable chain artifact")
    source = parse_bed(input_bed)
    executable = shutil.which(args.crossmap) if not Path(args.crossmap).is_file() else args.crossmap
    if not executable:
        raise LiftoverError("CrossMap executable is unavailable in the existing environment")
    version = command_version(executable)
    if output_dir.exists():
        raise LiftoverError("output directory must be new to prevent provenance overwrite")
    output_dir.mkdir(parents=True)
    mapped_path = output_dir / "lifted.bed"
    command = [str(executable), "bed", str(chain), str(input_bed), str(mapped_path)]
    completed = subprocess.run(command, text=True, capture_output=True, check=False, timeout=180)
    if completed.returncode != 0:
        raise LiftoverError(f"CrossMap execution failed: {completed.stderr.strip()}")
    mapped, unmapped = parse_outputs(mapped_path, Path(str(mapped_path) + ".unmap"), set(source))
    split_ids = sorted(record_id for record_id, rows in mapped.items() if len(rows) > 1)
    if args.unmapped_policy == "block-if-any" and unmapped:
        raise LiftoverError("unmapped records violate the declared block-if-any policy")
    if args.split_mapping_policy == "block-downstream" and split_ids:
        raise LiftoverError("split mappings violate the declared block-downstream policy")
    report: dict[str, Any] = {
        "passed": True, "module_id": MODULE_ID, "module_version": MODULE_VERSION,
        "source_assembly": args.source_assembly, "target_assembly": args.target_assembly,
        "coordinate_convention": "zero-based-half-open", "quality_gate_ids": list(QUALITY_GATES),
        "input_sha256": sha256(input_bed), "chain_sha256": expected_chain_digest,
        "tool_versions": {"CrossMap": version},
        "command": {"tool": "CrossMap", "subcommand": "bed", "argument_roles": ["declared-chain", "declared-input-bed", "new-output-bed"]},
        "records": {"input": len(source), "mapped": len(mapped), "unmapped": len(unmapped), "split_mapped": len(split_ids), "unmapped_ids": sorted(unmapped), "split_mapped_ids": split_ids},
        "policies": {"split_mapping": args.split_mapping_policy, "unmapped": args.unmapped_policy},
        "claim_boundary": "Coordinate mapping does not establish allele, gene, peak, regulatory, orthology, or functional equivalence."
    }
    (output_dir / "liftover-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LiftoverError as exc:
        print(f"{MODULE_ID}: {exc}", file=sys.stderr)
        raise SystemExit(2)
