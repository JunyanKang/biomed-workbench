"""MultiQC runtime probes and bounded aggregate report parser."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path, PurePosixPath


class MultiQCReportError(ValueError):
    """Raised when aggregate QC evidence is unsafe or structurally incomplete."""


def _multiqc_interpreter() -> Path:
    executable = shutil.which("multiqc")
    if executable is None:
        raise RuntimeError("MultiQC executable is unavailable")
    first_line = Path(executable).read_text(encoding="utf-8", errors="strict").splitlines()[0]
    if not first_line.startswith("#!"):
        raise RuntimeError("MultiQC launcher has no interpreter")
    interpreter = Path(first_line[2:].strip())
    if not interpreter.is_absolute() or not interpreter.is_file() or not os.access(interpreter, os.X_OK):
        raise RuntimeError("MultiQC interpreter is unavailable")
    return interpreter


def _probe(code: str, *, timeout_seconds: int) -> str:
    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    completed = subprocess.run(
        [str(_multiqc_interpreter()), "-c", code],
        capture_output=True,
        text=True,
        check=True,
        timeout=timeout_seconds,
    )
    return completed.stdout.strip()


def probe_multiqc_python(*, timeout_seconds: int) -> str:
    return _probe("import platform; print(platform.python_version())", timeout_seconds=timeout_seconds)


def _probe_package(name: str, timeout_seconds: int) -> str:
    return _probe(f"from importlib.metadata import version; print(version('{name}'))", timeout_seconds=timeout_seconds)


def probe_multiqc_pydantic(*, timeout_seconds: int) -> str:
    return _probe_package("pydantic", timeout_seconds)


def probe_multiqc_plotly(*, timeout_seconds: int) -> str:
    return _probe_package("plotly", timeout_seconds)


def probe_multiqc_pyarrow(*, timeout_seconds: int) -> str:
    return _probe_package("pyarrow", timeout_seconds)


def probe_multiqc_polars(*, timeout_seconds: int) -> str:
    return _probe_package("polars", timeout_seconds)


def probe_multiqc_jsonschema(*, timeout_seconds: int) -> str:
    return _probe_package("jsonschema", timeout_seconds)


def probe_multiqc_jinja2(*, timeout_seconds: int) -> str:
    return _probe_package("jinja2", timeout_seconds)


def parse_multiqc_archive(path: Path | str, *, expected_version: str = "1.35") -> dict[str, object]:
    """Return a deterministic, path-free summary of one MultiQC data archive."""
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if not members or len(members) > 5000 or sum(item.file_size for item in members) > 100_000_000:
                raise MultiQCReportError("MultiQC archive size or entry count is invalid")
            for item in members:
                member = PurePosixPath(item.filename)
                mode = item.external_attr >> 16
                if member.is_absolute() or ".." in member.parts or "\\" in item.filename or (mode & 0o170000) == 0o120000:
                    raise MultiQCReportError("MultiQC archive contains an unsafe entry")
            data_members = [item for item in members if PurePosixPath(item.filename).name == "multiqc_data.json"]
            version_members = [item for item in members if PurePosixPath(item.filename).name == "multiqc_software_versions.json"]
            if len(data_members) != 1 or len(version_members) != 1:
                raise MultiQCReportError("MultiQC archive omits required data or version evidence")
            data = json.loads(archive.read(data_members[0]).decode("utf-8"))
            software = json.loads(archive.read(version_members[0]).decode("utf-8"))
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MultiQCReportError("MultiQC archive cannot be read") from exc
    if not isinstance(data, dict) or str(data.get("config_version")) != expected_version:
        raise MultiQCReportError("MultiQC report version is incompatible")
    general = data.get("report_general_stats_data")
    if not isinstance(general, dict) or not isinstance(general.get("fastqc"), dict) or not general["fastqc"]:
        raise MultiQCReportError("MultiQC report contains no FastQC sample statistics")
    fastqc_versions = software.get("FastQC") or software.get("fastqc")
    if isinstance(fastqc_versions, dict):
        fastqc_versions = [version for values in fastqc_versions.values() for version in (values if isinstance(values, list) else [values])]
    elif not isinstance(fastqc_versions, list):
        fastqc_versions = [fastqc_versions] if fastqc_versions else []
    if not fastqc_versions:
        raise MultiQCReportError("MultiQC report omits FastQC software-version evidence")
    samples = {}
    required_metrics = {"total_sequences", "percent_gc", "avg_sequence_length", "percent_duplicates", "percent_fails"}
    for sample_id, metrics in sorted(general["fastqc"].items()):
        if not isinstance(sample_id, str) or not sample_id or not isinstance(metrics, dict) or not required_metrics <= set(metrics):
            raise MultiQCReportError("MultiQC FastQC sample statistics are incomplete")
        normalized = {key: float(metrics[key]) for key in sorted(required_metrics)}
        if normalized["total_sequences"] <= 0 or not 0 <= normalized["percent_gc"] <= 100 or not 0 <= normalized["percent_fails"] <= 100:
            raise MultiQCReportError("MultiQC FastQC metrics are outside valid ranges")
        samples[sample_id] = normalized
    flagged = [sample_id for sample_id, metrics in samples.items() if metrics["percent_fails"] > 0]
    return {
        "schema_version": 1,
        "multiqc_version": expected_version,
        "fastqc_versions": sorted(str(value) for value in fastqc_versions),
        "sample_count": len(samples),
        "samples": samples,
        "flagged_samples": flagged,
        "downstream_readiness": "requires-assay-aware-review" if flagged else "technically-ready-pending-design-review",
        "interpretation_policy": "Aggregate QC prioritizes cross-sample outliers but does not replace assay-aware review of individual FastQC modules.",
    }
