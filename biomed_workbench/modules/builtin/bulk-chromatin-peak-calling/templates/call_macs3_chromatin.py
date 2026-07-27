#!/usr/bin/env python3
"""Call and reload bulk ChIP-seq, CUT&RUN, or CUT&Tag peaks with MACS3.

The template operates only on project-supplied BED/BEDPE/BAM evidence in an
already prepared scientific runtime. It records the exact command, parameters,
input digests, output digests, interval accounting, and no-control decision. It
does not install tools, manufacture a fallback peak set, or interpret peaks as
direct binding, functional enhancers, or causal gene regulation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path


class ChromatinPeakError(ValueError):
    """Raised when a peak-calling input or output violates the declared contract."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def regular_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ChromatinPeakError(f"{label} must be a stable non-symlink file")
    return path


def parse_bed(path: Path, *, minimum_columns: int = 3) -> dict[str, object]:
    """Validate zero-based BED-like coordinates and return immutable accounting."""
    rows = 0
    chromosomes: Counter[str] = Counter()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip() or raw.startswith(("#", "track", "browser")):
                continue
            fields = raw.rstrip("\n").split("\t")
            if len(fields) < minimum_columns:
                raise ChromatinPeakError(f"{path.name} line {line_number} has fewer than {minimum_columns} columns")
            try:
                start, end = int(fields[1]), int(fields[2])
            except ValueError as exc:
                raise ChromatinPeakError(f"{path.name} line {line_number} has noninteger coordinates") from exc
            if not fields[0] or start < 0 or end <= start:
                raise ChromatinPeakError(f"{path.name} line {line_number} has invalid genomic coordinates")
            rows += 1
            chromosomes[fields[0]] += 1
    if rows == 0:
        raise ChromatinPeakError(f"{path.name} has no valid interval records")
    return {"rows": rows, "chromosomes": dict(sorted(chromosomes.items())), "sha256": sha256(path)}


def validate_input_format(path: Path, input_format: str) -> dict[str, object]:
    """Validate format-specific source evidence before handing it to MACS3."""
    if input_format == "BAM":
        index_candidates = (Path(f"{path}.bai"), Path(f"{path}.csi"), path.with_suffix(".bai"), path.with_suffix(".csi"))
        if not any(candidate.is_file() and not candidate.is_symlink() for candidate in index_candidates):
            raise ChromatinPeakError("BAM input requires a readable BAI or CSI index")
        return {"format": "BAM", "sha256": sha256(path), "index_present": True}
    if input_format == "BED":
        return {"format": "BED", **parse_bed(path, minimum_columns=3)}
    if input_format != "BEDPE":
        raise ChromatinPeakError(f"unsupported input format: {input_format}")
    evidence = parse_bed(path, minimum_columns=6)
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip() or raw.startswith(("#", "track", "browser")):
                continue
            fields = raw.rstrip("\n").split("\t")
            try:
                start2, end2 = int(fields[4]), int(fields[5])
            except ValueError as exc:
                raise ChromatinPeakError(f"{path.name} line {line_number} has noninteger second-end coordinates") from exc
            if not fields[3] or start2 < 0 or end2 <= start2:
                raise ChromatinPeakError(f"{path.name} line {line_number} has invalid second-end BEDPE coordinates")
    return {"format": "BEDPE", **evidence}


def parse_peak_output(path: Path, *, peak_mode: str) -> dict[str, object]:
    minimum_columns = 9 if peak_mode == "broad" else 10
    evidence = parse_bed(path, minimum_columns=minimum_columns)
    finite_statistics = 0
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            if not raw.strip() or raw.startswith("#"):
                continue
            fields = raw.rstrip("\n").split("\t")
            try:
                values = [float(value) for value in fields[6:9]]
            except ValueError as exc:
                raise ChromatinPeakError(f"{path.name} contains nonnumeric MACS3 peak statistics") from exc
            if any(not math.isfinite(value) for value in values):
                raise ChromatinPeakError(f"{path.name} contains nonfinite MACS3 peak statistics")
            finite_statistics += 1
    if finite_statistics != evidence["rows"]:
        raise ChromatinPeakError("peak row count and statistical accounting disagree")
    return {**evidence, "finite_statistic_rows": finite_statistics}


def command_version(executable: str) -> tuple[str, str]:
    resolved = shutil.which(executable)
    if resolved is None:
        raise ChromatinPeakError(f"MACS3 executable not found: {executable}")
    completed = subprocess.run([resolved, "--version"], capture_output=True, text=True, check=False, timeout=30)
    output = (completed.stdout + "\n" + completed.stderr).strip()
    if completed.returncode != 0 or not output:
        raise ChromatinPeakError("MACS3 version detection failed")
    try:
        distribution_version = importlib.metadata.version("MACS3")
    except importlib.metadata.PackageNotFoundError:
        distribution_version = output
    return resolved, distribution_version


def build_command(args: argparse.Namespace, executable: str) -> list[str]:
    command = [
        executable, "callpeak", "-t", str(args.treatment), "-f", args.input_format,
        "-n", args.name, "--outdir", str(args.output_dir), "-g", str(args.genome_size),
        "-q", str(args.qvalue), "--keep-dup", args.keep_dup,
    ]
    if args.control is not None:
        command.extend(["-c", str(args.control)])
    if args.peak_mode == "broad":
        command.extend(["--broad", "--broad-cutoff", str(args.broad_cutoff)])
    else:
        command.append("--call-summits")
    if args.nomodel_extsize is not None:
        command.extend(["--nomodel", "--extsize", str(args.nomodel_extsize)])
    return command


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assay", choices=("chip-seq", "cutrun", "cuttag"), required=True)
    parser.add_argument("--treatment", type=Path, required=True)
    parser.add_argument("--control", type=Path)
    parser.add_argument("--input-format", choices=("BED", "BEDPE", "BAM"), required=True)
    parser.add_argument("--peak-mode", choices=("narrow", "broad"), required=True)
    parser.add_argument("--genome-size", required=True)
    parser.add_argument("--qvalue", type=float, required=True)
    parser.add_argument("--broad-cutoff", type=float, default=0.1)
    parser.add_argument("--nomodel-extsize", type=int, help="Explicit fixed fragment extension when MACS3 model building is scientifically inappropriate")
    parser.add_argument("--keep-dup", choices=("all", "auto"), default="auto")
    parser.add_argument("--name", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--macs3", default="macs3")
    return parser.parse_args()


def validate_request(args: argparse.Namespace) -> None:
    regular_file(args.treatment, "treatment")
    if args.control is not None:
        regular_file(args.control, "control")
    if not 0 < args.qvalue < 1 or not 0 < args.broad_cutoff < 1:
        raise ChromatinPeakError("qvalue and broad-cutoff must be between zero and one")
    if args.nomodel_extsize is not None and not 1 <= args.nomodel_extsize <= 2000:
        raise ChromatinPeakError("nomodel-extsize must be an integer between 1 and 2000")
    if not args.name or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in args.name):
        raise ChromatinPeakError("name must contain only letters, numbers, dots, underscores, or hyphens")
    if args.output_dir.exists() or args.output_dir.is_symlink():
        raise ChromatinPeakError("output-dir must be a new non-symlink path")
    if args.report.exists() or args.report.is_symlink():
        raise ChromatinPeakError("report must be a new non-symlink path")
    if args.assay == "chip-seq" and args.control is None:
        raise ChromatinPeakError("chip-seq requires a matched input/control artifact in this template")
    validate_input_format(args.treatment, args.input_format)
    if args.control is not None:
        validate_input_format(args.control, args.input_format)


def main() -> int:
    args = parse_args()
    validate_request(args)
    executable, version = command_version(args.macs3)
    treatment_digest = sha256(args.treatment)
    control_digest = sha256(args.control) if args.control is not None else None
    treatment_format = validate_input_format(args.treatment, args.input_format)
    control_format = validate_input_format(args.control, args.input_format) if args.control is not None else None
    args.output_dir.mkdir(parents=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    command = build_command(args, executable)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=7200)
    except subprocess.TimeoutExpired as exc:
        raise ChromatinPeakError("MACS3 peak calling exceeded the declared two-hour limit") from exc
    if completed.returncode != 0:
        raise ChromatinPeakError(f"MACS3 callpeak failed: {completed.stderr[-6000:]}")
    if sha256(args.treatment) != treatment_digest or (args.control is not None and sha256(args.control) != control_digest):
        raise ChromatinPeakError("a source input changed during peak calling")

    extension = "broadPeak" if args.peak_mode == "broad" else "narrowPeak"
    peaks = args.output_dir / f"{args.name}_peaks.{extension}"
    if not peaks.is_file() or peaks.stat().st_size == 0:
        raise ChromatinPeakError(f"MACS3 did not produce a nonempty {extension} output")
    peak_evidence = parse_peak_output(peaks, peak_mode=args.peak_mode)
    summit_evidence = None
    if args.peak_mode == "narrow":
        summits = args.output_dir / f"{args.name}_summits.bed"
        if not summits.is_file() or summits.stat().st_size == 0:
            raise ChromatinPeakError("narrow peak calling completed without nonempty summit output")
        summit_evidence = parse_bed(summits, minimum_columns=5)

    report = {
        "module_id": "bulk-chromatin-peak-calling", "module_version": "0.1.0", "passed": True,
        "assay": args.assay, "tool": {"name": "MACS3", "version": version},
        "input": {"treatment_sha256": treatment_digest, "control_sha256": control_digest, "format": args.input_format, "treatment_format_validation": treatment_format, "control_format_validation": control_format},
        "parameters": {"peak_mode": args.peak_mode, "genome_size": str(args.genome_size), "qvalue": args.qvalue, "broad_cutoff": args.broad_cutoff if args.peak_mode == "broad" else None, "keep_duplicates": args.keep_dup, "nomodel_extsize": args.nomodel_extsize},
        "command": {"argv": command, "stderr_tail": completed.stderr[-4000:]},
        "outputs": {"peaks": {**peak_evidence, "path": peaks.name}, "summits": summit_evidence},
        "quality_gate_ids": ["bulk-chromatin-input-control", "bulk-chromatin-macs3-output", "bulk-chromatin-provenance"],
        "limitations": ["Peak calls are method- and parameter-specific enrichment evidence, not direct binding or causal regulatory proof.", "No-control CUT&RUN or CUT&Tag output remains assay-level enrichment evidence and needs independent specificity and replicate assessment."],
        "source_inputs_immutable": True, "outputs_reloaded": True, "no_environment_or_compute_infrastructure_managed": True,
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "peak_count": peak_evidence["rows"], "tool_version": version}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ChromatinPeakError as exc:
        print(f"ChromatinPeakError: {exc}", file=sys.stderr)
        raise SystemExit(2)
