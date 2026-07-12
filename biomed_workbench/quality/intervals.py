"""Strict parsers for versioned genomic interval tool outputs."""

from __future__ import annotations

from pathlib import Path


class IntervalReportError(ValueError):
    """Raised when interval evidence violates its declared BED contract."""


def _bed(values: list[str], *, offset: int, columns: int, label: str) -> tuple[str, int, int, tuple[str, ...]]:
    fields = values[offset : offset + columns]
    if len(fields) != columns:
        raise IntervalReportError(f"{label} BED fields are incomplete")
    chromosome = fields[0]
    try:
        start, end = int(fields[1]), int(fields[2])
    except (ValueError, IndexError) as exc:
        raise IntervalReportError(f"{label} BED coordinates are invalid") from exc
    if not chromosome or any(character.isspace() for character in chromosome) or start < 0 or end <= start:
        raise IntervalReportError(f"{label} BED interval violates zero-based half-open coordinates")
    return chromosome, start, end, tuple(fields)


def parse_bedtools_intersect_report(
    path: Path | str,
    *,
    query_columns: int,
    reference_columns: int,
    expected_version: str = "2.31.1",
) -> dict[str, object]:
    if query_columns < 3 or query_columns > 12 or reference_columns < 3 or reference_columns > 12:
        raise IntervalReportError("BED column counts must be between 3 and 12")
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise IntervalReportError("bedtools intersect report cannot be read") from exc
    overlaps = []
    query_ids = set()
    reference_ids = set()
    for number, line in enumerate(lines, start=1):
        if not line or line.startswith(("track", "browser", "#")):
            raise IntervalReportError(f"unexpected non-data line at intersect row {number}")
        values = line.split("\t")
        if len(values) != query_columns + reference_columns:
            raise IntervalReportError(f"intersect row {number} has an unexpected BED column count")
        query_chromosome, query_start, query_end, query = _bed(values, offset=0, columns=query_columns, label="query")
        reference_chromosome, reference_start, reference_end, reference = _bed(
            values, offset=query_columns, columns=reference_columns, label="reference"
        )
        overlap = min(query_end, reference_end) - max(query_start, reference_start)
        if query_chromosome != reference_chromosome or overlap <= 0:
            raise IntervalReportError(f"intersect row {number} does not represent a positive same-reference overlap")
        query_ids.add(query)
        reference_ids.add(reference)
        overlaps.append(overlap)
    return {
        "schema_version": 1,
        "bedtools_version": expected_version,
        "overlap_pair_count": len(overlaps),
        "overlapping_query_interval_count": len(query_ids),
        "overlapping_reference_interval_count": len(reference_ids),
        "total_pairwise_overlap_bp": sum(overlaps),
        "empty_result": not overlaps,
        "coordinate_system": "zero-based-half-open",
        "downstream_readiness": "technically-ready-pending-build-identity-and-design-review",
        "interpretation_policy": "Pairwise overlap is geometric evidence only; enrichment, assignment, causality, and biological relevance require explicit denominators, null models, reference-build identity, and assay-aware review.",
    }
