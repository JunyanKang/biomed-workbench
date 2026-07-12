"""Version-specific parsing for samtools alignment quality reports."""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
import shutil
import subprocess


class AlignmentQualityReportError(ValueError):
    """Raised when an alignment quality report is incomplete or inconsistent."""


def probe_bwa_version(*, timeout_seconds: int) -> str:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    executable = shutil.which("bwa")
    if executable is None:
        raise RuntimeError("bwa is unavailable")
    completed = subprocess.run([executable], text=True, capture_output=True, check=False, timeout=timeout_seconds)
    match = re.search(r"Version: ([0-9]+(?:\.[0-9]+)+-r[0-9]+)", f"{completed.stdout}\n{completed.stderr}")
    if not match:
        raise RuntimeError("bwa version output is unavailable")
    return match.group(1)


def probe_bwa_homebrew_bottle(*, timeout_seconds: int) -> str:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    executable = shutil.which("bwa")
    if executable is None:
        raise RuntimeError("bwa is unavailable")
    receipt = Path(executable).resolve().parent.parent / "INSTALL_RECEIPT.json"
    try:
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        version = payload["source"]["versions"]["stable"]
        arch = payload["arch"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("bwa Homebrew receipt is unavailable or invalid") from exc
    if payload.get("built_as_bottle") is not True or payload.get("poured_from_bottle") is not True or version != "0.7.19" or arch != "arm64":
        raise RuntimeError("bwa Homebrew bottle identity is incompatible")
    return f"{version}-bottle-{arch}"


_COUNT_FIELDS = (
    "total", "primary", "secondary", "supplementary", "duplicates", "primary duplicates", "mapped",
    "primary mapped", "paired in sequencing", "read1", "read2", "properly paired",
    "with itself and mate mapped", "singletons", "with mate mapped to a different chr",
    "with mate mapped to a different chr (mapQ >= 5)",
)


def _section(payload: object, name: str) -> dict[str, object]:
    if not isinstance(payload, dict) or set(payload) != {"QC-passed reads", "QC-failed reads"}:
        raise AlignmentQualityReportError("flagstat report must contain exact QC pass and fail sections")
    section = payload[name]
    if not isinstance(section, dict):
        raise AlignmentQualityReportError(f"{name} section is not an object")
    if not set(_COUNT_FIELDS) <= set(section):
        raise AlignmentQualityReportError(f"{name} section omits required count fields")
    for field in _COUNT_FIELDS:
        value = section[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise AlignmentQualityReportError(f"{name} contains an invalid {field} count")
    if section["primary"] + section["secondary"] + section["supplementary"] != section["total"]:
        raise AlignmentQualityReportError(f"{name} read classes do not sum to total")
    if section["read1"] + section["read2"] != section["paired in sequencing"]:
        raise AlignmentQualityReportError(f"{name} paired read classes are inconsistent")
    bounds = {
        "duplicates": section["total"],
        "primary duplicates": section["primary"],
        "mapped": section["total"],
        "primary mapped": section["primary"],
        "properly paired": section["paired in sequencing"],
        "singletons": section["paired in sequencing"],
    }
    if any(section[field] > denominator for field, denominator in bounds.items()):
        raise AlignmentQualityReportError(f"{name} contains a count larger than its denominator")
    percentage_fields = {
        "mapped %": (section["mapped"], section["total"]),
        "primary mapped %": (section["primary mapped"], section["primary"]),
        "properly paired %": (section["properly paired"], section["paired in sequencing"]),
        "singletons %": (section["singletons"], section["paired in sequencing"]),
    }
    for field, (numerator, denominator) in percentage_fields.items():
        observed = section.get(field)
        expected = _percent(numerator, denominator)
        if expected is None:
            if observed is not None:
                raise AlignmentQualityReportError(f"{name} {field} must be null without a denominator")
        elif not isinstance(observed, (int, float)) or isinstance(observed, bool) or not math.isfinite(observed) or abs(observed - expected) > 0.01:
            raise AlignmentQualityReportError(f"{name} {field} differs from its counts")
    return section


def _percent(numerator: int, denominator: int) -> float | None:
    return round(100.0 * numerator / denominator, 6) if denominator else None


def parse_samtools_flagstat_report(path: Path | str, *, expected_version: str = "1.23") -> dict[str, object]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AlignmentQualityReportError("samtools flagstat JSON cannot be read") from exc
    passed = _section(payload, "QC-passed reads")
    failed = _section(payload, "QC-failed reads")
    counts = {field: passed[field] + failed[field] for field in _COUNT_FIELDS}
    total = counts["total"]
    if total <= 0:
        raise AlignmentQualityReportError("flagstat report contains no reads")
    primary = counts["primary"]
    paired = counts["paired in sequencing"]
    metrics = {
        "mapped_percent": _percent(counts["mapped"], total),
        "primary_mapped_percent": _percent(counts["primary mapped"], primary),
        "duplicate_percent": _percent(counts["duplicates"], total),
        "properly_paired_percent": _percent(counts["properly paired"], paired),
        "singleton_percent": _percent(counts["singletons"], paired),
        "qc_failed_percent": _percent(failed["total"], total),
    }
    if any(value is not None and (not math.isfinite(value) or value < 0 or value > 100) for value in metrics.values()):
        raise AlignmentQualityReportError("derived flagstat percentages are invalid")
    return {
        "schema_version": 1,
        "samtools_version": expected_version,
        "counts": counts,
        "metrics": metrics,
        "paired_end_observed": paired > 0,
        "downstream_readiness": "technically-ready-pending-design-and-reference-review",
        "interpretation_policy": "Flag statistics qualify alignment mechanics only; assay design, reference choice, read groups, coverage, bias, and biological adequacy require separate checks.",
    }


def _header_fields(line: str) -> dict[str, str]:
    fields = {}
    for field in line.split("\t")[1:]:
        if ":" not in field:
            raise AlignmentQualityReportError("SAM header field is malformed")
        key, value = field.split(":", 1)
        if not key or key in fields or not value:
            raise AlignmentQualityReportError("SAM header fields are invalid or duplicated")
        fields[key] = value
    return fields


def parse_bwa_mem_sam(
    path: Path | str,
    *,
    expected_version: str,
    expected_sample_id: str,
    reference_sequences: dict[str, int],
    expected_read_count: int,
) -> dict[str, object]:
    if not expected_sample_id or expected_read_count <= 0 or not reference_sequences:
        raise AlignmentQualityReportError("BWA SAM expectations are incomplete")
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise AlignmentQualityReportError("BWA SAM output cannot be read") from exc
    hd = []
    sq = {}
    rg = []
    pg = []
    records = []
    for line in lines:
        if line.startswith("@HD\t"):
            hd.append(_header_fields(line))
        elif line.startswith("@SQ\t"):
            fields = _header_fields(line)
            try:
                length = int(fields["LN"])
                name = fields["SN"]
            except (KeyError, ValueError) as exc:
                raise AlignmentQualityReportError("SAM sequence dictionary is invalid") from exc
            if name in sq or length <= 0:
                raise AlignmentQualityReportError("SAM sequence dictionary is duplicated or invalid")
            sq[name] = length
        elif line.startswith("@RG\t"):
            rg.append(_header_fields(line))
        elif line.startswith("@PG\t"):
            pg.append(_header_fields(line))
        elif line.startswith("@") or not line:
            raise AlignmentQualityReportError("SAM contains an unsupported header or blank record")
        else:
            records.append(line.split("\t"))
    if hd != [{"VN": "1.5", "SO": "unsorted", "GO": "query"}]:
        raise AlignmentQualityReportError("BWA SAM @HD contract differs from the validated release")
    if sq != reference_sequences:
        raise AlignmentQualityReportError("SAM sequence dictionary differs from the reference manifest")
    matching_rg = [item for item in rg if item.get("ID") == expected_sample_id and item.get("SM") == expected_sample_id]
    if len(matching_rg) != 1:
        raise AlignmentQualityReportError("SAM read group does not uniquely preserve sample identity")
    matching_pg = [item for item in pg if item.get("PN") == "bwa" and item.get("VN") == expected_version]
    if len(matching_pg) != 1:
        raise AlignmentQualityReportError("SAM program record does not identify the validated BWA version")
    command_line = matching_pg[0].get("CL", "")
    if any(token.startswith(("/", "file://")) for token in command_line.split()):
        raise AlignmentQualityReportError("SAM program record contains a machine-absolute path")
    counts = {"total": 0, "mapped": 0, "unmapped": 0, "primary": 0, "secondary": 0, "supplementary": 0}
    query_names = set()
    for fields in records:
        if len(fields) < 11:
            raise AlignmentQualityReportError("SAM alignment record has fewer than 11 fields")
        try:
            flag, position, mapping_quality = int(fields[1]), int(fields[3]), int(fields[4])
        except ValueError as exc:
            raise AlignmentQualityReportError("SAM flag, position, or mapping quality is invalid") from exc
        if flag < 0 or mapping_quality < 0 or mapping_quality > 255:
            raise AlignmentQualityReportError("SAM flag or mapping quality is out of range")
        tags = fields[11:]
        if f"RG:Z:{expected_sample_id}" not in tags:
            raise AlignmentQualityReportError("SAM record omits the validated sample read group")
        query_names.add(fields[0])
        counts["total"] += 1
        if flag & 0x100:
            counts["secondary"] += 1
        elif flag & 0x800:
            counts["supplementary"] += 1
        else:
            counts["primary"] += 1
        if flag & 0x4:
            if fields[2] != "*" or position != 0 or fields[5] != "*":
                raise AlignmentQualityReportError("unmapped SAM record has mapped coordinates or CIGAR")
            counts["unmapped"] += 1
        else:
            if fields[2] not in reference_sequences or position < 1 or position > reference_sequences[fields[2]] or fields[5] == "*":
                raise AlignmentQualityReportError("mapped SAM record violates reference coordinates or CIGAR")
            counts["mapped"] += 1
    if len(query_names) != expected_read_count or counts["primary"] != expected_read_count or counts["total"] < expected_read_count:
        raise AlignmentQualityReportError("SAM read accounting differs from the input FASTQ")
    return {
        "schema_version": 1,
        "bwa_version": expected_version,
        "sam_header_version": "1.5",
        "sample_id": expected_sample_id,
        "reference_sequences": dict(sorted(reference_sequences.items())),
        "counts": counts,
        "primary_mapping_percent": round(100.0 * counts["mapped"] / counts["primary"], 6),
        "program_record_paths": "workdir-relative",
        "downstream_readiness": "technically-ready-for-sam-to-sorted-bam-validation",
        "interpretation_policy": "BWA-MEM alignment is a technical transformation; reference suitability, read-group design, duplicate handling, mapping ambiguity, coverage, and assay-specific biological adequacy require downstream validation.",
    }
