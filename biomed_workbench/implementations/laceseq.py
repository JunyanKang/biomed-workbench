"""No-edit LACE-seq read-cluster calling with provenance and reload checks.

The implementation reproduces the interval logic published with LACE-seq at
the pinned upstream revision, while replacing its hard-coded paths, shared
temporary filenames, and destructive cleanup with typed project inputs.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


UPSTREAM_REPOSITORY = "https://github.com/caochch/LACEseq"
UPSTREAM_COMMIT = "b8d1193638190c50c8553847ad3a1653544dbe14"


class LaceSeqExecutionError(ValueError):
    """Raised when LACE-seq inputs or reloaded outputs violate the contract."""


@dataclass(frozen=True, order=True)
class BedRead:
    chrom: str
    start: int
    end: int
    name: str
    score: str
    strand: str


@dataclass(frozen=True)
class Cluster:
    chrom: str
    start: int
    end: int
    plus_reads: int
    minus_reads: int
    strand: str
    strand_reads: int
    strand_rpm: float


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _input_file(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise LaceSeqExecutionError(f"{label} must be a local BED6 path")
    path = Path(value).expanduser()
    if path.is_symlink() or not path.is_file():
        raise LaceSeqExecutionError(f"{label} must be a readable non-symlink file: {path}")
    return path.resolve()


def read_bed6(path: Path) -> list[BedRead]:
    reads: dict[tuple[str, int, int, str], BedRead] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip() or raw.startswith(("#", "track", "browser")):
                continue
            fields = raw.rstrip("\n").split("\t")
            if len(fields) < 6:
                raise LaceSeqExecutionError(f"{path}:{line_number} is not BED6")
            try:
                start, end = int(fields[1]), int(fields[2])
            except ValueError as exc:
                raise LaceSeqExecutionError(f"{path}:{line_number} has non-integer coordinates") from exc
            if not fields[0] or start < 0 or end <= start:
                raise LaceSeqExecutionError(f"{path}:{line_number} has invalid half-open coordinates")
            if fields[5] not in {"+", "-"}:
                raise LaceSeqExecutionError(f"{path}:{line_number} requires + or - strand")
            key = (fields[0], start, end, fields[5])
            reads.setdefault(key, BedRead(fields[0], start, end, fields[3], fields[4], fields[5]))
    if not reads:
        raise LaceSeqExecutionError(f"BED6 input has no reads: {path}")
    return sorted(reads.values())


def merge_intervals(reads: Iterable[BedRead], distance: int) -> list[tuple[str, int, int]]:
    if distance < 0:
        raise LaceSeqExecutionError("merge_distance must be >= 0")
    intervals = sorted((read.chrom, read.start, read.end) for read in reads)
    merged: list[tuple[str, int, int]] = []
    for chrom, start, end in intervals:
        if merged and merged[-1][0] == chrom and start <= merged[-1][2] + distance:
            old_chrom, old_start, old_end = merged[-1]
            merged[-1] = (old_chrom, old_start, max(old_end, end))
        else:
            merged.append((chrom, start, end))
    return merged


def subtract_intervals(
    reads: Iterable[BedRead], controls: Iterable[tuple[str, int, int]]
) -> list[BedRead]:
    """Match upstream unstranded ``bedtools intersect -v`` semantics."""
    by_chrom: dict[str, list[tuple[int, int]]] = {}
    for chrom, start, end in controls:
        by_chrom.setdefault(chrom, []).append((start, end))
    remaining: list[BedRead] = []
    for read in reads:
        overlaps_control = any(
            control_start < read.end and control_end > read.start
            for control_start, control_end in by_chrom.get(read.chrom, [])
        )
        if not overlaps_control:
            remaining.append(read)
    return sorted(remaining)


def call_clusters(
    reads: list[BedRead],
    *,
    denominator_reads: int,
    merge_distance: int,
    initial_rpm: float,
    min_strand_reads: int,
) -> list[Cluster]:
    if denominator_reads <= 0:
        raise LaceSeqExecutionError("RPM denominator must be positive")
    if initial_rpm < 0 or min_strand_reads < 1:
        raise LaceSeqExecutionError("initial_rpm must be >= 0 and min_strand_reads must be >= 1")
    candidates = merge_intervals(reads, merge_distance)
    clusters: list[Cluster] = []
    for chrom, start, end in candidates:
        overlapping = [
            read for read in reads
            if read.chrom == chrom and read.start < end and read.end > start
        ]
        plus = sum(read.strand == "+" for read in overlapping)
        minus = sum(read.strand == "-" for read in overlapping)
        # LACE-seq reads report the reverse-transcription product orientation:
        # upstream assigns RNA '+' when minus-strand alignments predominate.
        if minus > plus:
            strand, strand_reads = "+", minus
        else:
            strand, strand_reads = "-", plus
        rpm = strand_reads * 1_000_000.0 / denominator_reads
        if rpm >= initial_rpm and max(plus, minus) >= min_strand_reads:
            clusters.append(Cluster(chrom, start, end, plus, minus, strand, strand_reads, rpm))
    return clusters


def _write_reads(path: Path, reads: Iterable[BedRead]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for read in reads:
            handle.write(
                f"{read.chrom}\t{read.start}\t{read.end}\t{read.name}\t{read.score}\t{read.strand}\n"
            )


def _output_record(path: Path, *, rows: int) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size == 0:
        raise LaceSeqExecutionError(f"declared output is missing or empty: {path}")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path), "rows": rows}


def execute_laceseq(request: dict[str, Any], *, output_dir: Path, report_path: Path) -> dict[str, Any]:
    if request.get("schema_version") != 1 or request.get("module_id") != "bulk-rbp-rna-binding":
        raise LaceSeqExecutionError("request must target bulk-rbp-rna-binding schema version 1")
    if str(request.get("assay", "")).lower() != "lace-seq":
        raise LaceSeqExecutionError("this executor accepts only assay=lace-seq")
    experiment_path = _input_file(request.get("experiment_bed"), "experiment_bed")
    control_path = _input_file(request.get("control_bed"), "control_bed")
    parameters = request.get("parameters", {})
    if not isinstance(parameters, dict):
        raise LaceSeqExecutionError("request.parameters must be an object")
    unknown = set(parameters) - {"merge_distance", "initial_rpm", "min_strand_reads"}
    if unknown:
        raise LaceSeqExecutionError("unknown LACE-seq parameters: " + ", ".join(sorted(unknown)))
    merge_distance = int(parameters.get("merge_distance", 200))
    initial_rpm = float(parameters.get("initial_rpm", 0.01))
    min_strand_reads = int(parameters.get("min_strand_reads", 20))
    if output_dir.exists():
        raise LaceSeqExecutionError(f"output directory already exists: {output_dir}")
    if report_path.exists():
        raise LaceSeqExecutionError(f"report already exists: {report_path}")

    experiment = read_bed6(experiment_path)
    control = read_bed6(control_path)
    # The pinned upstream command first runs plain ``bedtools merge`` for IgG,
    # then applies the adjustable distance only when joining experiment seeds.
    control_merged = merge_intervals(control, 0)
    cleaned = subtract_intervals(experiment, control_merged)
    if not cleaned:
        raise LaceSeqExecutionError("control subtraction removed every LACE-seq read")
    clusters = call_clusters(
        cleaned,
        denominator_reads=len(cleaned),
        merge_distance=merge_distance,
        initial_rpm=initial_rpm,
        min_strand_reads=min_strand_reads,
    )

    output_dir.mkdir(parents=True)
    cleaned_path = output_dir / "control_subtracted_reads.bed"
    cluster_bed = output_dir / "lace_clusters.bed"
    cluster_tsv = output_dir / "lace_clusters.tsv"
    metrics_path = output_dir / "lace_metrics.json"
    _write_reads(cleaned_path, cleaned)
    with cluster_bed.open("w", encoding="utf-8") as handle:
        for index, cluster in enumerate(clusters, 1):
            handle.write(
                f"{cluster.chrom}\t{cluster.start}\t{cluster.end}\tLACE_cluster_{index}\t"
                f"{cluster.strand_reads}\t{cluster.strand}\n"
            )
    with cluster_tsv.open("w", encoding="utf-8") as handle:
        handle.write("cluster_id\tchrom\tstart\tend\tstrand\tplus_reads\tminus_reads\tstrand_reads\tstrand_rpm\n")
        for index, cluster in enumerate(clusters, 1):
            handle.write(
                f"LACE_cluster_{index}\t{cluster.chrom}\t{cluster.start}\t{cluster.end}\t{cluster.strand}\t"
                f"{cluster.plus_reads}\t{cluster.minus_reads}\t{cluster.strand_reads}\t{cluster.strand_rpm:.8f}\n"
            )
    metrics = {
        "experiment_unique_reads": len(experiment),
        "control_unique_reads": len(control),
        "control_merged_intervals": len(control_merged),
        "control_filtered_unique_reads": len(cleaned),
        "retained_clusters": len(clusters),
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    implementation_path = Path(__file__).resolve()
    report = {
        "schema_version": 1,
        "module_id": "bulk-rbp-rna-binding",
        "assay": "lace-seq",
        "passed": True,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "method": {
            "name": "LACE-seq strand-aware read-cluster calling",
            "upstream_repository": UPSTREAM_REPOSITORY,
            "upstream_commit": UPSTREAM_COMMIT,
            "coordinate_semantics": "BED zero-based half-open",
            "control_subtraction": "whole-read exclusion on any unstranded overlap, matching upstream bedtools intersect -v",
            "deduplication": "chromosome, start, end, and alignment strand, matching the pinned Perl workflow",
            "strand_assignment": "minus-strand alignments imply plus-strand RNA; ties resolve to minus, matching upstream",
            "parameters": {
                "merge_distance": merge_distance,
                "initial_rpm": initial_rpm,
                "min_strand_reads": min_strand_reads,
            },
        },
        "implementation": {
            "path": str(implementation_path.relative_to(implementation_path.parents[2])),
            "sha256": sha256(implementation_path),
        },
        "inputs": {
            "experiment_bed": _output_record(experiment_path, rows=len(experiment)),
            "control_bed": _output_record(control_path, rows=len(control)),
        },
        "metrics": metrics,
        "outputs": {
            "control_subtracted_reads": _output_record(cleaned_path, rows=len(cleaned)),
            "clusters_bed": _output_record(cluster_bed, rows=len(clusters)) if clusters else {
                "path": str(cluster_bed), "bytes": 0, "sha256": sha256(cluster_bed), "rows": 0
            },
            "clusters_tsv": _output_record(cluster_tsv, rows=len(clusters)),
            "metrics": _output_record(metrics_path, rows=1),
        },
        "interpretation_scope": (
            "This executor calls LACE-seq read clusters from aligned BED6 reads after matched-control subtraction. "
            "Raw FASTQ projects enter through the companion LACE-seq FASTQ executor, which performs the published trimming, pre-rRNA depletion and Bowtie mapping steps before this cluster stage."
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
