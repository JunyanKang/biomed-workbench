"""Strict, auditable filtering of one-sample biallelic VCF 4.5 records."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path


class FilterError(ValueError):
    """Raised when VCF filtering cannot satisfy its declared contract."""


def _fields(value: str, separator: str) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    if value == ".":
        return result
    for field in value.split(separator):
        key, marker, item = field.partition("=")
        if not key or key in result:
            raise FilterError("VCF contains an invalid or duplicate structured field")
        result[key] = item if marker else None
    return result


def _number(value: str | None, name: str) -> float | None:
    if value in {None, ".", ""}:
        return None
    if "," in value:
        raise FilterError(f"{name} must contain one value for a biallelic record")
    try:
        result = float(value)
    except ValueError as exc:
        raise FilterError(f"{name} is not numeric") from exc
    if not math.isfinite(result):
        raise FilterError(f"{name} must be finite")
    return result


def _metrics(info: dict[str, str | None], format_text: str | None, sample_text: str | None) -> tuple[float | None, float | None]:
    depth = _number(info.get("DP"), "DP")
    allele_fraction = _number(info.get("AF"), "AF")
    if format_text is not None and sample_text is not None:
        names = format_text.split(":")
        values = sample_text.split(":")
        if len(names) != len(values) or len(names) != len(set(names)):
            raise FilterError("VCF FORMAT and sample fields are inconsistent")
        sample = dict(zip(names, values, strict=True))
        if depth is None:
            depth = _number(sample.get("DP"), "FORMAT/DP")
        if allele_fraction is None and sample.get("AD") not in {None, ".", ""}:
            try:
                counts = [int(value) for value in sample["AD"].split(",")]
            except ValueError as exc:
                raise FilterError("FORMAT/AD is not an integer vector") from exc
            if len(counts) != 2 or any(value < 0 for value in counts):
                raise FilterError("FORMAT/AD must contain nonnegative ref and alt counts")
            denominator = sum(counts)
            allele_fraction = counts[1] / denominator if denominator else None
    if depth is not None and (depth < 0 or not depth.is_integer()):
        raise FilterError("DP must be a nonnegative integer")
    if allele_fraction is not None and not 0 <= allele_fraction <= 1:
        raise FilterError("AF must be between zero and one")
    return depth, allele_fraction


def _genes(info: dict[str, str | None]) -> set[str]:
    value = info.get("ANN")
    genes = set()
    if value:
        for annotation in value.split(","):
            fields = annotation.split("|")
            if len(fields) >= 4 and fields[3].strip():
                genes.add(fields[3].strip().upper())
    return genes


def filter_vcf(
    input_path: Path,
    output_path: Path,
    report_path: Path,
    *,
    minimum_quality: float,
    minimum_depth: int,
    minimum_allele_fraction: float,
    genes: str,
    require_pass: bool,
    missing_metric_policy: str,
) -> None:
    if minimum_quality < 0 or minimum_depth < 0 or not 0 <= minimum_allele_fraction <= 1:
        raise FilterError("filter thresholds are outside valid bounds")
    if missing_metric_policy not in {"error", "exclude"}:
        raise FilterError("missing metric policy must be error or exclude")
    selected_genes = None if genes == "*" else {value.strip().upper() for value in genes.split(",") if value.strip()}
    if selected_genes == set():
        raise FilterError("gene selection must be * or a comma-separated nonempty set")
    try:
        lines = input_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise FilterError("input VCF cannot be read as UTF-8") from exc
    if not lines or lines[0] != "##fileformat=VCFv4.5":
        raise FilterError("input must declare VCFv4.5")
    header_lines = []
    column_header = None
    sample_count = 0
    contig_order: dict[str, int] = {}
    records = []
    previous = None
    for number, line in enumerate(lines, start=1):
        if line.startswith("##"):
            if column_header is not None:
                raise FilterError("metadata appears after the VCF column header")
            header_lines.append(line)
            if line.startswith("##contig=<ID="):
                contig = line.removeprefix("##contig=<ID=").split(",", 1)[0].split(">", 1)[0]
                if not contig or contig in contig_order:
                    raise FilterError("VCF contig dictionary is invalid")
                contig_order[contig] = len(contig_order)
            continue
        if line.startswith("#CHROM\t"):
            if column_header is not None:
                raise FilterError("VCF contains duplicate column headers")
            columns = line.split("\t")
            if columns[:8] != ["#CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER", "INFO"]:
                raise FilterError("VCF fixed columns are invalid")
            sample_count = max(0, len(columns) - 9)
            if len(columns) == 9 or sample_count > 1 or (sample_count == 1 and columns[8] != "FORMAT"):
                raise FilterError("module supports either sites-only VCF or exactly one sample with FORMAT")
            column_header = line
            continue
        if not line or line.startswith("#") or column_header is None:
            raise FilterError(f"unexpected VCF content at line {number}")
        values = line.split("\t")
        expected_columns = 8 if sample_count == 0 else 10
        if len(values) != expected_columns:
            raise FilterError(f"VCF record {number} has an invalid column count")
        contig, position_text, identifier, ref, alt, quality_text, filter_text, info_text = values[:8]
        try:
            position = int(position_text)
        except ValueError as exc:
            raise FilterError(f"VCF record {number} has an invalid POS") from exc
        if contig not in contig_order or position < 1 or not ref or not alt or "," in alt or alt.startswith("<") or alt == ".":
            raise FilterError(f"VCF record {number} is not one declared biallelic sequence variant")
        order = (contig_order[contig], position)
        if previous is not None and order < previous:
            raise FilterError("VCF records are not coordinate sorted")
        previous = order
        quality = _number(quality_text, "QUAL")
        info = _fields(info_text, ";")
        depth, allele_fraction = _metrics(info, values[8] if sample_count else None, values[9] if sample_count else None)
        record_genes = _genes(info)
        records.append(
            {
                "line": line,
                "key": f"{contig}:{position}:{ref}:{alt}:{identifier}",
                "quality": quality,
                "depth": depth,
                "allele_fraction": allele_fraction,
                "filter": filter_text,
                "genes": record_genes,
            }
        )
    if column_header is None or not contig_order:
        raise FilterError("VCF header or contig dictionary is incomplete")
    accepted = []
    exclusion_counts: Counter[str] = Counter()
    for record in records:
        missing = [name for name, value in (("quality", record["quality"]), ("depth", record["depth"]), ("allele_fraction", record["allele_fraction"])) if value is None]
        if missing:
            if missing_metric_policy == "error":
                raise FilterError("VCF record lacks a required filtering metric")
            exclusion_counts["missing_metric"] += 1
            continue
        if require_pass and record["filter"] not in {"PASS", "."}:
            exclusion_counts["filter_status"] += 1
        elif record["quality"] < minimum_quality:
            exclusion_counts["quality"] += 1
        elif record["depth"] < minimum_depth:
            exclusion_counts["depth"] += 1
        elif record["allele_fraction"] < minimum_allele_fraction:
            exclusion_counts["allele_fraction"] += 1
        elif selected_genes is not None and not (record["genes"] & selected_genes):
            exclusion_counts["gene"] += 1
        else:
            accepted.append(record)
    output_path.write_text("\n".join([*header_lines, column_header, *(record["line"] for record in accepted)]) + "\n", encoding="utf-8")
    report = {
        "schema_version": 1,
        "fileformat": "VCFv4.5",
        "method": "strict-biallelic-vcf-filter-v1",
        "parameters": {
            "minimum_quality": minimum_quality,
            "minimum_depth": minimum_depth,
            "minimum_allele_fraction": minimum_allele_fraction,
            "genes": sorted(selected_genes) if selected_genes is not None else ["*"],
            "require_pass": require_pass,
            "missing_metric_policy": missing_metric_policy,
        },
        "input_record_count": len(records),
        "accepted_record_count": len(accepted),
        "excluded_record_count": len(records) - len(accepted),
        "exclusion_counts": dict(sorted(exclusion_counts.items())),
        "accepted_record_keys": [record["key"] for record in accepted],
        "sample_count": sample_count,
        "quality_status": "passed",
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--minimum-quality", type=float, required=True)
    parser.add_argument("--minimum-depth", type=int, required=True)
    parser.add_argument("--minimum-allele-fraction", type=float, required=True)
    parser.add_argument("--genes", required=True)
    parser.add_argument("--require-pass", choices=("true", "false"), required=True)
    parser.add_argument("--missing-metric-policy", choices=("error", "exclude"), required=True)
    args = parser.parse_args()
    filter_vcf(
        args.input,
        args.output,
        args.report,
        minimum_quality=args.minimum_quality,
        minimum_depth=args.minimum_depth,
        minimum_allele_fraction=args.minimum_allele_fraction,
        genes=args.genes,
        require_pass=args.require_pass == "true",
        missing_metric_policy=args.missing_metric_policy,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
