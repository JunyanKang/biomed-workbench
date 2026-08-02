"""Pinned Cromwell/WDL adapter for the published rdshear NET-seq workflow."""

from __future__ import annotations

import hashlib
import gzip
import json
import re
import shutil
import subprocess
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


UPSTREAM_COMMIT = "ebcc7790c19041cb3da73f7a84965d8b4bf29a40"
UPSTREAM_WDL_SHA256 = "197ccd91ba5e73b83f142bae488b6458da0333cb3b7621004991cc9068b5b59c"
UPSTREAM_WDL_URL = f"https://raw.githubusercontent.com/rdshear/netseq/{UPSTREAM_COMMIT}/netseq.wdl"
UPSTREAM_REPOSITORY = "https://github.com/rdshear/netseq"
CROMWELL_VERSION = "88"
REQUIRED_OUTPUTS = (
    "output_bam", "bedgraph_pos", "bedgraph_neg", "mask_pos", "mask_neg",
    "alignment_log", "fastp_report_html", "fastp_report_json",
)
_DIGEST_IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$")
_SRA_RUN = re.compile(r"^(?:SRR|ERR|DRR)[0-9]+$")


class NetSeqExecutionError(ValueError):
    """Raised when the NET-seq workflow contract, run, or outputs are invalid."""


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _stable_file(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise NetSeqExecutionError(f"{label} must be a local file path")
    path = Path(value).expanduser()
    if path.is_symlink() or not path.is_file():
        raise NetSeqExecutionError(f"{label} must be a readable non-symlink file: {path}")
    return path.resolve()


def _wdl_bytes() -> bytes:
    request = urllib.request.Request(UPSTREAM_WDL_URL, headers={"User-Agent": "biomed-workbench/0.2 netseq-wdl"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def materialize_local_reference_wdl(destination: Path, *, source_bytes: bytes | None = None) -> dict[str, str]:
    """Derive a local-reference WDL through two reviewed deterministic edits."""
    payload = _wdl_bytes() if source_bytes is None else source_bytes
    observed = hashlib.sha256(payload).hexdigest()
    if observed != UPSTREAM_WDL_SHA256:
        raise NetSeqExecutionError(
            f"upstream NET-seq WDL digest changed: expected {UPSTREAM_WDL_SHA256}, observed {observed}"
        )
    text = payload.decode("utf-8")
    old_decl = 'String refFasta = "https://hgdownload.soe.ucsc.edu/goldenPath/sacCer3/bigZips/sacCer3.fa.gz"'
    task_decl = "        String refFasta\n"
    if (
        text.count(old_decl) != 1
        or text.count(task_decl) != 1
        or text.count("wget --quiet ~{refFasta} -O - | ${unzipFasta}") != 1
    ):
        raise NetSeqExecutionError("reviewed NET-seq WDL reference expressions were not found exactly once")
    text = text.replace(old_decl, "File refFasta")
    text = text.replace(task_decl, "        File refFasta\n")
    text = text.replace("wget --quiet ~{refFasta} -O - | ${unzipFasta}", "cat ~{refFasta} | ${unzipFasta}")
    destination.write_text(text, encoding="utf-8")
    return {
        "upstream_sha256": observed,
        "derived_sha256": sha256(destination),
        "reviewed_changes": (
            "workflow and task refFasta String declarations to localized File; "
            "wget stream to cat localized file"
        ),
    }


def _output_paths(metadata: dict[str, Any]) -> dict[str, Path]:
    outputs = metadata.get("outputs")
    if not isinstance(outputs, dict):
        raise NetSeqExecutionError("Cromwell metadata lacks outputs")
    resolved: dict[str, Path] = {}
    for name in REQUIRED_OUTPUTS:
        matches = [value for key, value in outputs.items() if str(key).endswith("." + name)]
        if len(matches) != 1 or not isinstance(matches[0], str):
            raise NetSeqExecutionError(f"Cromwell metadata does not uniquely declare {name}")
        path = Path(matches[0]).expanduser().resolve()
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise NetSeqExecutionError(f"NET-seq output is missing or empty: {path}")
        resolved[name] = path
    return resolved


class _HTMLReloadParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags = 0
        self.text = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags += 1

    def handle_data(self, data: str) -> None:
        self.text += len(data.strip())


def _reload_outputs(outputs: dict[str, Path]) -> dict[str, Any]:
    try:
        with gzip.open(outputs["output_bam"], "rb") as handle:
            if handle.read(4) != b"BAM\x01":
                raise NetSeqExecutionError("output_bam is not a reloadable BAM file")
    except (OSError, EOFError) as exc:
        raise NetSeqExecutionError("output_bam is not a reloadable BAM file") from exc

    bedgraph_rows: dict[str, int] = {}
    for name in ("bedgraph_pos", "bedgraph_neg", "mask_pos", "mask_neg"):
        rows = 0
        try:
            with gzip.open(outputs[name], "rt", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip() or line.startswith(("#", "track", "browser")):
                        continue
                    fields = line.rstrip("\n").split("\t")
                    if len(fields) < 4:
                        raise ValueError("fewer than four bedGraph columns")
                    start, end, value = int(fields[1]), int(fields[2]), float(fields[3])
                    if start < 0 or end <= start or not fields[0] or value != value:
                        raise ValueError("invalid bedGraph interval or value")
                    rows += 1
        except (OSError, EOFError, UnicodeError, ValueError) as exc:
            raise NetSeqExecutionError(f"{name} is not a reloadable gzip-compressed bedGraph") from exc
        bedgraph_rows[name] = rows
    if bedgraph_rows["bedgraph_pos"] + bedgraph_rows["bedgraph_neg"] == 0:
        raise NetSeqExecutionError("strand occupancy bedGraphs contain no intervals")

    try:
        fastp = json.loads(outputs["fastp_report_json"].read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NetSeqExecutionError("fastp JSON output is invalid") from exc
    if not isinstance(fastp, dict) or not isinstance(fastp.get("summary"), dict):
        raise NetSeqExecutionError("fastp JSON output lacks the summary object")

    parser = _HTMLReloadParser()
    try:
        parser.feed(outputs["fastp_report_html"].read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise NetSeqExecutionError("fastp HTML output is not reloadable") from exc
    if parser.tags < 2 or parser.text == 0:
        raise NetSeqExecutionError("fastp HTML output is empty or malformed")

    try:
        alignment_log = outputs["alignment_log"].read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise NetSeqExecutionError("STAR alignment log is not reloadable") from exc
    input_match = re.search(r"Number of input reads\s*\|\s*([0-9]+)", alignment_log)
    unique_match = re.search(r"Uniquely mapped reads number\s*\|\s*([0-9]+)", alignment_log)
    if not input_match or not unique_match:
        raise NetSeqExecutionError("STAR alignment log lacks required read-count fields")

    before = fastp.get("summary", {}).get("before_filtering", {})
    return {
        "bam_reloaded": True,
        "bedgraph_rows": bedgraph_rows,
        "fastp_json_reloaded": True,
        "fastp_html_reloaded": True,
        "fastp_reads_before_filtering": before.get("total_reads") if isinstance(before, dict) else None,
        "star_input_reads": int(input_match.group(1)),
        "star_uniquely_mapped_reads": int(unique_match.group(1)),
    }


def execute_netseq(
    request: dict[str, Any],
    *,
    output_dir: Path,
    report_path: Path,
    cromwell: str = "cromwell",
    timeout_seconds: int = 172800,
    _source_wdl_bytes: bytes | None = None,
) -> dict[str, Any]:
    output_dir = output_dir.expanduser().resolve()
    report_path = report_path.expanduser().resolve()
    if request.get("schema_version") != 1 or request.get("module_id") != "bulk-nascent-transcription":
        raise NetSeqExecutionError("request must target bulk-nascent-transcription schema version 1")
    if str(request.get("assay", "")).lower() != "net-seq":
        raise NetSeqExecutionError("this executor accepts only assay=net-seq")
    fastq_value = request.get("input_fastq")
    sra_value = request.get("sra_run_id")
    if bool(fastq_value) == bool(sra_value):
        raise NetSeqExecutionError("provide exactly one of input_fastq or sra_run_id")
    fastq = _stable_file(fastq_value, "input_fastq") if fastq_value else None
    sra_run = str(sra_value).strip().upper() if sra_value else None
    if sra_run and not _SRA_RUN.fullmatch(sra_run):
        raise NetSeqExecutionError("sra_run_id must be an SRR, ERR, or DRR run accession")
    reference = _stable_file(request.get("reference_fasta"), "reference_fasta")
    reference_sha = request.get("reference_sha256")
    if not isinstance(reference_sha, str) or reference_sha != sha256(reference):
        raise NetSeqExecutionError("reference_sha256 must match the localized reference FASTA")
    container = request.get("container_image")
    if not isinstance(container, str) or not _DIGEST_IMAGE.fullmatch(container):
        raise NetSeqExecutionError("container_image must be an immutable image@sha256 digest")
    parameters = request.get("parameters", {})
    if not isinstance(parameters, dict):
        raise NetSeqExecutionError("request.parameters must be an object")
    allowed = {
        "sample_name", "genome_name", "max_read_count", "adapter_sequence", "umi_width",
        "dup_calc_accuracy", "minimum_read_length", "out_sam_mult_nmax",
        "out_filter_multimap_nmax", "threads", "memory",
    }
    unknown = set(parameters) - allowed
    if unknown:
        raise NetSeqExecutionError("unknown NET-seq parameters: " + ", ".join(sorted(unknown)))
    values = {
        "sample_name": str(parameters.get("sample_name", sra_run or fastq.name.split(".fastq")[0])).strip(),
        "genome_name": str(parameters.get("genome_name", "custom")).strip(),
        "max_read_count": int(parameters.get("max_read_count", 0)),
        "adapter_sequence": str(parameters.get("adapter_sequence", "ATCTCGTATGCCGTCTTCTGCTTG")).strip().upper(),
        "umi_width": int(parameters.get("umi_width", 6)),
        "dup_calc_accuracy": int(parameters.get("dup_calc_accuracy", 3)),
        "minimum_read_length": int(parameters.get("minimum_read_length", 24)),
        "out_sam_mult_nmax": int(parameters.get("out_sam_mult_nmax", 1)),
        "out_filter_multimap_nmax": int(parameters.get("out_filter_multimap_nmax", 1)),
        "threads": int(parameters.get("threads", 4)),
        "memory": str(parameters.get("memory", "8G")).strip(),
    }
    if not values["sample_name"] or not values["genome_name"] or not re.fullmatch(r"[ACGTN]+", values["adapter_sequence"]):
        raise NetSeqExecutionError("sample_name, genome_name, or adapter_sequence is invalid")
    if values["max_read_count"] < 0 or values["umi_width"] < 0 or not 1 <= values["dup_calc_accuracy"] <= 5:
        raise NetSeqExecutionError("max_read_count, umi_width, or dup_calc_accuracy is outside the official range")
    if values["minimum_read_length"] < 1 or values["threads"] < 1:
        raise NetSeqExecutionError("minimum_read_length and threads must be positive")
    if values["out_sam_mult_nmax"] < 1 or values["out_filter_multimap_nmax"] < 1:
        raise NetSeqExecutionError("STAR multimapping parameters must be positive")
    if not re.fullmatch(r"[1-9][0-9]*(?:\.[0-9]+)?[KMGTP]i?B?", values["memory"], re.IGNORECASE):
        raise NetSeqExecutionError("memory must use a Cromwell-compatible size such as 8G")
    if output_dir.exists() or report_path.exists():
        raise NetSeqExecutionError("output directory and report path must not already exist")
    executable = shutil.which(cromwell) if "/" not in cromwell else str(_stable_file(cromwell, "cromwell executable"))
    if not executable:
        raise NetSeqExecutionError(f"Cromwell executable not found: {cromwell}")
    version = subprocess.run([executable, "--version"], capture_output=True, text=True, check=False, timeout=30)
    version_text = (version.stdout + version.stderr).strip()
    if version.returncode != 0 or not re.search(rf"(?:^|\s){CROMWELL_VERSION}(?:\s|$)", version_text):
        raise NetSeqExecutionError(f"Cromwell {CROMWELL_VERSION} is required; observed {version_text!r}")

    output_dir.mkdir(parents=True)
    provenance = output_dir / "provenance"
    provenance.mkdir()
    wdl_path = provenance / "netseq.local-reference.wdl"
    derivation = materialize_local_reference_wdl(wdl_path, source_bytes=_source_wdl_bytes)
    inputs = {
        "netseq.refFasta": str(reference),
        "netseq.sampleName": values["sample_name"], "netseq.genomeName": values["genome_name"],
        "netseq.maxReadCount": values["max_read_count"], "netseq.adapterSequence": values["adapter_sequence"],
        "netseq.umiWidth": values["umi_width"], "netseq.dupCalcAccuracy": values["dup_calc_accuracy"],
        "netseq.minimumReadLength": values["minimum_read_length"],
        "netseq.outSAMmultNmax": values["out_sam_mult_nmax"],
        "netseq.outFilterMultiMax": values["out_filter_multimap_nmax"],
        "netseq.threads": values["threads"], "netseq.memory": values["memory"],
        "netseq.preemptible": 0, "netseq.netseq_docker": container,
    }
    if fastq is not None:
        inputs["netseq.inputFastQ"] = str(fastq)
    else:
        inputs["netseq.sraRunId"] = sra_run
    inputs_path = provenance / "inputs.json"
    inputs_path.write_text(json.dumps(inputs, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    metadata_path = provenance / "metadata.json"
    argv = [executable, "run", "-i", str(inputs_path), "-t", "wdl", "-m", str(metadata_path), str(wdl_path)]
    completed = subprocess.run(
        argv, cwd=output_dir, capture_output=True, text=True, check=False, timeout=timeout_seconds
    )
    log_path = provenance / "cromwell.log"
    log_path.write_text(
        "$ " + " ".join(json.dumps(value) for value in argv) + "\n\nSTDOUT\n" + completed.stdout
        + "\nSTDERR\n" + completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0 or not metadata_path.is_file():
        raise NetSeqExecutionError(f"Cromwell NET-seq execution failed; see {log_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    outputs = _output_paths(metadata)
    reload_metrics = _reload_outputs(outputs)
    implementation = Path(__file__).resolve()
    output_records = {
        name: {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
        for name, path in outputs.items()
    }
    report = {
        "schema_version": 1, "module_id": "bulk-nascent-transcription", "assay": "net-seq",
        "passed": True, "executed_at": datetime.now(timezone.utc).isoformat(),
        "workflow": {
            "repository": UPSTREAM_REPOSITORY, "commit": UPSTREAM_COMMIT,
            "upstream_wdl_url": UPSTREAM_WDL_URL, **derivation,
            "runtime": "Cromwell", "runtime_version": version_text, "container_image": container,
        },
        "implementation": {"path": str(implementation.relative_to(implementation.parents[2])), "sha256": sha256(implementation)},
        "inputs": {
            **(
                {"fastq": {"path": str(fastq), "bytes": fastq.stat().st_size, "sha256": sha256(fastq)}}
                if fastq is not None else {"sra_run_id": sra_run}
            ),
            "reference_fasta": {"path": str(reference), "bytes": reference.stat().st_size, "sha256": reference_sha},
        },
        "parameters": values, "outputs": output_records,
        "reload_validation": reload_metrics,
        "provenance": {
            "inputs_json": {"path": str(inputs_path), "sha256": sha256(inputs_path)},
            "metadata": {"path": str(metadata_path), "sha256": sha256(metadata_path)},
            "log": {"path": str(log_path), "sha256": sha256(log_path)},
        },
        "interpretation_scope": (
            "The released configuration reproduces the authors' Saccharomyces cerevisiae sacCer3, hexamer-UMI design in a local Cromwell runtime. "
            "The same executable accepts project-specific references and UMI layouts while retaining them in provenance and project-level validation."
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
