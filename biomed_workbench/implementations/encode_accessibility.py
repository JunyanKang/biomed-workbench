"""Pinned ENCODE ATAC/DNase WDL execution through the official Caper API."""

from __future__ import annotations

import hashlib
import gzip
import json
import re
import shutil
import struct
import subprocess
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


PIPELINE_VERSION = "2.2.3"
PIPELINE_COMMIT = "47ba8dff9c332e24b48e767303e9fcac98589cf2"
CAPER_VERSION = "2.3.1"
SOURCE = "https://github.com/ENCODE-DCC/atac-seq-pipeline"


class EncodeAccessibilityExecutionError(ValueError):
    pass


class _HtmlStructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.add(tag.lower())


def _reloadable_html(path: Path) -> bool:
    parser = _HtmlStructureParser()
    try:
        parser.feed(path.read_text(encoding="utf-8", errors="strict"))
        parser.close()
    except (UnicodeDecodeError, ValueError):
        return False
    return "html" in parser.tags or {"h1", "table"}.issubset(parser.tags)


def _sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _file(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise EncodeAccessibilityExecutionError(f"{label} must be a local path")
    path = Path(value).expanduser()
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise EncodeAccessibilityExecutionError(f"{label} must be a nonempty non-symlink file: {path}")
    return path.resolve()


def _pipeline_root(value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise EncodeAccessibilityExecutionError("pipeline_root must identify the pinned ENCODE checkout")
    root = Path(value).expanduser().resolve()
    if not (root / "atac.wdl").is_file():
        raise EncodeAccessibilityExecutionError(f"atac.wdl is missing under {root}")
    observed = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False, timeout=30)
    if observed.returncode != 0 or observed.stdout.strip() != PIPELINE_COMMIT:
        raise EncodeAccessibilityExecutionError(f"ENCODE pipeline commit {PIPELINE_COMMIT} required")
    return root


def _fastq_replicates(value: object) -> tuple[list[dict[str, list[Path]]], bool]:
    if not isinstance(value, list) or not value or len(value) > 10:
        raise EncodeAccessibilityExecutionError("fastq_replicates must contain 1 to 10 biological replicates")
    rows: list[dict[str, list[Path]]] = []
    endedness: set[bool] = set()
    for index, row in enumerate(value, 1):
        if not isinstance(row, dict) or set(row) - {"fastq_1", "fastq_2"}:
            raise EncodeAccessibilityExecutionError(f"replicate {index} has unknown fields")
        r1 = row.get("fastq_1")
        r2 = row.get("fastq_2", [])
        if not isinstance(r1, list) or not r1 or not isinstance(r2, list):
            raise EncodeAccessibilityExecutionError(f"replicate {index} requires nonempty fastq_1 and optional fastq_2 arrays")
        if r2 and len(r1) != len(r2):
            raise EncodeAccessibilityExecutionError(f"replicate {index} FASTQ lane counts differ")
        endedness.add(bool(r2))
        rows.append({"fastq_1": [_file(path, f"replicate {index} fastq_1") for path in r1], "fastq_2": [_file(path, f"replicate {index} fastq_2") for path in r2]})
    if len(endedness) != 1:
        raise EncodeAccessibilityExecutionError("mixed single- and paired-end replicates require an explicit separate run")
    return rows, endedness.pop()


def _bam_replicates(value: object) -> list[dict[str, Any]]:
    """Validate the official ENCODE ``atac.bams`` biological-replicate input."""
    if not isinstance(value, list) or not value or len(value) > 10:
        raise EncodeAccessibilityExecutionError("bam_replicates must contain 1 to 10 biological replicates")
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(value, 1):
        if not isinstance(row, dict) or set(row) != {"bam", "paired_end"} or not isinstance(row["paired_end"], bool):
            raise EncodeAccessibilityExecutionError(
                f"BAM replicate {index} requires exactly bam and boolean paired_end fields"
            )
        bam = _file(row["bam"], f"BAM replicate {index}")
        with bam.open("rb") as raw:
            compressed_magic = raw.read(2)
        opener = gzip.open if compressed_magic == b"\x1f\x8b" else open
        with opener(bam, "rb") as handle:
            if handle.read(4) != b"BAM\x01":
                raise EncodeAccessibilityExecutionError(f"BAM replicate {index} is not a BAM/BGZF stream: {bam}")
            header_length_raw = handle.read(4)
            if len(header_length_raw) != 4:
                raise EncodeAccessibilityExecutionError(f"BAM replicate {index} has a truncated header: {bam}")
            header_length = struct.unpack("<i", header_length_raw)[0]
            header = handle.read(header_length).decode("utf-8", errors="replace")
        hd = next((line for line in header.splitlines() if line.startswith("@HD\t")), "")
        if "\tSO:coordinate" not in hd:
            raise EncodeAccessibilityExecutionError(
                f"BAM replicate {index} must be coordinate sorted for the official ENCODE atac.bams input: {bam}"
            )
        rows.append({"bam": bam, "paired_end": row["paired_end"]})
    return rows


def _bam_provenance(value: object) -> dict[str, Any]:
    required = {"producer", "producer_version", "source", "parameters", "source_files", "quality_files"}
    if not isinstance(value, dict) or set(value) != required:
        raise EncodeAccessibilityExecutionError(f"bam_provenance requires exactly {sorted(required)}")
    for key in ("producer", "producer_version", "source"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise EncodeAccessibilityExecutionError(f"bam_provenance.{key} must be a nonempty string")
    if not isinstance(value["parameters"], dict) or not value["parameters"]:
        raise EncodeAccessibilityExecutionError("bam_provenance.parameters must be a nonempty object")
    if not isinstance(value["source_files"], list) or not value["source_files"]:
        raise EncodeAccessibilityExecutionError("bam_provenance.source_files must be a nonempty path array")
    if not isinstance(value["quality_files"], list):
        raise EncodeAccessibilityExecutionError("bam_provenance.quality_files must be a path array")
    return {
        "producer": value["producer"].strip(),
        "producer_version": value["producer_version"].strip(),
        "source": value["source"].strip(),
        "parameters": value["parameters"],
        "source_files": [_file(path, "bam_provenance source file") for path in value["source_files"]],
        "quality_files": [_file(path, "bam_provenance quality file") for path in value["quality_files"]],
    }


def _primary_execution_files(output_dir: Path, predicate: Any) -> list[Path]:
    """Return canonical Cromwell task outputs without input or glob copies."""
    files: list[Path] = []
    for path in output_dir.rglob("*"):
        if not path.is_file() or path.stat().st_size == 0:
            continue
        relative_parts = path.relative_to(output_dir).parts
        if "execution" not in relative_parts or "inputs" in relative_parts:
            continue
        if any(part.startswith("glob-") for part in relative_parts):
            continue
        if predicate(path):
            files.append(path)
    return sorted(files)


def execute_encode_accessibility(
    request: dict[str, Any],
    *,
    output_dir: Path,
    report_path: Path,
    caper_executable: str = "caper",
    caper_config: Path | None = None,
    timeout_seconds: int = 172800,
) -> dict[str, Any]:
    assay = str(request.get("assay", "")).lower()
    if request.get("schema_version") != 1 or request.get("module_id") != "bulk-chromatin-accessibility" or assay not in {"atac-seq", "dnase-seq"}:
        raise EncodeAccessibilityExecutionError("request must target atac-seq or dnase-seq in bulk-chromatin-accessibility schema version 1")
    root = _pipeline_root(request.get("pipeline_root"))
    genome_tsv = _file(request.get("genome_tsv"), "genome_tsv")
    has_fastq = request.get("fastq_replicates") is not None
    has_bam = request.get("bam_replicates") is not None
    if has_fastq == has_bam:
        raise EncodeAccessibilityExecutionError("provide exactly one of fastq_replicates or bam_replicates")
    fastq_replicates: list[dict[str, list[Path]]] = []
    bam_replicates: list[dict[str, Any]] = []
    bam_provenance: dict[str, Any] | None = None
    paired_end: bool | None = None
    if has_fastq:
        fastq_replicates, paired_end = _fastq_replicates(request.get("fastq_replicates"))
    else:
        bam_replicates = _bam_replicates(request.get("bam_replicates"))
        bam_provenance = _bam_provenance(request.get("bam_provenance"))
    parameters = request.get("parameters", {})
    allowed = {"title", "description", "align_only", "true_rep_only", "auto_detect_adapter", "adapter", "enable_xcor", "enable_gc_bias", "enable_fraglen_stat", "enable_idr", "multimapping", "mapq_threshold", "duplicate_marker", "no_duplicate_removal", "peak_caller", "cap_number_peaks", "p_value_threshold", "idr_threshold", "fraglen_stat_picard_java_heap", "max_concurrent_tasks"}
    if not isinstance(parameters, dict) or set(parameters) - allowed:
        raise EncodeAccessibilityExecutionError("unknown ENCODE accessibility parameter")
    values = {
        "title": str(parameters.get("title", assay)), "description": str(parameters.get("description", f"{assay} analysis")),
        "align_only": bool(parameters.get("align_only", False)), "true_rep_only": bool(parameters.get("true_rep_only", False)),
        "auto_detect_adapter": bool(parameters.get("auto_detect_adapter", True)), "adapter": parameters.get("adapter"), "enable_xcor": bool(parameters.get("enable_xcor", False)),
        "enable_gc_bias": bool(parameters.get("enable_gc_bias", True)),
        "enable_fraglen_stat": bool(parameters.get("enable_fraglen_stat", True)),
        "enable_idr": bool(parameters.get("enable_idr", True)),
        "multimapping": int(parameters.get("multimapping", 4)), "mapq_threshold": int(parameters.get("mapq_threshold", 30)),
        "duplicate_marker": str(parameters.get("duplicate_marker", "picard")).lower(),
        "no_duplicate_removal": bool(parameters.get("no_duplicate_removal", False)), "peak_caller": str(parameters.get("peak_caller", "macs2")),
        "cap_number_peaks": int(parameters.get("cap_number_peaks", 300000)), "p_value_threshold": float(parameters.get("p_value_threshold", 0.01)),
        "idr_threshold": float(parameters.get("idr_threshold", 0.05)),
        "fraglen_stat_picard_java_heap": parameters.get("fraglen_stat_picard_java_heap"),
        "max_concurrent_tasks": int(parameters.get("max_concurrent_tasks", 1)),
    }
    if values["multimapping"] < 1 or values["mapq_threshold"] < 0 or values["duplicate_marker"] not in {"picard", "sambamba"} or values["cap_number_peaks"] < 1 or values["peak_caller"] != "macs2" or not 0 < values["p_value_threshold"] <= 1 or not 0 < values["idr_threshold"] <= 1 or values["max_concurrent_tasks"] < 1:
        raise EncodeAccessibilityExecutionError("ENCODE accessibility parameter is outside the official range")
    adapter = values["adapter"]
    if adapter is not None and (not isinstance(adapter, str) or not re.fullmatch(r"[ACGTN]+", adapter.upper())):
        raise EncodeAccessibilityExecutionError("adapter must be an IUPAC A/C/G/T/N sequence")
    heap = values["fraglen_stat_picard_java_heap"]
    if heap is not None and (not isinstance(heap, str) or not re.fullmatch(r"[1-9][0-9]*[GM]", heap)):
        raise EncodeAccessibilityExecutionError("fraglen_stat_picard_java_heap must use positive G or M units, for example 1G")
    if values["auto_detect_adapter"] and adapter:
        raise EncodeAccessibilityExecutionError("choose automatic adapter detection or a fixed adapter, not both")
    executable = shutil.which(caper_executable) if "/" not in caper_executable else str(_file(caper_executable, "caper executable"))
    if not executable:
        raise EncodeAccessibilityExecutionError(f"Caper executable not found: {caper_executable}")
    resolved_caper_config = _file(str(caper_config), "caper_config") if caper_config is not None else None
    version_probe = subprocess.run([executable, "--version"], capture_output=True, text=True, check=False, timeout=30)
    version_text = (version_probe.stdout + version_probe.stderr).strip()
    if version_probe.returncode != 0 or CAPER_VERSION not in version_text:
        raise EncodeAccessibilityExecutionError(f"Caper {CAPER_VERSION} required; observed {version_text!r}")
    if output_dir.exists() or report_path.exists():
        raise EncodeAccessibilityExecutionError("output directory and report path must not already exist")
    output_dir = output_dir.resolve(); report_path = report_path.resolve()
    input_json = output_dir.parent / f".{output_dir.name}.encode-accessibility.inputs.json"
    tmp_dir = output_dir.parent / f".{output_dir.name}.caper-tmp"
    if input_json.exists() or tmp_dir.exists():
        raise EncodeAccessibilityExecutionError("generated ENCODE input or temporary path already exists")
    inputs: dict[str, Any] = {
        "atac.title": values["title"], "atac.description": values["description"],
        "atac.pipeline_type": "atac" if assay == "atac-seq" else "dnase", "atac.genome_tsv": str(genome_tsv),
        "atac.paired_end": paired_end, "atac.align_only": values["align_only"], "atac.true_rep_only": values["true_rep_only"],
        "atac.auto_detect_adapter": values["auto_detect_adapter"], "atac.enable_xcor": values["enable_xcor"],
        "atac.enable_gc_bias": values["enable_gc_bias"], "atac.multimapping": values["multimapping"],
        "atac.mapq_thresh": values["mapq_threshold"], "atac.dup_marker": values["duplicate_marker"],
        "atac.no_dup_removal": values["no_duplicate_removal"],
        "atac.enable_fraglen_stat": values["enable_fraglen_stat"],
        "atac.enable_idr": values["enable_idr"],
        # ENCODE ATAC-seq pipeline 2.2.3 has a fixed MACS2 peak caller and no
        # ``atac.peak_caller`` WDL input.  Keep the validated user-facing value
        # in provenance without sending a nonexistent key to Womtool.
        "atac.cap_num_peak": values["cap_number_peaks"],
        "atac.pval_thresh": values["p_value_threshold"], "atac.idr_thresh": values["idr_threshold"],
    }
    if heap is not None:
        inputs["atac.fraglen_stat_picard_java_heap"] = heap
    if adapter:
        inputs["atac.adapter"] = adapter.upper()
    if fastq_replicates:
        inputs["atac.paired_end"] = paired_end
        for index, row in enumerate(fastq_replicates, 1):
            inputs[f"atac.fastqs_rep{index}_R1"] = [str(path) for path in row["fastq_1"]]
            if paired_end:
                inputs[f"atac.fastqs_rep{index}_R2"] = [str(path) for path in row["fastq_2"]]
    else:
        inputs["atac.bams"] = [str(row["bam"]) for row in bam_replicates]
        endedness = [bool(row["paired_end"]) for row in bam_replicates]
        if len(set(endedness)) == 1:
            inputs["atac.paired_end"] = endedness[0]
        else:
            inputs["atac.paired_ends"] = endedness
    input_json.write_text(json.dumps(inputs, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    metadata = output_dir / "metadata.json"
    argv = [executable, "run"]
    if resolved_caper_config is not None:
        argv.extend(["--conf", str(resolved_caper_config)])
    argv.extend([str(root / "atac.wdl"), "-i", str(input_json), "--docker", "--out-dir", str(output_dir), "--tmp-dir", str(tmp_dir), "--metadata-output", str(metadata), "--max-concurrent-tasks", str(values["max_concurrent_tasks"])])
    completed = subprocess.run(argv, cwd=root, capture_output=True, text=True, check=False, timeout=timeout_seconds)
    if completed.returncode != 0:
        raise EncodeAccessibilityExecutionError(f"ENCODE accessibility workflow failed: {completed.stderr[-4000:]}")
    if not metadata.is_file() or metadata.stat().st_size == 0:
        raise EncodeAccessibilityExecutionError("Caper completed without metadata.json")
    metadata_payload = json.loads(metadata.read_text(encoding="utf-8"))
    status = str(metadata_payload.get("status", metadata_payload.get("workflowStatus", "")))
    if status and status.lower() not in {"succeeded", "success"}:
        raise EncodeAccessibilityExecutionError(f"Caper metadata reports workflow status {status!r}")
    qc_json = _primary_execution_files(output_dir, lambda path: path.name.lower().endswith("qc.json"))
    qc_html = _primary_execution_files(output_dir, lambda path: path.name.lower().endswith("qc.html"))
    peaks = _primary_execution_files(
        output_dir,
        lambda path: path.name.lower().endswith(("narrowpeak.gz", "broadpeak.gz", "gappedpeak.gz")),
    )
    signals = _primary_execution_files(
        output_dir,
        lambda path: path.name.lower().endswith((".bigwig", ".bw")),
    )
    if not values["align_only"] and (not qc_json or not qc_html or not peaks or not signals):
        raise EncodeAccessibilityExecutionError("ENCODE workflow completed without QC JSON/HTML, peaks, and signal tracks")
    if values["align_only"] and (not qc_json or not qc_html):
        raise EncodeAccessibilityExecutionError("ENCODE align-only workflow completed without QC JSON/HTML")
    for path in qc_json:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise EncodeAccessibilityExecutionError(f"QC JSON is not an object: {path}")
    for path in qc_html:
        if not _reloadable_html(path):
            raise EncodeAccessibilityExecutionError(f"QC HTML is not reloadable: {path}")
    peak_rows = 0
    for path in peaks:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip() or line.startswith(("#", "track", "browser")):
                    continue
                fields = line.rstrip("\n").split("\t")
                if len(fields) < 3 or int(fields[1]) < 0 or int(fields[2]) <= int(fields[1]):
                    raise EncodeAccessibilityExecutionError(f"invalid peak interval in {path}")
                peak_rows += 1
    if peaks and peak_rows == 0:
        raise EncodeAccessibilityExecutionError("ENCODE peak files contain no intervals")
    for path in signals:
        if path.read_bytes()[:4] not in {b"\x26\xfc\x8f\x88", b"\x88\x8f\xfc\x26"}:
            raise EncodeAccessibilityExecutionError(f"signal track is not a reloadable bigWig: {path}")
    log = output_dir / "encode-accessibility.execution.log"
    log.write_text("STDOUT\n" + completed.stdout + "\nSTDERR\n" + completed.stderr, encoding="utf-8")
    def records(paths: list[Path]) -> list[dict[str, Any]]:
        unique = sorted(set(paths))
        return [{"path": str(path.relative_to(output_dir)), "bytes": path.stat().st_size, "sha256": _sha256(path)} for path in unique]
    implementation = Path(__file__).resolve()
    source_inputs = [
        genome_tsv,
        *[path for row in fastq_replicates for key in ("fastq_1", "fastq_2") for path in row[key]],
        *[row["bam"] for row in bam_replicates],
    ]
    report = {
        "schema_version": 1, "module_id": "bulk-chromatin-accessibility", "assay": assay, "passed": True,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "workflow": {"name": "ENCODE ATAC/DNase WDL", "version": PIPELINE_VERSION, "commit": PIPELINE_COMMIT, "source": SOURCE, "caper_version": CAPER_VERSION, "version_probe": version_text},
        "implementation": {"path": str(implementation.relative_to(implementation.parents[2])), "sha256": _sha256(implementation)},
        "inputs": [{"path": str(path), "bytes": path.stat().st_size, "sha256": _sha256(path)} for path in source_inputs],
        "parameters": values, "input_mode": "fastq" if fastq_replicates else "unfiltered_bam", "input_json_sha256": _sha256(input_json),
        "runtime": {"caper_config_sha256": _sha256(resolved_caper_config) if resolved_caper_config is not None else None},
        "outputs": {"metadata": records([metadata]), "qc_json": records(qc_json), "qc_html": records(qc_html), "peaks": records(peaks), "signals": records(signals)},
        "reloaded": {"qc_json_objects": len(qc_json), "qc_html_documents": len(qc_html), "peak_intervals": peak_rows, "bigwig_tracks": len(signals)},
        "provenance": {"log_sha256": _sha256(log)},
        "interpretation_scope": "Accessibility signal is assay- and enzyme-dependent; factor occupancy and enhancer causality require independent evidence beyond accessible peaks or footprints.",
    }
    if bam_provenance is not None:
        report["upstream_bam_provenance"] = {
            "producer": bam_provenance["producer"],
            "producer_version": bam_provenance["producer_version"],
            "source": bam_provenance["source"],
            "parameters": bam_provenance["parameters"],
            "source_files": [
                {"path": str(path), "bytes": path.stat().st_size, "sha256": _sha256(path)}
                for path in bam_provenance["source_files"]
            ],
            "quality_files": [
                {"path": str(path), "bytes": path.stat().st_size, "sha256": _sha256(path)}
                for path in bam_provenance["quality_files"]
            ],
        }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
