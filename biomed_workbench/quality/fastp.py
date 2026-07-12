"""fastp Bioconda build probe and deterministic QC-only report parser."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


class FastPReportError(ValueError):
    """Raised when a fastp report is incomplete or is not a QC-only execution."""


def probe_fastp_bioconda_build(*, timeout_seconds: int) -> str:
    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    executable = shutil.which("fastp")
    if executable is None:
        raise RuntimeError("fastp executable is unavailable")
    prefix = Path(executable).resolve().parent.parent
    records = sorted((prefix / "conda-meta").glob("fastp-*.json"))
    if len(records) != 1:
        raise RuntimeError("fastp Bioconda package record is unavailable or ambiguous")
    payload = json.loads(records[0].read_text(encoding="utf-8"))
    if payload.get("name") != "fastp" or not payload.get("version") or not payload.get("build"):
        raise RuntimeError("fastp Bioconda package record is invalid")
    return f"{payload['version']}-{payload['build']}"


def parse_fastp_report(path: Path | str, *, expected_version: str = "1.3.6") -> dict[str, object]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FastPReportError("fastp JSON report cannot be read") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("summary"), dict):
        raise FastPReportError("fastp JSON report structure is incomplete")
    summary = payload["summary"]
    if summary.get("fastp_version") != expected_version:
        raise FastPReportError("fastp report version is incompatible")
    before = summary.get("before_filtering")
    after = summary.get("after_filtering")
    duplication = payload.get("duplication")
    if not isinstance(before, dict) or not isinstance(after, dict) or not isinstance(duplication, dict):
        raise FastPReportError("fastp summary or duplication metrics are incomplete")
    required = {"total_reads", "total_bases", "q20_rate", "q30_rate", "read1_mean_length", "gc_content"}
    if not required <= set(before) or not required <= set(after) or "rate" not in duplication:
        raise FastPReportError("fastp required QC metrics are absent")
    command = payload.get("command")
    required_flags = {
        "--disable_adapter_trimming",
        "--disable_quality_filtering",
        "--disable_length_filtering",
        "--disable_trim_poly_g",
    }
    if not isinstance(command, str) or not all(flag in command.split() for flag in required_flags):
        raise FastPReportError("fastp report was not generated with the validated QC-only contract")
    if before["total_reads"] <= 0 or before["total_reads"] != after["total_reads"] or before["total_bases"] != after["total_bases"]:
        raise FastPReportError("fastp QC-only execution changed or omitted reads")
    for values in (before, after):
        if not 0 <= float(values["q20_rate"]) <= 1 or not 0 <= float(values["q30_rate"]) <= 1 or not 0 <= float(values["gc_content"]) <= 1:
            raise FastPReportError("fastp rates are outside valid ranges")
    metrics = {
        "total_reads": int(before["total_reads"]),
        "total_bases": int(before["total_bases"]),
        "q20_rate": float(before["q20_rate"]),
        "q30_rate": float(before["q30_rate"]),
        "mean_read1_length": float(before["read1_mean_length"]),
        "gc_fraction": float(before["gc_content"]),
        "duplication_rate": float(duplication["rate"]),
    }
    flagged = []
    if metrics["q30_rate"] < 0.8:
        flagged.append("low-q30-rate")
    if metrics["duplication_rate"] > 0.5:
        flagged.append("high-duplication-rate")
    return {
        "schema_version": 1,
        "fastp_version": expected_version,
        "sequencing": str(summary.get("sequencing", "")),
        "qc_only_read_accounting_passed": True,
        "metrics": metrics,
        "flagged_metrics": flagged,
        "contamination_screening": {
            "status": "not-assessed",
            "reason": "fastp composition and overrepresentation metrics do not establish taxonomic contamination.",
        },
        "downstream_readiness": "requires-assay-aware-review" if flagged else "technically-ready-pending-design-review",
        "interpretation_policy": "fastp QC metrics complement but do not replace FastQC modules, taxonomic screening, or assay-specific review.",
    }
