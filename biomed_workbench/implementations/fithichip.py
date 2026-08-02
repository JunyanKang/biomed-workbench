"""Pinned FitHiChIP execution for HiChIP and PLAC-seq valid pairs."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VERSION = "11.0"
COMMIT = "0ea1ac21be870908c672316ffbb630189dc6fae2"
SOURCE = "https://github.com/ay-lab/FitHiChIP"


class FitHiChIPExecutionError(ValueError):
    pass


def _sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _file(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise FitHiChIPExecutionError(f"{label} must be a local path")
    path = Path(value).expanduser()
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise FitHiChIPExecutionError(f"{label} must be a nonempty non-symlink file: {path}")
    return path.resolve()


def _pinned_root(value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise FitHiChIPExecutionError("fithichip_root must identify a local pinned FitHiChIP checkout")
    root = Path(value).expanduser().resolve()
    script = root / "FitHiChIP_HiCPro.sh"
    if not script.is_file():
        raise FitHiChIPExecutionError(f"FitHiChIP_HiCPro.sh is missing under {root}")
    observed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False, timeout=30
    )
    if observed.returncode != 0 or observed.stdout.strip() != COMMIT:
        raise FitHiChIPExecutionError(f"FitHiChIP commit {COMMIT} required; observed {observed.stdout.strip()!r}")
    return root


def execute_fithichip(
    request: dict[str, Any], *, output_dir: Path, report_path: Path, timeout_seconds: int = 172800
) -> dict[str, Any]:
    assay = str(request.get("assay", "")).lower()
    if request.get("schema_version") != 1 or request.get("module_id") != "bulk-three-dimensional-genome" or assay not in {"hichip", "plac-seq"}:
        raise FitHiChIPExecutionError("request must target hichip or plac-seq in bulk-three-dimensional-genome schema version 1")
    valid_pairs = _file(request.get("valid_pairs"), "valid_pairs")
    chrom_sizes = _file(request.get("chrom_sizes"), "chrom_sizes")
    peaks = _file(request.get("peak_file"), "peak_file")
    root = _pinned_root(request.get("fithichip_root"))
    parameters = request.get("parameters", {})
    allowed = {"interaction_type", "bin_size", "lower_distance", "upper_distance", "peak_to_peak_background", "bias_type", "merge_interactions", "q_value", "prefix", "circular_genome", "overwrite"}
    if not isinstance(parameters, dict) or set(parameters) - allowed:
        raise FitHiChIPExecutionError("unknown FitHiChIP parameter")
    values = {
        "interaction_type": int(parameters.get("interaction_type", 3)),
        "bin_size": int(parameters.get("bin_size", 5000)),
        "lower_distance": int(parameters.get("lower_distance", 20000)),
        "upper_distance": int(parameters.get("upper_distance", 2000000)),
        "peak_to_peak_background": int(parameters.get("peak_to_peak_background", 0)),
        "bias_type": int(parameters.get("bias_type", 1)),
        "merge_interactions": int(parameters.get("merge_interactions", 1)),
        "q_value": float(parameters.get("q_value", 0.01)),
        "prefix": str(parameters.get("prefix", "FitHiChIP")),
        "circular_genome": int(parameters.get("circular_genome", 0)),
        "overwrite": int(parameters.get("overwrite", 0)),
    }
    if values["interaction_type"] not in {1, 2, 3, 4, 5} or values["bias_type"] not in {1, 2}:
        raise FitHiChIPExecutionError("interaction_type or bias_type is outside the official choices")
    if any(values[key] not in {0, 1} for key in ("peak_to_peak_background", "merge_interactions", "circular_genome", "overwrite")):
        raise FitHiChIPExecutionError("FitHiChIP Boolean parameters must be 0 or 1")
    if values["bin_size"] <= 0 or values["lower_distance"] < 0 or values["upper_distance"] <= values["lower_distance"] or not 0 < values["q_value"] <= 1:
        raise FitHiChIPExecutionError("FitHiChIP distance, bin, or q-value parameter is invalid")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", values["prefix"]):
        raise FitHiChIPExecutionError("prefix must contain only letters, numbers, dot, underscore, or dash")
    if output_dir.exists() or report_path.exists():
        raise FitHiChIPExecutionError("output directory and report path must not already exist")
    output_dir = output_dir.resolve()
    report_path = report_path.resolve()
    config_path = output_dir.parent / f".{output_dir.name}.fithichip.config"
    if config_path.exists():
        raise FitHiChIPExecutionError(f"generated config already exists: {config_path}")
    config = {
        "ValidPairs": valid_pairs, "Interval": "", "Matrix": "", "Bed": "", "HIC": "", "COOL": "",
        "ChrSizeFile": chrom_sizes, "PeakFile": peaks, "OutDir": output_dir,
        "CircularGenome": values["circular_genome"], "IntType": values["interaction_type"],
        "BINSIZE": values["bin_size"], "LowDistThr": values["lower_distance"], "UppDistThr": values["upper_distance"],
        "UseP2PBackgrnd": values["peak_to_peak_background"], "BiasType": values["bias_type"],
        "MergeInt": values["merge_interactions"], "QVALUE": values["q_value"], "PREFIX": values["prefix"],
        "OverWrite": values["overwrite"],
    }
    config_path.write_text("\n".join(f"{key}={value}" for key, value in config.items()) + "\n", encoding="utf-8")
    completed = subprocess.run(
        ["bash", str(root / "FitHiChIP_HiCPro.sh"), "-C", str(config_path)], cwd=root,
        capture_output=True, text=True, check=False, timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        raise FitHiChIPExecutionError(f"FitHiChIP failed: {completed.stderr[-4000:]}")
    significant = sorted(path for path in output_dir.rglob(f"{values['prefix']}.interactions_FitHiC_Q*.bed") if "WashU" not in path.name and path.stat().st_size > 0)
    all_loops = sorted(path for path in output_dir.rglob(f"{values['prefix']}.interactions_FitHiC.bed") if path.stat().st_size > 0)
    summaries = sorted(path for path in output_dir.rglob("*.html") if path.stat().st_size > 0)
    if not significant or not all_loops:
        raise FitHiChIPExecutionError("FitHiChIP completed without nonempty all-interaction and FDR-filtered loop tables")
    log = output_dir / "fithichip.execution.log"
    log.write_text("STDOUT\n" + completed.stdout + "\nSTDERR\n" + completed.stderr, encoding="utf-8")
    def records(paths: list[Path]) -> list[dict[str, Any]]:
        return [{"path": str(path.relative_to(output_dir)), "bytes": path.stat().st_size, "sha256": _sha256(path)} for path in paths]
    implementation = Path(__file__).resolve()
    report = {
        "schema_version": 1, "module_id": "bulk-three-dimensional-genome", "assay": assay, "passed": True,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "workflow": {"name": "FitHiChIP", "version": VERSION, "commit": COMMIT, "source": SOURCE},
        "implementation": {"path": str(implementation.relative_to(implementation.parents[2])), "sha256": _sha256(implementation)},
        "inputs": {"valid_pairs": _sha256(valid_pairs), "chrom_sizes": _sha256(chrom_sizes), "peak_file": _sha256(peaks)},
        "parameters": values, "generated_config_sha256": _sha256(config_path),
        "outputs": {"all_interactions": records(all_loops), "significant_interactions": records(significant), "summaries": records(summaries)},
        "provenance": {"log_sha256": _sha256(log)},
        "claim_boundary": "FitHiChIP calls enrichment- and background-model-dependent protein-anchored contacts; a significant loop is not regulatory causality.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
