"""Strict validation for bounded VCF region-query evidence."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re


class VCFReportError(ValueError):
    """Raised when queried VCF evidence violates its declared contract."""


_REGION_RE = re.compile(r"([^:\s]+):(\d+)-(\d+)")


def parse_vcf_document(
    path: Path | str,
    *,
    expected_fileformat: str = "VCFv4.5",
    expected_samples: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """Validate the stable document-level structure of a coordinate-sorted VCF."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise VCFReportError("VCF document cannot be read") from exc
    if not lines or lines[0] != f"##fileformat={expected_fileformat}":
        raise VCFReportError("VCF fileformat declaration is missing or incompatible")
    contigs = []
    header = None
    records = []
    previous = None
    for number, line in enumerate(lines, start=1):
        if line.startswith("##contig=<ID="):
            contig = line.removeprefix("##contig=<ID=").split(",", 1)[0].split(">", 1)[0]
            if not contig or contig in contigs:
                raise VCFReportError("VCF contig declaration is invalid")
            contigs.append(contig)
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
                raise VCFReportError("VCF genotype columns require FORMAT and samples")
            continue
        if not line or line.startswith("#") or header is None:
            raise VCFReportError(f"unexpected VCF content at line {number}")
        fields = line.split("\t")
        if len(fields) != len(header):
            raise VCFReportError(f"VCF record {number} has an invalid column count")
        try:
            position = int(fields[1])
        except ValueError as exc:
            raise VCFReportError(f"VCF record {number} has an invalid POS") from exc
        if fields[0] not in contigs or position < 1 or not fields[3] or not fields[4]:
            raise VCFReportError(f"VCF record {number} has an invalid contig, position, or allele")
        order = (contigs.index(fields[0]), position)
        if previous is not None and order < previous:
            raise VCFReportError("VCF records are not coordinate sorted")
        previous = order
        records.append(fields)
    if header is None or not contigs:
        raise VCFReportError("VCF column header or contig dictionary is missing")
    samples = tuple(header[9:]) if len(header) > 9 else ()
    if expected_samples is not None and samples != expected_samples:
        raise VCFReportError("VCF sample identity or order differs from the declared manifest")
    return {
        "schema_version": 1,
        "fileformat": expected_fileformat,
        "record_count": len(records),
        "contigs": contigs,
        "sample_count": len(samples),
        "samples": list(samples),
        "coordinate_system": "one-based-inclusive",
        "coordinate_sorted": True,
    }


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


def parse_vcf_filter_outputs(
    vcf_path: Path | str,
    report_path: Path | str,
    *,
    expected_parameters: dict[str, object],
    expected_samples: tuple[str, ...],
    expected_input_count: int,
) -> dict[str, object]:
    """Independently validate filtered VCF records against their audit report."""
    try:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
        lines = Path(vcf_path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VCFReportError("VCF filter outputs cannot be read") from exc
    required = {
        "schema_version", "fileformat", "method", "parameters", "input_record_count", "accepted_record_count",
        "excluded_record_count", "exclusion_counts", "accepted_record_keys", "sample_count", "quality_status",
    }
    if not isinstance(report, dict) or set(report) != required or report.get("schema_version") != 1:
        raise VCFReportError("VCF filter report schema is invalid")
    if (
        report.get("fileformat") != "VCFv4.5"
        or report.get("method") != "strict-biallelic-vcf-filter-v1"
        or report.get("parameters") != expected_parameters
        or report.get("quality_status") != "passed"
        or report.get("input_record_count") != expected_input_count
        or not isinstance(report.get("exclusion_counts"), dict)
        or set(report["exclusion_counts"]) - {"allele_fraction", "depth", "filter_status", "gene", "missing_metric", "quality"}
        or any(not isinstance(value, int) or value < 0 for value in report["exclusion_counts"].values())
    ):
        raise VCFReportError("VCF filter report identity, parameters, or exclusions are invalid")
    accepted_count = report.get("accepted_record_count")
    excluded_count = report.get("excluded_record_count")
    if (
        not isinstance(accepted_count, int)
        or not isinstance(excluded_count, int)
        or accepted_count < 0
        or excluded_count < 0
        or accepted_count + excluded_count != expected_input_count
        or sum(report["exclusion_counts"].values()) != excluded_count
        or not isinstance(report.get("accepted_record_keys"), list)
        or len(report["accepted_record_keys"]) != accepted_count
    ):
        raise VCFReportError("VCF filter record accounting does not reconcile")
    if not lines or lines[0] != "##fileformat=VCFv4.5":
        raise VCFReportError("filtered output does not preserve VCFv4.5")
    header = next((line.split("\t") for line in lines if line.startswith("#CHROM\t")), None)
    if header is None or tuple(header[9:]) != expected_samples or report.get("sample_count") != len(expected_samples):
        raise VCFReportError("filtered VCF sample identity differs from the declared manifest")
    data = [line.split("\t") for line in lines if line and not line.startswith("#")]
    if len(data) != accepted_count or any(len(fields) != len(header) for fields in data):
        raise VCFReportError("filtered VCF rows differ from report accounting")
    parameters = expected_parameters
    selected_genes = set(parameters["genes"])
    accepted_keys = []
    previous = None
    for fields in data:
        contig, position_text, identifier, ref, alt, quality_text, filter_text, info_text = fields[:8]
        try:
            position = int(position_text)
            quality = float(quality_text)
        except ValueError as exc:
            raise VCFReportError("filtered VCF contains an invalid position or quality") from exc
        if previous is not None and contig == previous[0] and position < previous[1]:
            raise VCFReportError("filtered VCF is not coordinate sorted")
        previous = (contig, position)
        info = {}
        for item in info_text.split(";"):
            key, marker, value = item.partition("=")
            if marker:
                info[key] = value
        try:
            depth = float(info["DP"])
            allele_fraction = float(info["AF"])
        except (KeyError, ValueError) as exc:
            raise VCFReportError("filtered VCF lacks validated DP or AF") from exc
        genes = {entry.split("|")[3].upper() for entry in info.get("ANN", "").split(",") if len(entry.split("|")) >= 4}
        if (
            "," in alt
            or quality < parameters["minimum_quality"]
            or depth < parameters["minimum_depth"]
            or allele_fraction < parameters["minimum_allele_fraction"]
            or (parameters["require_pass"] and filter_text not in {"PASS", "."})
            or (selected_genes != {"*"} and not genes & selected_genes)
        ):
            raise VCFReportError("filtered VCF contains a record that fails declared rules")
        accepted_keys.append(f"{contig}:{position}:{ref}:{alt}:{identifier}")
    if accepted_keys != report["accepted_record_keys"]:
        raise VCFReportError("filtered VCF records differ from accepted report identities")
    return {
        "schema_version": 1,
        "method": report["method"],
        "input_record_count": expected_input_count,
        "accepted_record_count": accepted_count,
        "excluded_record_count": excluded_count,
        "exclusion_counts": report["exclusion_counts"],
        "accepted_record_keys": accepted_keys,
        "sample_count": len(expected_samples),
        "quality_status": "passed",
        "downstream_readiness": "filtered-vcf-ready-pending-normalization-annotation-and-design-review",
        "interpretation_policy": "Threshold acceptance is technical evidence only and does not establish call validity, biological association, pathogenicity, or clinical actionability.",
    }
