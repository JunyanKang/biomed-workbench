"""Raw FASTQ-to-cluster execution for the published LACE-seq protocol."""

from __future__ import annotations

import gzip
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from biomed_workbench.implementations.laceseq import execute_laceseq, sha256


METHOD_DOI = "10.1038/s41556-021-00696-9"
UPSTREAM_COMMIT = "b8d1193638190c50c8553847ad3a1653544dbe14"
CUTADAPT_115_IMAGE = "quay.io/biocontainers/cutadapt@sha256:949d08d76446d48af457b5d485ec4d93cb8f49fab407f9eb1e0e0104ebbc3777"
BOWTIE_123_IMAGE = "quay.io/biocontainers/bowtie@sha256:f29fc740b5d50d6b305c480c5eba5b42c28e0bfb7dd5d4b9b720ac529a5d61ee"
_DIGEST_IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$")


class LaceSeqFastqExecutionError(ValueError):
    """Raised when raw LACE-seq preprocessing or alignment cannot be completed."""


def _file(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise LaceSeqFastqExecutionError(f"{label} must be a local file path")
    path = Path(value).expanduser()
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise LaceSeqFastqExecutionError(f"{label} must be a nonempty non-symlink file: {path}")
    return path.resolve()


def _executable(value: str, label: str) -> str:
    resolved = shutil.which(value) if "/" not in value else str(Path(value).expanduser().resolve())
    if not resolved or not Path(resolved).is_file():
        raise LaceSeqFastqExecutionError(f"{label} executable not found: {value}")
    return resolved


def _index(prefix_value: object, label: str) -> tuple[Path, list[Path]]:
    if not isinstance(prefix_value, str) or not prefix_value.strip():
        raise LaceSeqFastqExecutionError(f"{label} must be a Bowtie 1 index prefix")
    prefix = Path(prefix_value).expanduser().resolve()
    parts = [Path(str(prefix) + suffix) for suffix in (".1.ebwt", ".2.ebwt", ".3.ebwt", ".4.ebwt", ".rev.1.ebwt", ".rev.2.ebwt")]
    if any(path.is_symlink() or not path.is_file() or path.stat().st_size == 0 for path in parts):
        raise LaceSeqFastqExecutionError(f"{label} is not a complete nonempty Bowtie 1 index: {prefix}")
    return prefix, parts


def _run(argv: list[str], *, log: Path, timeout_seconds: int) -> None:
    completed = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=timeout_seconds)
    with log.open("a", encoding="utf-8") as handle:
        handle.write("$ " + " ".join(json.dumps(item) for item in argv) + "\n")
        handle.write("STDOUT\n" + completed.stdout + "\nSTDERR\n" + completed.stderr + "\n")
    if completed.returncode != 0:
        raise LaceSeqFastqExecutionError(f"LACE-seq command failed with exit code {completed.returncode}; see {log}")


def _container_command(
    docker: str,
    *,
    platform: str,
    image: str,
    mounts: list[tuple[Path, bool]],
    argv: list[str],
) -> list[str]:
    command = [docker, "run", "--rm", "--platform", platform]
    seen: set[tuple[str, bool]] = set()
    for path, read_only in mounts:
        resolved = path.resolve()
        key = (str(resolved), read_only)
        if key in seen:
            continue
        seen.add(key)
        suffix = ":ro" if read_only else ""
        command.extend(["-v", f"{resolved}:{resolved}{suffix}"])
    return [*command, image, *argv]


def _fastq_records(path: Path) -> int:
    opener = gzip.open if path.suffix == ".gz" else open
    lines = 0
    with opener(path, "rt", encoding="utf-8", errors="strict") as handle:
        for raw in handle:
            lines += 1
            if lines % 4 == 1 and not raw.startswith("@"):
                raise LaceSeqFastqExecutionError(f"invalid FASTQ identifier in {path}")
    if lines == 0 or lines % 4:
        raise LaceSeqFastqExecutionError(f"FASTQ is empty or truncated: {path}")
    return lines // 4


def _sam_to_bed6(sam: Path, bed: Path) -> int:
    cigar_token = re.compile(r"(\d+)([MIDNSHP=X])")
    rows = 0
    with sam.open(encoding="utf-8") as source, bed.open("w", encoding="utf-8") as target:
        for raw in source:
            if raw.startswith("@"):
                continue
            fields = raw.rstrip("\n").split("\t")
            if len(fields) < 11:
                raise LaceSeqFastqExecutionError(f"invalid SAM alignment row in {sam}")
            flag = int(fields[1])
            if flag & 4:
                continue
            start = int(fields[3]) - 1
            reference_span = sum(int(size) for size, op in cigar_token.findall(fields[5]) if op in "MDN=X")
            if start < 0 or reference_span <= 0:
                raise LaceSeqFastqExecutionError(f"invalid mapped coordinate in {sam}")
            strand = "-" if flag & 16 else "+"
            target.write(f"{fields[2]}\t{start}\t{start + reference_span}\t{fields[0]}\t{fields[4]}\t{strand}\n")
            rows += 1
    if rows == 0:
        raise LaceSeqFastqExecutionError(f"Bowtie produced no mapped reads for {sam}")
    return rows


def _artifact(path: Path, *, records: int | None = None) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size == 0:
        raise LaceSeqFastqExecutionError(f"required LACE-seq artifact is missing or empty: {path}")
    value: dict[str, Any] = {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
    if records is not None:
        value["records"] = records
    return value


def execute_laceseq_fastq(
    request: dict[str, Any],
    *,
    output_dir: Path,
    report_path: Path,
    cutadapt: str = "cutadapt",
    bowtie: str = "bowtie",
    docker: str = "docker",
    timeout_seconds: int = 172800,
) -> dict[str, Any]:
    output_dir = output_dir.expanduser().resolve()
    report_path = report_path.expanduser().resolve()
    if request.get("schema_version") != 1 or request.get("module_id") != "bulk-rbp-rna-binding":
        raise LaceSeqFastqExecutionError("request must target bulk-rbp-rna-binding schema version 1")
    if str(request.get("assay", "")).lower() != "lace-seq":
        raise LaceSeqFastqExecutionError("this executor accepts only assay=lace-seq")
    experiment = _file(request.get("experiment_fastq"), "experiment_fastq")
    control = _file(request.get("control_fastq"), "control_fastq")
    reference_metadata = request.get("reference_metadata")
    if not isinstance(reference_metadata, dict) or set(reference_metadata) != {
        "rrna_fasta", "rrna_name", "rrna_source_url", "genome_fasta", "genome_build",
        "genome_scope", "genome_source_url"
    }:
        raise LaceSeqFastqExecutionError(
            "reference_metadata must declare source-bound rRNA and genome FASTA metadata"
        )
    rrna_fasta = _file(reference_metadata.get("rrna_fasta"), "reference_metadata.rrna_fasta")
    genome_fasta = _file(reference_metadata.get("genome_fasta"), "reference_metadata.genome_fasta")
    for name in ("rrna_name", "rrna_source_url", "genome_build", "genome_scope", "genome_source_url"):
        if not isinstance(reference_metadata.get(name), str) or not reference_metadata[name].strip():
            raise LaceSeqFastqExecutionError(f"reference_metadata.{name} must be a nonempty string")
    rrna_prefix, rrna_parts = _index(request.get("rrna_bowtie_index"), "rrna_bowtie_index")
    genome_prefix, genome_parts = _index(request.get("genome_bowtie_index"), "genome_bowtie_index")
    parameters = request.get("parameters", {})
    allowed = {"adapter_sequence", "quality_cutoff", "minimum_length", "maximum_n_fraction", "polya_length", "polya_rounds", "mismatches", "maximum_multihits", "threads", "merge_distance", "initial_rpm", "min_strand_reads"}
    if not isinstance(parameters, dict) or set(parameters) - allowed:
        raise LaceSeqFastqExecutionError("unknown LACE-seq FASTQ parameter")
    values = {
        "adapter_sequence": str(parameters.get("adapter_sequence", "ATCTCGTATGCCGTCTTCTGCTT")).upper(),
        "quality_cutoff": str(parameters.get("quality_cutoff", "30,0")),
        "minimum_length": int(parameters.get("minimum_length", 18)),
        "maximum_n_fraction": float(parameters.get("maximum_n_fraction", 0.25)),
        "polya_length": int(parameters.get("polya_length", 15)),
        "polya_rounds": int(parameters.get("polya_rounds", 2)),
        "mismatches": int(parameters.get("mismatches", 2)),
        "maximum_multihits": int(parameters.get("maximum_multihits", 10)),
        "threads": int(parameters.get("threads", 4)),
        "merge_distance": int(parameters.get("merge_distance", 200)),
        "initial_rpm": float(parameters.get("initial_rpm", 0.01)),
        "min_strand_reads": int(parameters.get("min_strand_reads", 20)),
    }
    if not re.fullmatch(r"[ACGTN]+", values["adapter_sequence"]) or not re.fullmatch(r"\d+(?:,\d+)?", values["quality_cutoff"]):
        raise LaceSeqFastqExecutionError("adapter_sequence or quality_cutoff is invalid")
    if values["minimum_length"] < 1 or not 0 <= values["maximum_n_fraction"] <= 1 or values["polya_length"] < 1 or values["polya_rounds"] < 1:
        raise LaceSeqFastqExecutionError("LACE-seq trimming parameter is outside its valid range")
    if not 0 <= values["mismatches"] <= 3 or values["maximum_multihits"] < 1 or values["threads"] < 1:
        raise LaceSeqFastqExecutionError("LACE-seq Bowtie parameter is outside its supported range")
    if output_dir.exists() or report_path.exists():
        raise LaceSeqFastqExecutionError("output directory and report path must not already exist")
    runtime = request.get("runtime", {"mode": "host"})
    if not isinstance(runtime, dict) or set(runtime) - {"mode", "platform", "cutadapt_image", "bowtie_image"}:
        raise LaceSeqFastqExecutionError("runtime must be a host or immutable-container runtime object")
    runtime_mode = str(runtime.get("mode", "host"))
    platform = str(runtime.get("platform", "linux/amd64"))
    cutadapt_image = str(runtime.get("cutadapt_image", CUTADAPT_115_IMAGE))
    bowtie_image = str(runtime.get("bowtie_image", BOWTIE_123_IMAGE))
    if runtime_mode == "containers":
        if platform != "linux/amd64" or not _DIGEST_IMAGE.fullmatch(cutadapt_image) or not _DIGEST_IMAGE.fullmatch(bowtie_image):
            raise LaceSeqFastqExecutionError("container mode requires linux/amd64 and immutable image@sha256 references")
        docker_exe = _executable(docker, "Docker")
        cutadapt_exe = "cutadapt"
        bowtie_exe = "bowtie"
        cutadapt_probe = [docker_exe, "run", "--rm", "--platform", platform, cutadapt_image, cutadapt_exe, "--version"]
        bowtie_probe = [docker_exe, "run", "--rm", "--platform", platform, bowtie_image, bowtie_exe, "--version"]
    elif runtime_mode == "host":
        docker_exe = ""
        cutadapt_exe = _executable(cutadapt, "cutadapt")
        bowtie_exe = _executable(bowtie, "bowtie")
        cutadapt_probe = [cutadapt_exe, "--version"]
        bowtie_probe = [bowtie_exe, "--version"]
    else:
        raise LaceSeqFastqExecutionError("runtime.mode must be host or containers")
    cutadapt_version = subprocess.run(cutadapt_probe, capture_output=True, text=True, check=False, timeout=60)
    bowtie_version = subprocess.run(bowtie_probe, capture_output=True, text=True, check=False, timeout=60)
    if cutadapt_version.returncode or bowtie_version.returncode:
        raise LaceSeqFastqExecutionError("cutadapt and Bowtie version probes must succeed")
    cutadapt_observed = cutadapt_version.stdout.strip()
    bowtie_observed = (bowtie_version.stdout + bowtie_version.stderr).strip().splitlines()[0]
    if cutadapt_observed != "1.15" or "version 1.2.3" not in bowtie_observed:
        raise LaceSeqFastqExecutionError(
            f"published LACE-seq runtime requires cutadapt 1.15 and Bowtie 1.2.3; observed {cutadapt_observed!r}, {bowtie_observed!r}"
        )
    output_dir.mkdir(parents=True)
    pre = output_dir / "preprocessing"; pre.mkdir()
    log = pre / "laceseq-fastq.log"
    container_mounts = [
        (output_dir, False), (experiment, True), (control, True),
        *[(path, True) for path in rrna_parts], *[(path, True) for path in genome_parts],
    ]
    def command(image: str, argv: list[str]) -> list[str]:
        if runtime_mode == "host":
            return argv
        return _container_command(
            docker_exe, platform=platform, image=image, mounts=container_mounts, argv=argv
        )
    input_records = {}
    bed_paths = {}
    alignment_counts = {}
    preprocessing_outputs = {}
    for label, source in (("experiment", experiment), ("control", control)):
        adapter_trimmed = pre / f"{label}.adapter-trimmed.fastq.gz"
        trimmed = pre / f"{label}.trimmed.fastq.gz"
        non_rrna = pre / f"{label}.non-rRNA.fastq"
        rrna_sam = pre / f"{label}.rRNA.sam"
        genome_sam = pre / f"{label}.genome.sam"
        bed = pre / f"{label}.genome.bed"
        _run(command(cutadapt_image, [cutadapt_exe, "-f", "fastq", "-q", values["quality_cutoff"], "-a", values["adapter_sequence"], "-m", str(values["minimum_length"]), "--max-n", str(values["maximum_n_fraction"]), "--trim-n", "-o", str(adapter_trimmed), str(source)]), log=log, timeout_seconds=timeout_seconds)
        _run(command(cutadapt_image, [cutadapt_exe, "-f", "fastq", "-a", f"A{{{values['polya_length']}}}", "-m", str(values["minimum_length"]), "-n", str(values["polya_rounds"]), "-o", str(trimmed), str(adapter_trimmed)]), log=log, timeout_seconds=timeout_seconds)
        _run(command(bowtie_image, [bowtie_exe, "-q", "-p", str(values["threads"]), "--un", str(non_rrna), "-S", str(rrna_prefix), str(trimmed), str(rrna_sam)]), log=log, timeout_seconds=timeout_seconds)
        _run(command(bowtie_image, [bowtie_exe, "-q", "-v", str(values["mismatches"]), "-m", str(values["maximum_multihits"]), "--best", "--strata", "-p", str(values["threads"]), "-S", str(genome_prefix), str(non_rrna), str(genome_sam)]), log=log, timeout_seconds=timeout_seconds)
        mapped = _sam_to_bed6(genome_sam, bed)
        input_records[label] = {"path": str(source), "bytes": source.stat().st_size, "sha256": sha256(source), "reads": _fastq_records(source)}
        bed_paths[label] = bed
        alignment_counts[label] = {"post_trim_reads": _fastq_records(trimmed), "non_rrna_reads": _fastq_records(non_rrna), "mapped_bed_rows": mapped}
        preprocessing_outputs[label] = {
            "adapter_trimmed_fastq": _artifact(adapter_trimmed, records=_fastq_records(adapter_trimmed)),
            "trimmed_fastq": _artifact(trimmed, records=alignment_counts[label]["post_trim_reads"]),
            "non_rrna_fastq": _artifact(non_rrna, records=alignment_counts[label]["non_rrna_reads"]),
            "rrna_sam": _artifact(rrna_sam),
            "genome_sam": _artifact(genome_sam),
            "genome_bed": _artifact(bed, records=mapped),
        }
    cluster_request = {
        "schema_version": 1, "module_id": "bulk-rbp-rna-binding", "assay": "lace-seq",
        "experiment_bed": str(bed_paths["experiment"]), "control_bed": str(bed_paths["control"]),
        "parameters": {key: values[key] for key in ("merge_distance", "initial_rpm", "min_strand_reads")},
    }
    cluster_report_path = output_dir / "cluster-execution.json"
    cluster_report = execute_laceseq(cluster_request, output_dir=output_dir / "clusters", report_path=cluster_report_path)
    implementation = Path(__file__).resolve()
    dockerfile = implementation.parents[1] / "runtime_compat" / "laceseq" / "Dockerfile"
    report = {
        "schema_version": 1, "module_id": "bulk-rbp-rna-binding", "assay": "lace-seq", "passed": True,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "method": {
            "name": "LACE-seq FASTQ preprocessing, Bowtie alignment and cluster calling",
            "doi": METHOD_DOI,
            "upstream_repository": "https://github.com/caochch/LACEseq",
            "upstream_commit": UPSTREAM_COMMIT,
        },
        "software": {"cutadapt": cutadapt_observed, "bowtie": bowtie_observed},
        "runtime": {
            "mode": runtime_mode,
            "platform": platform if runtime_mode == "containers" else None,
            "cutadapt_image": cutadapt_image if runtime_mode == "containers" else None,
            "bowtie_image": bowtie_image if runtime_mode == "containers" else None,
            "dockerfile": {
                "path": str(dockerfile.relative_to(implementation.parents[2])),
                "sha256": sha256(dockerfile),
            } if runtime_mode == "containers" else None,
        },
        "parameters": values,
        "inputs": input_records,
        "references": {
            "rrna": {
                "name": reference_metadata["rrna_name"],
                "source_url": reference_metadata["rrna_source_url"],
                "fasta": _artifact(rrna_fasta),
                "index_prefix": str(rrna_prefix),
                "index_parts": {p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)} for p in rrna_parts},
            },
            "genome": {
                "build": reference_metadata["genome_build"],
                "scope": reference_metadata["genome_scope"],
                "source_url": reference_metadata["genome_source_url"],
                "fasta": _artifact(genome_fasta),
                "index_prefix": str(genome_prefix),
                "index_parts": {p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)} for p in genome_parts},
            },
        },
        "preprocessing": alignment_counts,
        "preprocessing_outputs": preprocessing_outputs,
        "clusters": cluster_report["metrics"],
        "cluster_stage": {
            "method": cluster_report["method"],
            "implementation": cluster_report["implementation"],
        },
        "outputs": {
            "cluster_report": {
                "path": str(cluster_report_path), "bytes": cluster_report_path.stat().st_size,
                "sha256": sha256(cluster_report_path),
            },
            **cluster_report["outputs"],
        },
        "implementation": {"path": str(implementation.relative_to(implementation.parents[2])), "sha256": sha256(implementation)},
        "provenance": {"log": {"path": str(log), "sha256": sha256(log)}},
        "interpretation_scope": "The released path follows the published sequential adapter/poly(A) trimming, pre-rRNA depletion, Bowtie mapping and matched-control cluster logic. The antibody, input amount, reference build and independent replicates remain explicit project design variables.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
