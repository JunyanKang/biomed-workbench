"""Calculate auditable TMB from filtered VCF 4.5 and callable BED 1.0."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


class TMBError(ValueError):
    """Raised when TMB inputs cannot satisfy the declared scientific contract."""


NONSYNONYMOUS = {
    "missense_variant": "missense",
    "protein_altering_variant": "missense",
    "nonsense_variant": "nonsense",
    "stop_gained": "nonsense",
    "stop_lost": "nonsense",
    "start_lost": "nonsense",
    "frameshift_variant": "frameshift",
    "splice_acceptor_variant": "splice_site",
    "splice_donor_variant": "splice_site",
    "disruptive_inframe_insertion": "inframe_indel",
    "disruptive_inframe_deletion": "inframe_indel",
    "inframe_insertion": "inframe_indel",
    "inframe_deletion": "inframe_indel",
}
IMPACT_RANK = {"HIGH": 4, "MODERATE": 3, "LOW": 2, "MODIFIER": 1}


def _callable_intervals(path: Path) -> tuple[dict[str, list[tuple[int, int]]], int, int]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise TMBError("callable BED cannot be read") from exc
    intervals: dict[str, list[tuple[int, int]]] = defaultdict(list)
    input_count = 0
    for number, line in enumerate(lines, start=1):
        if not line or line.startswith("#"):
            continue
        if line.startswith(("track", "browser")):
            raise TMBError("callable BED may not contain browser directives")
        fields = line.split("\t")
        if len(fields) < 3:
            raise TMBError(f"BED row {number} has fewer than three fields")
        chromosome = fields[0]
        try:
            start, end = int(fields[1]), int(fields[2])
        except ValueError as exc:
            raise TMBError(f"BED row {number} has invalid coordinates") from exc
        if not chromosome or start < 0 or end <= start:
            raise TMBError(f"BED row {number} violates zero-based half-open coordinates")
        intervals[chromosome].append((start, end))
        input_count += 1
    if input_count == 0:
        raise TMBError("callable BED contains no intervals")
    merged: dict[str, list[tuple[int, int]]] = {}
    for chromosome, values in intervals.items():
        rows = []
        for start, end in sorted(values):
            if rows and start <= rows[-1][1]:
                rows[-1] = (rows[-1][0], max(rows[-1][1], end))
            else:
                rows.append((start, end))
        merged[chromosome] = rows
    bases = sum(end - start for values in merged.values() for start, end in values)
    if bases <= 0:
        raise TMBError("callable BED has no positive union territory")
    return merged, input_count, bases


def _inside(intervals: dict[str, list[tuple[int, int]]], chromosome: str, position: int) -> bool:
    coordinate = position - 1
    return any(start <= coordinate < end for start, end in intervals.get(chromosome, ()))


def _annotations(info: str, alt: str) -> list[tuple[str, str, str]]:
    fields = {}
    for item in info.split(";"):
        key, marker, value = item.partition("=")
        if not key or key in fields:
            raise TMBError("VCF INFO contains an invalid or duplicate field")
        fields[key] = value if marker else None
    ann = fields.get("ANN")
    if not ann:
        raise TMBError("every TMB input record requires ANN consequence annotations")
    annotations = []
    for entry in ann.split(","):
        values = entry.split("|")
        if len(values) < 4 or not values[0] or not values[1]:
            raise TMBError("ANN entry does not contain allele, consequence, impact, and gene fields")
        if values[0] == alt:
            annotations.append((values[1], values[2].upper(), values[3]))
    if not annotations:
        raise TMBError("ANN contains no annotation for the record ALT allele")
    return annotations


def _classify(annotations: list[tuple[str, str, str]]) -> tuple[str | None, str | None]:
    best = None
    for consequences, impact, gene in annotations:
        for consequence in consequences.split("&"):
            category = NONSYNONYMOUS.get(consequence)
            if category is None:
                continue
            candidate = (IMPACT_RANK.get(impact, 0), category, gene or None)
            if best is None or candidate[0] > best[0] or (candidate[0] == best[0] and candidate[1:] < best[1:]):
                best = candidate
    return (best[1], best[2]) if best is not None else (None, None)


def calculate(vcf_path: Path, bed_path: Path, report_path: Path) -> None:
    intervals, interval_count, callable_bases = _callable_intervals(bed_path)
    try:
        lines = vcf_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise TMBError("filtered VCF cannot be read") from exc
    if not lines or lines[0] != "##fileformat=VCFv4.5":
        raise TMBError("TMB input must declare VCFv4.5")
    contigs = []
    header = None
    previous = None
    input_count = 0
    outside_callable = 0
    noncoding = 0
    eligible_keys = []
    categories = Counter()
    genes = Counter()
    for number, line in enumerate(lines, start=1):
        if line.startswith("##contig=<ID="):
            contig = line.removeprefix("##contig=<ID=").split(",", 1)[0].split(">", 1)[0]
            if not contig or contig in contigs:
                raise TMBError("VCF contig dictionary is invalid")
            contigs.append(contig)
            continue
        if line.startswith("##"):
            continue
        if line.startswith("#CHROM\t"):
            if header is not None:
                raise TMBError("VCF contains duplicate column headers")
            header = line.split("\t")
            if header[:8] != ["#CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER", "INFO"]:
                raise TMBError("VCF fixed columns are invalid")
            if set(intervals) - set(contigs):
                raise TMBError("callable BED contains a chromosome absent from the VCF contig dictionary")
            continue
        if not line or line.startswith("#") or header is None:
            raise TMBError(f"unexpected VCF content at line {number}")
        fields = line.split("\t")
        if len(fields) != len(header):
            raise TMBError(f"VCF record {number} has an invalid column count")
        chromosome, position_text, identifier, ref, alt, _quality, filter_value, info = fields[:8]
        try:
            position = int(position_text)
        except ValueError as exc:
            raise TMBError(f"VCF record {number} has an invalid POS") from exc
        if chromosome not in contigs or position < 1 or not ref or not alt or "," in alt or alt.startswith("<"):
            raise TMBError(f"VCF record {number} violates the biallelic sequence and reference contract")
        order = (contigs.index(chromosome), position)
        if previous is not None and order < previous:
            raise TMBError("VCF records are not coordinate sorted")
        previous = order
        if filter_value not in {"PASS", "."}:
            raise TMBError("TMB input contains a record that has not passed upstream filtering")
        input_count += 1
        annotations = _annotations(info, alt)
        if not _inside(intervals, chromosome, position):
            outside_callable += 1
            continue
        category, gene = _classify(annotations)
        if category is None:
            noncoding += 1
            continue
        key = f"{chromosome}:{position}:{ref}:{alt}:{identifier}"
        eligible_keys.append(key)
        categories[category] += 1
        if gene:
            genes[gene] += 1
    if header is None:
        raise TMBError("VCF column header is missing")
    callable_megabases = callable_bases / 1_000_000
    report = {
        "schema_version": 1,
        "method": "ann-nonsynonymous-variants-per-callable-bed-union-mb-v1",
        "input_variant_count": input_count,
        "within_callable_variant_count": input_count - outside_callable,
        "outside_callable_variant_count": outside_callable,
        "non_nonsynonymous_variant_count": noncoding,
        "nonsynonymous_variant_count": len(eligible_keys),
        "eligible_variant_keys": eligible_keys,
        "category_counts": dict(sorted(categories.items())),
        "gene_counts": dict(sorted(genes.items())),
        "input_interval_count": interval_count,
        "merged_interval_count": sum(len(values) for values in intervals.values()),
        "callable_bases": callable_bases,
        "callable_megabases": callable_megabases,
        "tmb_mutations_per_mb": len(eligible_keys) / callable_megabases,
        "quality_status": "passed",
        "classification_policy": "none-without-assay-indication-and-validated-cutoffs",
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vcf", type=Path, required=True)
    parser.add_argument("--callable-bed", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    calculate(args.vcf, args.callable_bed, args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
