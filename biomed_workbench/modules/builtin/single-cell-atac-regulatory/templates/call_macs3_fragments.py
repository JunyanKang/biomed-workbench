#!/usr/bin/env python3
"""Call reproducible scATAC peaks from validated 10x fragment records with MACS3."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.metadata
import json
import math
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def parse_allowlist(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    barcodes = {line.strip().split("\t", 1)[0] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    if not barcodes:
        raise ValueError("barcode allow-list is empty")
    return barcodes


def validate_and_filter(source: Path, destination: Path, allowlist: set[str] | None) -> dict[str, object]:
    observed_barcodes: Counter[str] = Counter()
    selected_barcodes: Counter[str] = Counter()
    total_records = selected_records = total_fragments = selected_fragments = 0
    with open_text(source) as reader, destination.open("w", encoding="utf-8", newline="") as writer:
        for line_number, raw in enumerate(reader, start=1):
            if not raw.strip() or raw.startswith("#"):
                continue
            fields = raw.rstrip("\n").split("\t")
            if len(fields) < 5:
                raise ValueError(f"fragment line {line_number} has fewer than five tab-separated fields")
            chrom, start_text, end_text, barcode, count_text = fields[:5]
            try:
                start, end, count = int(start_text), int(end_text), int(count_text)
            except ValueError as error:
                raise ValueError(f"fragment line {line_number} has a non-integer coordinate or count") from error
            if not chrom or start < 0 or end <= start or not barcode or count <= 0:
                raise ValueError(f"fragment line {line_number} violates FRAG coordinate, barcode, or count requirements")
            total_records += 1
            total_fragments += count
            observed_barcodes[barcode] += count
            if allowlist is None or barcode in allowlist:
                writer.write("\t".join((chrom, str(start), str(end), barcode, str(count))) + "\n")
                selected_records += 1
                selected_fragments += count
                selected_barcodes[barcode] += count
    if total_records == 0:
        raise ValueError("fragment file contains no data records")
    if selected_records == 0:
        raise ValueError("barcode selection retained no fragment records")
    missing = sorted(allowlist - set(observed_barcodes)) if allowlist is not None else []
    return {
        "total_records": total_records,
        "selected_records": selected_records,
        "excluded_records": total_records - selected_records,
        "total_fragment_count": total_fragments,
        "selected_fragment_count": selected_fragments,
        "excluded_fragment_count": total_fragments - selected_fragments,
        "observed_barcodes": len(observed_barcodes),
        "selected_barcodes": len(selected_barcodes),
        "allowlist_barcodes": len(allowlist) if allowlist is not None else None,
        "allowlist_barcodes_absent_from_fragments": missing,
    }


def parse_bed(path: Path, minimum_columns: int) -> dict[str, object]:
    rows = 0
    chromosomes: Counter[str] = Counter()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip() or raw.startswith(("#", "track", "browser")):
                continue
            fields = raw.rstrip("\n").split("\t")
            if len(fields) < minimum_columns:
                raise ValueError(f"{path.name} line {line_number} has fewer than {minimum_columns} columns")
            try:
                start, end = int(fields[1]), int(fields[2])
                numeric = [float(value) for value in fields[4:minimum_columns] if value not in {".", ""}]
            except ValueError as error:
                raise ValueError(f"{path.name} line {line_number} has malformed numeric fields") from error
            if not fields[0] or start < 0 or end <= start or any(not math.isfinite(value) for value in numeric):
                raise ValueError(f"{path.name} line {line_number} has invalid coordinates or scores")
            rows += 1
            chromosomes[fields[0]] += 1
    if rows == 0:
        raise ValueError(f"{path.name} contains no reloadable intervals")
    return {"rows": rows, "chromosomes": dict(sorted(chromosomes.items())), "sha256": sha256(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fragments", type=Path, required=True)
    parser.add_argument("--barcode-allowlist", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--genome-size", required=True, help="MACS3 genome size token or positive integer")
    parser.add_argument("--qvalue", type=float, default=0.05)
    parser.add_argument("--macs3", default="macs3")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    if not args.fragments.is_file():
        raise FileNotFoundError(args.fragments)
    if args.barcode_allowlist is not None and not args.barcode_allowlist.is_file():
        raise FileNotFoundError(args.barcode_allowlist)
    if not args.name or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in args.name):
        raise ValueError("name must contain only letters, numbers, dot, underscore, or hyphen")
    if not 0 < args.qvalue < 1:
        raise ValueError("qvalue must be between zero and one")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    executable = shutil.which(args.macs3)
    if executable is None:
        raise FileNotFoundError(f"MACS3 executable not found: {args.macs3}")
    version = importlib.metadata.version("MACS3")
    source_digest = sha256(args.fragments)
    allowlist_digest = sha256(args.barcode_allowlist) if args.barcode_allowlist is not None else None
    allowlist = parse_allowlist(args.barcode_allowlist)

    with tempfile.TemporaryDirectory(prefix="biomed-macs3-frag-") as temporary:
        filtered = Path(temporary) / "selected.fragments.tsv"
        accounting = validate_and_filter(args.fragments, filtered, allowlist)
        command = [
            executable, "callpeak", "-t", str(filtered), "-f", "FRAG", "-n", args.name,
            "--outdir", str(args.output_dir), "-g", str(args.genome_size), "-q", str(args.qvalue),
            "--keep-dup", "all", "--call-summits",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"MACS3 callpeak failed ({completed.returncode}):\n{completed.stderr[-6000:]}")
    if sha256(args.fragments) != source_digest:
        raise RuntimeError("source fragments changed during peak calling")

    narrow_peak = args.output_dir / f"{args.name}_peaks.narrowPeak"
    summits = args.output_dir / f"{args.name}_summits.bed"
    peaks_xls = args.output_dir / f"{args.name}_peaks.xls"
    for output in (narrow_peak, summits, peaks_xls):
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError(f"expected MACS3 output is missing or empty: {output.name}")
    peak_evidence = parse_bed(narrow_peak, 10)
    summit_evidence = parse_bed(summits, 5)

    report = {
        "schema_version": 1,
        "passed": True,
        "tool": "MACS3",
        "tool_version": version,
        "input": {
            "format": "10x-fragments-frag-five-column",
            "compression": "gzip" if args.fragments.suffix == ".gz" else "none",
            "sha256": source_digest,
            "barcode_allowlist_sha256": allowlist_digest,
        },
        "parameters": {
            "format": "FRAG", "genome_size": str(args.genome_size), "qvalue": args.qvalue,
            "keep_duplicates": "all", "call_summits": True, "name": args.name,
        },
        "accounting": accounting,
        "outputs": {"narrow_peak": peak_evidence, "summits": summit_evidence, "peaks_xls_sha256": sha256(peaks_xls)},
        "quality_status": "passed",
        "source_fragments_immutable": True,
        "outputs_reloaded": True,
        "no_environment_or_compute_infrastructure_managed": True,
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "peaks": peak_evidence["rows"], "selected_barcodes": accounting["selected_barcodes"], "tool_version": version}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
