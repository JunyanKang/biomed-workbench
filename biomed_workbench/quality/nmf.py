"""Independent validation for project-owned NMF metagene outputs."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Mapping


class NMFReportError(ValueError):
    """Raised when NMF factors or their audit report violate the contract."""


_REPORT_FIELDS = {
    "schema_version",
    "method",
    "input_feature_count",
    "retained_feature_count",
    "removed_features",
    "sample_count",
    "candidate_ranks",
    "selected_rank",
    "selection_rule",
    "selection_error_gap",
    "quality_thresholds",
    "restarts",
    "max_iter",
    "tolerance",
    "seed",
    "rank_metrics",
    "selected_relative_error",
    "selected_mse",
    "maximum_component_similarity",
    "top_features",
    "dominant_component_by_sample",
    "quality_findings",
    "quality_status",
}
_RANK_FIELDS = {
    "rank",
    "best_relative_error",
    "mean_relative_error",
    "relative_error_sd",
    "component_stability",
    "assignment_stability",
    "converged_restarts",
    "iterations",
}
_THRESHOLD_FIELDS = {
    "minimum_component_stability",
    "minimum_assignment_stability",
    "maximum_component_similarity",
}


def _identifiers(path: Path, label: str) -> list[str]:
    try:
        values = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise NMFReportError(f"{label} identifiers cannot be read") from exc
    if not values or any(not value or value.strip() != value or "\t" in value for value in values):
        raise NMFReportError(f"{label} identifiers are invalid")
    if len(values) != len(set(values)):
        raise NMFReportError(f"{label} identifiers are not unique")
    return values


def _numeric_rows(path: Path, expected_rows: int, expected_columns: int, label: str) -> list[list[float]]:
    try:
        rows = list(csv.reader(path.read_text(encoding="utf-8").splitlines(), delimiter="\t"))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise NMFReportError(f"{label} cannot be read") from exc
    if len(rows) != expected_rows or any(len(row) != expected_columns for row in rows):
        raise NMFReportError(f"{label} dimensions are invalid")
    try:
        values = [[float(value) for value in row] for row in rows]
    except ValueError as exc:
        raise NMFReportError(f"{label} contains a nonnumeric value") from exc
    if any(not math.isfinite(value) or value < 0 for row in values for value in row):
        raise NMFReportError(f"{label} must be finite and nonnegative")
    return values


def _factor_table(path: Path, row_header: str, expected_rows: list[str], expected_columns: list[str], label: str) -> list[list[float]]:
    try:
        rows = list(csv.reader(path.read_text(encoding="utf-8").splitlines(), delimiter="\t"))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise NMFReportError(f"{label} cannot be read") from exc
    if not rows or rows[0] != [row_header, *expected_columns]:
        raise NMFReportError(f"{label} header differs from its declared axes")
    if [row[0] for row in rows[1:] if row] != expected_rows or any(len(row) != len(expected_columns) + 1 for row in rows[1:]):
        raise NMFReportError(f"{label} row axis or dimensions are invalid")
    try:
        values = [[float(value) for value in row[1:]] for row in rows[1:]]
    except ValueError as exc:
        raise NMFReportError(f"{label} contains a nonnumeric value") from exc
    if any(not math.isfinite(value) or value < 0 for row in values for value in row):
        raise NMFReportError(f"{label} must be finite and nonnegative")
    return values


def _number(value: object, label: str, *, lower: float = 0.0, upper: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NMFReportError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < lower or (upper is not None and result > upper):
        raise NMFReportError(f"{label} is outside its valid range")
    return result


def _close(left: float, right: float, label: str) -> None:
    if not math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-12):
        raise NMFReportError(f"{label} does not match independent reconstruction")


def parse_nmf_outputs(
    matrix_path: Path,
    feature_path: Path,
    sample_path: Path,
    loadings_path: Path,
    exposures_path: Path,
    report_path: Path,
    *,
    expected_parameters: Mapping[str, object],
) -> dict[str, object]:
    """Validate factors, selection accounting, and reconstruction from source inputs."""

    features = _identifiers(feature_path, "feature")
    samples = _identifiers(sample_path, "sample")
    matrix = _numeric_rows(matrix_path, len(features), len(samples), "input matrix")
    retained_mask = []
    for row in matrix:
        mean = sum(row) / len(row)
        retained_mask.append(sum(row) > 0 and sum((value - mean) ** 2 for value in row) / len(row) > 0)
    retained_features = [feature for feature, keep in zip(features, retained_mask, strict=True) if keep]
    removed_features = [feature for feature, keep in zip(features, retained_mask, strict=True) if not keep]
    retained_matrix = [row for row, keep in zip(matrix, retained_mask, strict=True) if keep]

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NMFReportError("NMF report cannot be read") from exc
    if not isinstance(report, dict) or set(report) != _REPORT_FIELDS:
        raise NMFReportError("NMF report fields differ from schema version 1")
    if report["schema_version"] != 1 or report["method"] != "sklearn-nmf-cd-frobenius-random-multistart-v1":
        raise NMFReportError("NMF report schema or method is unsupported")
    if report["input_feature_count"] != len(features) or report["retained_feature_count"] != len(retained_features) or report["removed_features"] != removed_features or report["sample_count"] != len(samples):
        raise NMFReportError("NMF report input and feature filtering accounting is inconsistent")

    required_parameters = {
        "ranks",
        "restarts",
        "max_iter",
        "tolerance",
        "top_genes",
        "selection_error_gap",
        "minimum_component_stability",
        "minimum_assignment_stability",
        "maximum_component_similarity",
        "seed",
    }
    if set(expected_parameters) != required_parameters:
        raise NMFReportError("expected NMF parameters are incomplete")
    ranks = sorted({int(value) for value in str(expected_parameters["ranks"]).split(",")})
    scalar_matches = {
        "candidate_ranks": ranks,
        "restarts": expected_parameters["restarts"],
        "max_iter": expected_parameters["max_iter"],
        "tolerance": expected_parameters["tolerance"],
        "selection_error_gap": expected_parameters["selection_error_gap"],
        "seed": expected_parameters["seed"],
    }
    if any(report[key] != value for key, value in scalar_matches.items()):
        raise NMFReportError("NMF report parameters differ from the executed command")
    thresholds = report["quality_thresholds"]
    if not isinstance(thresholds, dict) or set(thresholds) != _THRESHOLD_FIELDS:
        raise NMFReportError("NMF quality thresholds are invalid")
    for key in _THRESHOLD_FIELDS:
        if thresholds[key] != expected_parameters[key]:
            raise NMFReportError("NMF quality thresholds differ from the executed command")

    rank_metrics = report["rank_metrics"]
    if not isinstance(rank_metrics, list) or len(rank_metrics) != len(ranks):
        raise NMFReportError("NMF rank metrics are incomplete")
    metrics_by_rank = {}
    restarts = int(expected_parameters["restarts"])
    max_iter = int(expected_parameters["max_iter"])
    for metric, rank in zip(rank_metrics, ranks, strict=True):
        if not isinstance(metric, dict) or set(metric) != _RANK_FIELDS or metric["rank"] != rank:
            raise NMFReportError("NMF rank metric schema or ordering is invalid")
        for key in ("best_relative_error", "mean_relative_error", "relative_error_sd"):
            _number(metric[key], f"rank {rank} {key}")
        if metric["best_relative_error"] > metric["mean_relative_error"] + 1e-12:
            raise NMFReportError("NMF best error exceeds mean restart error")
        for key in ("component_stability", "assignment_stability"):
            _number(metric[key], f"rank {rank} {key}", upper=1.0)
        if not isinstance(metric["converged_restarts"], int) or isinstance(metric["converged_restarts"], bool) or not 0 <= metric["converged_restarts"] <= restarts:
            raise NMFReportError("NMF converged restart count is invalid")
        if not isinstance(metric["iterations"], list) or len(metric["iterations"]) != restarts or any(not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= max_iter for value in metric["iterations"]):
            raise NMFReportError("NMF iteration accounting is invalid")
        metrics_by_rank[rank] = metric

    selected_rank = report["selected_rank"]
    if selected_rank not in ranks:
        raise NMFReportError("selected NMF rank was not a candidate")
    best_error = min(metrics_by_rank[rank]["best_relative_error"] for rank in ranks)
    gap = float(expected_parameters["selection_error_gap"])
    eligible = [rank for rank in ranks if metrics_by_rank[rank]["best_relative_error"] <= best_error + gap + 1e-15]
    expected_rank = min(
        eligible,
        key=lambda rank: (-metrics_by_rank[rank]["component_stability"], -metrics_by_rank[rank]["assignment_stability"], rank),
    )
    if selected_rank != expected_rank:
        raise NMFReportError("selected NMF rank does not follow the declared rule")
    components = [f"Metagene_{index + 1}" for index in range(selected_rank)]
    loadings = _factor_table(loadings_path, "feature_id", retained_features, components, "metagene loadings")
    exposures = _factor_table(exposures_path, "component_id", components, samples, "sample exposures")
    for column in range(selected_rank):
        _close(sum(row[column] for row in loadings), 1.0, "loading column normalization")

    squared_error = 0.0
    squared_norm = 0.0
    for row_index, source_row in enumerate(retained_matrix):
        for sample_index, observed in enumerate(source_row):
            fitted = sum(loadings[row_index][component] * exposures[component][sample_index] for component in range(selected_rank))
            squared_error += (observed - fitted) ** 2
            squared_norm += observed**2
    relative_error = math.sqrt(squared_error) / math.sqrt(squared_norm)
    mse = squared_error / (len(retained_features) * len(samples))
    _close(relative_error, float(report["selected_relative_error"]), "selected relative error")
    _close(mse, float(report["selected_mse"]), "selected MSE")
    _close(relative_error, float(metrics_by_rank[selected_rank]["best_relative_error"]), "selected rank metric")

    top_count = min(int(expected_parameters["top_genes"]), len(retained_features))
    expected_top = {}
    for component_index, component in enumerate(components):
        order = sorted(range(len(retained_features)), key=lambda index: (-loadings[index][component_index], index))[:top_count]
        expected_top[component] = [
            {"feature": retained_features[index], "weight": loadings[index][component_index]}
            for index in order
        ]
    if report["top_features"] != expected_top:
        raise NMFReportError("NMF top features differ from the loading matrix")
    assignments = {
        sample: components[max(range(selected_rank), key=lambda component: exposures[component][sample_index])]
        for sample_index, sample in enumerate(samples)
    }
    if report["dominant_component_by_sample"] != assignments:
        raise NMFReportError("NMF sample assignments differ from the exposure matrix")

    maximum_similarity = 0.0
    norms = [math.sqrt(sum(value**2 for value in row)) for row in exposures]
    for left in range(selected_rank):
        for right in range(left + 1, selected_rank):
            similarity = sum(a * b for a, b in zip(exposures[left], exposures[right], strict=True)) / (norms[left] * norms[right])
            maximum_similarity = max(maximum_similarity, similarity)
    _close(maximum_similarity, float(report["maximum_component_similarity"]), "component similarity")
    selected_metric = metrics_by_rank[selected_rank]
    findings = []
    if selected_metric["converged_restarts"] != restarts:
        findings.append("nonconverged-restarts")
    if selected_metric["component_stability"] < thresholds["minimum_component_stability"]:
        findings.append("component-instability")
    if selected_metric["assignment_stability"] < thresholds["minimum_assignment_stability"]:
        findings.append("assignment-instability")
    if maximum_similarity > thresholds["maximum_component_similarity"]:
        findings.append("redundant-components")
    if report["quality_findings"] != findings or report["quality_status"] != ("passed" if not findings else "warning"):
        raise NMFReportError("NMF quality status differs from independently evaluated thresholds")
    return report
