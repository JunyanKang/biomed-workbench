"""Strict validation for bounded VCF region-query evidence."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re


class VCFReportError(ValueError):
    """Raised when queried VCF evidence violates its declared contract."""


_REGION_RE = re.compile(r"([^:\s]+):(\d+)-(\d+)")


def _end_from_info(position: int, ref: str, info: str) -> int:
    for field in info.split(";"):
        if field.startswith("END="):
            try:
                end = int(field[4:])
            except ValueError as exc:
                raise VCFReportError("VCF END is not an integer") from exc
            if end < position:
                raise VCFReportError("VCF END precedes POS")
            return end
    return position + max(len(ref), 1) - 1


def parse_tabix_vcf_query(
    path: Path | str,
    *,
    region: str,
    expected_fileformat: str = "VCFv4.5",
    expected_samples: tuple[str, ...] | None = None,
    expected_tool_version: str = "1.23",
) -> dict[str, object]:
    """Validate a header-preserving tabix region query and summarize its records."""
    match = _REGION_RE.fullmatch(region)
    if match is None:
        raise VCFReportError("region must use reference:start-end syntax")
    region_contig, region_start_text, region_end_text = match.groups()
    region_start, region_end = int(region_start_text), int(region_end_text)
    if region_start < 1 or region_end < region_start:
        raise VCFReportError("region violates one-based inclusive coordinates")
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise VCFReportError("queried VCF cannot be read") from exc
    if not lines or lines[0] != f"##fileformat={expected_fileformat}":
        raise VCFReportError("VCF fileformat declaration is missing or incompatible")
    contigs = set()
    header = None
    records = []
    for number, line in enumerate(lines, start=1):
        if line.startswith("##contig=<ID="):
            contig = line.removeprefix("##contig=<ID=").split(",", 1)[0].split(">", 1)[0]
            if not contig:
                raise VCFReportError("VCF contig declaration is empty")
            contigs.add(contig)
            continue
        if line.startswith("##"):
            continue
        if line.startswith("#CHROM\t"):
            if header is not None:
                raise VCFReportError("VCF contains duplicate column headers")
            header = line.split("\t")
            if header[:8] != ["#CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER", "INFO"]:
                raise VCFReportError("VCF fixed columns are invalid")
            if len(header) == 9 or (len(header) > 9 and header[8] != "FORMAT"):
                raise VCFReportError("VCF genotype columns require FORMAT and at least one sample")
            continue
        if line.startswith("#") or header is None:
            raise VCFReportError(f"unexpected VCF content at line {number}")
        fields = line.split("\t")
        if len(fields) != len(header) or len(fields) < 8:
            raise VCFReportError(f"VCF record {number} has an invalid column count")
        contig, position_text, _identifier, ref, alt, _quality, filter_value, info = fields[:8]
        try:
            position = int(position_text)
        except ValueError as exc:
            raise VCFReportError(f"VCF record {number} has an invalid POS") from exc
        if position < 1 or not ref or not alt or alt == "." or any(value == "" for value in fields):
            raise VCFReportError(f"VCF record {number} has an invalid allele or empty field")
        end = _end_from_info(position, ref, info)
        if contig != region_contig or end < region_start or position > region_end:
            raise VCFReportError(f"VCF record {number} falls outside the declared region")
        records.append((contig, position, end, ref, alt, filter_value))
    if header is None:
        raise VCFReportError("VCF column header is missing")
    if region_contig not in contigs:
        raise VCFReportError("queried reference is absent from VCF contig declarations")
    samples = tuple(header[9:]) if len(header) > 9 else ()
    if expected_samples is not None and samples != expected_samples:
        raise VCFReportError("VCF sample identity or order differs from the declared manifest")
    order = [(contig, position) for contig, position, *_rest in records]
    if order != sorted(order, key=lambda item: item[1]):
        raise VCFReportError("queried VCF records are not coordinate sorted")
    type_counts = Counter()
    filter_counts = Counter()
    for _contig, _position, _end, ref, alt, filter_value in records:
        alleles = alt.split(",")
        if len(ref) == 1 and all(len(allele) == 1 and not allele.startswith("<") for allele in alleles):
            type_counts["snv"] += 1
        elif all(not allele.startswith("<") for allele in alleles):
            type_counts["indel_or_mnv"] += 1
        else:
            type_counts["symbolic"] += 1
        filter_counts[filter_value] += 1
    return {
        "schema_version": 1,
        "tool": "tabix",
        "tool_version": expected_tool_version,
        "fileformat": expected_fileformat,
        "region": region,
        "coordinate_system": "one-based-inclusive",
        "record_count": len(records),
        "sample_count": len(samples),
        "samples": list(samples),
        "type_counts": dict(sorted(type_counts.items())),
        "filter_counts": dict(sorted(filter_counts.items())),
        "empty_result": not records,
        "header_preserved": True,
        "downstream_readiness": "technically-ready-pending-reference-and-analysis-design-review",
        "interpretation_policy": "Regional retrieval preserves selected records but does not validate variant calling, normalization, annotation, genotype quality, cohort design, or clinical significance.",
    }
