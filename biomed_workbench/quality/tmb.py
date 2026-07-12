"""Independent validation of VCF- and BED-derived mutation burden reports."""

from __future__ import annotations

import json
import math
from pathlib import Path


class TMBReportError(ValueError):
    """Raised when mutation-burden evidence violates its declared contract."""


def parse_tmb_report(
    path: Path | str,
    *,
    expected_input_variants: int,
    expected_input_intervals: int,
) -> dict[str, object]:
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TMBReportError("TMB report cannot be read") from exc
    required = {
        "schema_version", "method", "input_variant_count", "within_callable_variant_count",
        "outside_callable_variant_count", "non_nonsynonymous_variant_count", "nonsynonymous_variant_count",
        "eligible_variant_keys", "category_counts", "gene_counts", "input_interval_count",
        "merged_interval_count", "callable_bases", "callable_megabases", "tmb_mutations_per_mb",
        "quality_status", "classification_policy",
    }
    if not isinstance(report, dict) or set(report) != required:
        raise TMBReportError("TMB report schema is invalid")
    integer_fields = (
        "input_variant_count", "within_callable_variant_count", "outside_callable_variant_count",
        "non_nonsynonymous_variant_count", "nonsynonymous_variant_count", "input_interval_count",
        "merged_interval_count", "callable_bases",
    )
    if any(not isinstance(report[field], int) or report[field] < 0 for field in integer_fields):
        raise TMBReportError("TMB report counts must be nonnegative integers")
    if (
        report["schema_version"] != 1
        or report["method"] != "ann-nonsynonymous-variants-per-callable-bed-union-mb-v1"
        or report["quality_status"] != "passed"
        or report["classification_policy"] != "none-without-assay-indication-and-validated-cutoffs"
        or report["input_variant_count"] != expected_input_variants
        or report["input_interval_count"] != expected_input_intervals
        or report["merged_interval_count"] > report["input_interval_count"]
        or report["within_callable_variant_count"] + report["outside_callable_variant_count"] != report["input_variant_count"]
        or report["nonsynonymous_variant_count"] + report["non_nonsynonymous_variant_count"] != report["within_callable_variant_count"]
    ):
        raise TMBReportError("TMB report identity, interval, or variant accounting is inconsistent")
    for name in ("eligible_variant_keys", "category_counts", "gene_counts"):
        if not isinstance(report[name], list if name == "eligible_variant_keys" else dict):
            raise TMBReportError("TMB report variant, category, or gene evidence has an invalid type")
    if (
        len(report["eligible_variant_keys"]) != report["nonsynonymous_variant_count"]
        or len(report["eligible_variant_keys"]) != len(set(report["eligible_variant_keys"]))
        or sum(report["category_counts"].values()) != report["nonsynonymous_variant_count"]
        or any(not isinstance(value, int) or value <= 0 for value in (*report["category_counts"].values(), *report["gene_counts"].values()))
    ):
        raise TMBReportError("TMB eligible variants, categories, or genes do not reconcile")
    callable_megabases = report["callable_megabases"]
    tmb = report["tmb_mutations_per_mb"]
    if (
        not isinstance(callable_megabases, (int, float))
        or not isinstance(tmb, (int, float))
        or not math.isfinite(callable_megabases)
        or not math.isfinite(tmb)
        or callable_megabases <= 0
        or not math.isclose(callable_megabases, report["callable_bases"] / 1_000_000, rel_tol=0, abs_tol=1e-12)
        or not math.isclose(tmb, report["nonsynonymous_variant_count"] / callable_megabases, rel_tol=1e-12, abs_tol=1e-12)
    ):
        raise TMBReportError("TMB denominator or mutation-per-megabase arithmetic is invalid")
    return {
        **report,
        "downstream_readiness": "descriptive-tmb-ready-pending-assay-and-indication-validation",
        "interpretation_policy": "No high/low label is valid without assay-, indication-, and outcome-validated cutoffs plus clinical governance.",
    }
