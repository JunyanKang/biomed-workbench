"""Version-specific parsing for samtools alignment quality reports."""

from __future__ import annotations

import json
import math
from pathlib import Path


class AlignmentQualityReportError(ValueError):
    """Raised when an alignment quality report is incomplete or inconsistent."""


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
