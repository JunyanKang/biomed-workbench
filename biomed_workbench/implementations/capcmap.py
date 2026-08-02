"""Pinned capC-MAP 1.1.3 execution for Capture-C FASTQ data."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VERSION = "1.1.3"
COMMIT = "fc2168f6da8a4fe331d5b22872789fa4caac0749"
SOURCE = "https://github.com/cbrackley/capC-MAP"


class CapCMapExecutionError(ValueError):
    pass


def _sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _file(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise CapCMapExecutionError(f"{label} must be a local path")
    path = Path(value).expanduser()
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise CapCMapExecutionError(f"{label} must be a nonempty non-symlink file: {path}")
    path = path.resolve()
    if any(character.isspace() for character in str(path)):
        raise CapCMapExecutionError(f"{label} path cannot contain whitespace because capC-MAP 1.1.3 parses whitespace-delimited configuration")
    return path


def _root(value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise CapCMapExecutionError("capcmap_root must identify a local pinned capC-MAP checkout")
    root = Path(value).expanduser().resolve()
    if not (root / "capC-map").is_file() or not (root / "VERSION").is_file():
        raise CapCMapExecutionError(f"capC-MAP source or VERSION is missing under {root}")
    observed = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False, timeout=30)
    if observed.returncode != 0 or observed.stdout.strip() != COMMIT or (root / "VERSION").read_text().strip() != VERSION:
        raise CapCMapExecutionError(f"capC-MAP {VERSION} commit {COMMIT} required")
    return root


def execute_capcmap(request: dict[str, Any], *, output_dir: Path, report_path: Path, timeout_seconds: int = 172800) -> dict[str, Any]:
    if request.get("schema_version") != 1 or request.get("module_id") != "bulk-three-dimensional-genome" or str(request.get("assay", "")).lower() != "capture-c":
        raise CapCMapExecutionError("request must target bulk-three-dimensional-genome assay=capture-c schema version 1")
    fastq1 = _file(request.get("fastq_1"), "fastq_1")
    fastq2 = _file(request.get("fastq_2"), "fastq_2")
    targets = _file(request.get("targets_bed"), "targets_bed")
    restriction_fragments = _file(request.get("restriction_fragments_bed"), "restriction_fragments_bed")
    root = _root(request.get("capcmap_root"))
    index = str(Path(str(request.get("bowtie_index", ""))).expanduser().resolve())
    if any(character.isspace() for character in index) or not Path(index + ".1.ebwt").is_file():
        raise CapCMapExecutionError("bowtie_index must be a whitespace-free Bowtie 1 index prefix with .1.ebwt")
    parameters = request.get("parameters", {})
    allowed = {"restriction_enzyme", "parallel", "align_mode", "exclude_bp", "trim_adapters", "interchromosomal", "normalize", "bins"}
    if not isinstance(parameters, dict) or set(parameters) - allowed:
        raise CapCMapExecutionError("unknown capC-MAP parameter")
    enzyme = str(parameters.get("restriction_enzyme", "DPNII")).upper()
    parallel = int(parameters.get("parallel", 1))
    align_mode = str(parameters.get("align_mode", "CONSERVATIVE")).upper()
    exclude = int(parameters.get("exclude_bp", 1000))
    trim = bool(parameters.get("trim_adapters", True))
    interchrom = bool(parameters.get("interchromosomal", False))
    normalize = bool(parameters.get("normalize", True))
    raw_bins = parameters.get("bins", [[500, 1000], [3000, 6000]])
    if not enzyme or any(character.isspace() for character in enzyme) or parallel < 1 or exclude < 0 or align_mode not in {"CONSERVATIVE", "RELAXED"}:
        raise CapCMapExecutionError("capC-MAP enzyme, parallel, exclusion, or alignment mode is invalid")
    if not isinstance(raw_bins, list) or not raw_bins:
        raise CapCMapExecutionError("bins must be a nonempty list of [step, window] pairs")
    bins: list[list[int]] = []
    for pair in raw_bins:
        if not isinstance(pair, list) or len(pair) != 2:
            raise CapCMapExecutionError("every bin must be [step, window]")
        step, window = int(pair[0]), int(pair[1])
        if step <= 0 or window < step:
            raise CapCMapExecutionError("bin step must be positive and window must be at least step")
        bins.append([step, window])
    if output_dir.exists() or report_path.exists():
        raise CapCMapExecutionError("output directory and report path must not already exist")
    output_dir = output_dir.resolve(); report_path = report_path.resolve()
    config_path = output_dir.parent / f".{output_dir.name}.capcmap.config"
    if config_path.exists():
        raise CapCMapExecutionError(f"generated config already exists: {config_path}")
    lines = [
        f"FASTQ1 {fastq1}", f"FASTQ2 {fastq2}", f"TARGETS {targets}", f"INDEX {index}",
        f"RESTFRAGS {restriction_fragments}", f"ENZYME {enzyme}", f"PARALLEL {parallel}",
        f"ALIGNMODE {align_mode}", f"EXCLUDE {exclude}", f"TRIMADAPTERS {'TRUE' if trim else 'FALSE'}",
        f"INTERCHROM {'TRUE' if interchrom else 'FALSE'}", f"NORMALIZE {'TRUE' if normalize else 'FALSE'}",
        *[f"BIN {step} {window}" for step, window in bins],
    ]
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    completed = subprocess.run([sys.executable, str(root / "capC-map"), "run", "-c", str(config_path), "-o", str(output_dir)], cwd=root, capture_output=True, text=True, check=False, timeout=timeout_seconds)
    if completed.returncode != 0:
        raise CapCMapExecutionError(f"capC-MAP failed: {completed.stderr[-4000:]}")
    valid_pairs = sorted(path for path in output_dir.rglob("*_validpairs_*.pairs") if path.stat().st_size > 0)
    raw_profiles = sorted(path for path in output_dir.rglob("*_rawpileup_*.bdg") if path.stat().st_size > 0)
    binned_profiles = sorted(path for path in output_dir.rglob("*_bin_*.bdg") if path.stat().st_size > 0)
    reports = sorted(path for path in output_dir.rglob("*_report.dat") if path.stat().st_size > 0)
    if not valid_pairs or not raw_profiles or not binned_profiles or not reports:
        raise CapCMapExecutionError("capC-MAP completed without valid pairs, target pileups, binned profiles, and report output")
    log = output_dir / "capcmap.execution.log"
    log.write_text("STDOUT\n" + completed.stdout + "\nSTDERR\n" + completed.stderr, encoding="utf-8")
    def records(paths: list[Path]) -> list[dict[str, Any]]:
        return [{"path": str(path.relative_to(output_dir)), "bytes": path.stat().st_size, "sha256": _sha256(path)} for path in paths]
    implementation = Path(__file__).resolve()
    report = {
        "schema_version": 1, "module_id": "bulk-three-dimensional-genome", "assay": "capture-c", "passed": True,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "workflow": {"name": "capC-MAP", "version": VERSION, "commit": COMMIT, "source": SOURCE},
        "implementation": {"path": str(implementation.relative_to(implementation.parents[2])), "sha256": _sha256(implementation)},
        "inputs": {"fastq_1": _sha256(fastq1), "fastq_2": _sha256(fastq2), "targets_bed": _sha256(targets), "restriction_fragments_bed": _sha256(restriction_fragments), "bowtie_index": index},
        "parameters": {"restriction_enzyme": enzyme, "parallel": parallel, "align_mode": align_mode, "exclude_bp": exclude, "trim_adapters": trim, "interchromosomal": interchrom, "normalize": normalize, "bins": bins},
        "generated_config_sha256": _sha256(config_path),
        "outputs": {"valid_pairs": records(valid_pairs), "raw_target_profiles": records(raw_profiles), "binned_target_profiles": records(binned_profiles), "reports": records(reports)},
        "provenance": {"log_sha256": _sha256(log)},
        "claim_boundary": "Capture-C profiles estimate population contact enrichment from declared bait fragments; capture efficiency and restriction-fragment design constrain comparisons.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
