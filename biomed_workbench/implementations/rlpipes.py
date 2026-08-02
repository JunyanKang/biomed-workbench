"""Pinned RLPipes execution adapter for assay-aware R-loop mapping."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RL_PIPES_VERSION = "0.9.3"
RL_PIPES_COMMIT = "b1f864e52c48e164c059b40afc450a5726c147e7"
RL_PIPES_REPOSITORY = "https://github.com/Bishop-Laboratory/RLPipes"
ASSAY_MODES = {
    "drip-seq": "DRIP",
    "dripc-seq": "DRIPc",
    "sdrip-seq": "sDRIP",
    "qdrip-seq": "qDRIP",
    "r-chip": "R-ChIP",
    "mapr": "MapR",
}
_ACCESSION = re.compile(r"^(?:SR[RX]\d+|GSM\d+)$", re.IGNORECASE)


class RLPipesExecutionError(ValueError):
    """Raised when an RLPipes request, run, or reloaded result is invalid."""


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _local_file(value: str, label: str) -> Path:
    path = Path(value).expanduser()
    if path.is_symlink() or not path.is_file():
        raise RLPipesExecutionError(f"{label} is not a readable non-symlink file: {path}")
    return path.resolve()


def validate_samplesheet(path: Path, *, allow_public_accessions: bool) -> tuple[int, list[dict[str, Any]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "experiment" not in reader.fieldnames:
            raise RLPipesExecutionError("RLPipes samples CSV requires an experiment column")
        rows = list(reader)
    if not rows:
        raise RLPipesExecutionError("RLPipes samples CSV is empty")
    inputs: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, 2):
        for column in ("experiment", "control"):
            value = str(row.get(column, "") or "").strip()
            if not value:
                if column == "experiment":
                    raise RLPipesExecutionError(f"samples row {row_number} lacks experiment")
                continue
            for member in value.split("~"):
                if _ACCESSION.fullmatch(member):
                    if not allow_public_accessions:
                        raise RLPipesExecutionError(
                            "public accessions are disabled for project runs; materialize and checksum local inputs first"
                        )
                    inputs.append({"accession": member.upper(), "column": column, "row": row_number})
                else:
                    resolved = _local_file(member, f"samples row {row_number} {column}")
                    inputs.append({
                        "path": str(resolved), "column": column, "row": row_number,
                        "bytes": resolved.stat().st_size, "sha256": sha256(resolved),
                    })
    return len(rows), inputs


def _run(argv: list[str], *, timeout_seconds: int, log_path: Path) -> None:
    completed = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=timeout_seconds)
    log_path.write_text(
        "$ " + " ".join(json.dumps(value) for value in argv) + "\n\nSTDOUT\n" + completed.stdout
        + "\nSTDERR\n" + completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RLPipesExecutionError(
            f"RLPipes stage failed with exit code {completed.returncode}; see {log_path}"
        )


def _records(paths: list[Path], root: Path) -> list[dict[str, Any]]:
    return [
        {"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(paths)
    ]


def execute_rlpipes(
    request: dict[str, Any],
    *,
    output_dir: Path,
    report_path: Path,
    executable: str = "RLPipes",
    timeout_seconds: int = 172800,
) -> dict[str, Any]:
    if request.get("schema_version") != 1 or request.get("module_id") != "bulk-r-loop-mapping":
        raise RLPipesExecutionError("request must target bulk-r-loop-mapping schema version 1")
    assay = str(request.get("assay", "")).lower()
    if assay not in ASSAY_MODES:
        raise RLPipesExecutionError(
            "RLPipes executor supports drip-seq, dripc-seq, sdrip-seq, qdrip-seq, r-chip, and mapr"
        )
    samples = _local_file(str(request.get("samples_csv", "")), "samples_csv")
    genome = str(request.get("genome", "")).strip()
    if not genome:
        raise RLPipesExecutionError("request.genome is required for checksum-bound local inputs")
    parameters = request.get("parameters", {})
    if not isinstance(parameters, dict):
        raise RLPipesExecutionError("request.parameters must be an object")
    allowed = {"threads", "debug", "bwamem2", "macs3", "groupby", "no_expression_match", "no_report", "use_aws_instead_of_sra", "conda_prefix"}
    unknown = set(parameters) - allowed
    if unknown:
        raise RLPipesExecutionError("unknown RLPipes parameters: " + ", ".join(sorted(unknown)))
    threads = int(parameters.get("threads", 1))
    if threads < 1:
        raise RLPipesExecutionError("threads must be >= 1")
    for name in ("debug", "bwamem2", "macs3", "no_expression_match", "no_report", "use_aws_instead_of_sra"):
        if name in parameters and not isinstance(parameters[name], bool):
            raise RLPipesExecutionError(f"parameters.{name} must be boolean")
    groupby = parameters.get("groupby")
    if groupby is not None and (not isinstance(groupby, str) or not groupby.strip()):
        raise RLPipesExecutionError("parameters.groupby must be a nonempty column name")
    conda_prefix = parameters.get("conda_prefix")
    if conda_prefix is not None and (not isinstance(conda_prefix, str) or not conda_prefix.startswith("/")):
        raise RLPipesExecutionError("parameters.conda_prefix must be an absolute path in the isolated runtime")
    allow_public = request.get("allow_public_accessions", False)
    if not isinstance(allow_public, bool):
        raise RLPipesExecutionError("allow_public_accessions must be boolean")
    sample_count, input_records = validate_samplesheet(samples, allow_public_accessions=allow_public)
    if output_dir.exists() or report_path.exists():
        raise RLPipesExecutionError("output directory and report path must not already exist")
    resolved_executable = shutil.which(executable) if "/" not in executable else str(_local_file(executable, "RLPipes executable"))
    if not resolved_executable:
        raise RLPipesExecutionError(f"RLPipes executable not found: {executable}")
    version = subprocess.run([resolved_executable, "--version"], capture_output=True, text=True, check=False, timeout=30)
    version_text = (version.stdout + version.stderr).strip()
    if version.returncode != 0 or RL_PIPES_VERSION not in version_text:
        raise RLPipesExecutionError(f"RLPipes {RL_PIPES_VERSION} is required; observed {version_text!r}")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    logs = output_dir.parent / f"{output_dir.name}.logs"
    if logs.exists():
        raise RLPipesExecutionError(f"log directory already exists: {logs}")
    logs.mkdir()
    build = [resolved_executable, "build", "-m", ASSAY_MODES[assay], "-g", genome, str(output_dir), str(samples)]
    snakemake_arguments: dict[str, object] = {"use_conda": True, "conda_frontend": "mamba"}
    if conda_prefix:
        snakemake_arguments["conda_prefix"] = conda_prefix
    common = ["-s", repr(snakemake_arguments), "-t", str(threads)]
    flag_map = {
        "debug": "--debug", "bwamem2": "--bwamem2", "macs3": "--macs3",
        "no_expression_match": "--noexp", "no_report": "--noreport",
        "use_aws_instead_of_sra": "--useaws",
    }
    for key, flag in flag_map.items():
        if parameters.get(key) is True:
            common.append(flag)
    if groupby:
        common.extend(["-G", groupby])
    _run(build, timeout_seconds=300, log_path=logs / "01_build.log")
    _run([resolved_executable, "check", *common, str(output_dir)], timeout_seconds=3600, log_path=logs / "02_check.log")
    _run([resolved_executable, "run", *common, str(output_dir)], timeout_seconds=timeout_seconds, log_path=logs / "03_run.log")

    coverage = list(output_dir.glob("coverage/*.bw"))
    peaks = list(output_dir.glob("peaks/*.broadPeak"))
    bams = list(output_dir.glob("bam/**/*.bam")) + list(output_dir.glob("wrangled_bam/**/*.bam"))
    reports = list(output_dir.glob("rlseq_report/*.html"))
    if not coverage or not peaks or not bams:
        raise RLPipesExecutionError("RLPipes completed without required coverage, peak, and BAM outputs")
    for path in coverage:
        if path.read_bytes()[:4] != b"\x26\xfc\x8f\x88":
            raise RLPipesExecutionError(f"invalid BigWig signature: {path}")
    for path in peaks:
        with path.open(encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, 1):
                if raw.strip() and len(raw.rstrip("\n").split("\t")) < 3:
                    raise RLPipesExecutionError(f"invalid broadPeak interval at {path}:{line_number}")
    if not parameters.get("no_report", False) and not reports:
        raise RLPipesExecutionError("RLSeq HTML report was requested but not produced")
    implementation = Path(__file__).resolve()
    report = {
        "schema_version": 1,
        "module_id": "bulk-r-loop-mapping",
        "assay": assay,
        "passed": True,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "workflow": {
            "name": "RLPipes", "version": RL_PIPES_VERSION, "commit": RL_PIPES_COMMIT,
            "repository": RL_PIPES_REPOSITORY, "mode": ASSAY_MODES[assay], "version_probe": version_text,
        },
        "implementation": {
            "path": str(implementation.relative_to(implementation.parents[2])), "sha256": sha256(implementation),
        },
        "inputs": {
            "samples_csv": {"path": str(samples), "bytes": samples.stat().st_size, "sha256": sha256(samples), "rows": sample_count},
            "source_files": input_records,
            "genome": genome,
        },
        "parameters": {"threads": threads, **parameters},
        "outputs": {
            "coverage": _records(coverage, output_dir), "peaks": _records(peaks, output_dir),
            "bam": _records(bams, output_dir), "rlseq_reports": _records(reports, output_dir),
            "logs": _records(list(logs.glob("*.log")), logs),
        },
        "interpretation_scope": (
            "RLPipes output is assay- and sensor-dependent R-loop mapping evidence; locus-specific structure and function "
            "still require RNase H-sensitive controls and orthogonal validation."
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
