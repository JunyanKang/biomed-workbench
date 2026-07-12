"""Stable multi-rank NMF metagene extraction with explicit model selection."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import warnings

import numpy as np
from scipy.optimize import linear_sum_assignment
from sklearn.decomposition import NMF
from sklearn.exceptions import ConvergenceWarning


class NMFError(ValueError):
    """Raised when an expression matrix cannot satisfy the NMF contract."""


def _identifiers(path: Path, label: str) -> list[str]:
    try:
        values = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    except (OSError, UnicodeDecodeError) as exc:
        raise NMFError(f"{label} identifiers cannot be read") from exc
    if not values or any(not value or "\t" in value for value in values) or len(values) != len(set(values)):
        raise NMFError(f"{label} identifiers must be nonempty and unique")
    return values


def _matrix(path: Path, feature_count: int, sample_count: int) -> np.ndarray:
    try:
        rows = list(csv.reader(path.read_text(encoding="utf-8").splitlines(), delimiter="\t"))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise NMFError("expression matrix cannot be read") from exc
    if len(rows) != feature_count or any(len(row) != sample_count for row in rows):
        raise NMFError("expression matrix dimensions differ from feature and sample manifests")
    try:
        values = np.asarray([[float(value) for value in row] for row in rows], dtype=np.float64)
    except ValueError as exc:
        raise NMFError("expression matrix contains a nonnumeric value") from exc
    if not np.all(np.isfinite(values)) or np.any(values < 0):
        raise NMFError("NMF expression values must be finite and nonnegative; negative values are never clipped")
    return values


def _normalize_factors(w: np.ndarray, h: np.ndarray, features: list[str]) -> tuple[np.ndarray, np.ndarray]:
    sums = w.sum(axis=0)
    if np.any(sums <= 0):
        raise NMFError("NMF produced an empty component")
    w = w / sums
    h = h * sums[:, None]
    top = np.argmax(w, axis=0)
    order = sorted(
        range(w.shape[1]),
        key=lambda index: (features[int(top[index])], tuple(float(-value) for value in w[:, index])),
    )
    return w[:, order], h[order, :]


def _align(reference_w: np.ndarray, candidate_w: np.ndarray, candidate_h: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    reference_norm = reference_w / np.maximum(np.linalg.norm(reference_w, axis=0, keepdims=True), np.finfo(float).eps)
    candidate_norm = candidate_w / np.maximum(np.linalg.norm(candidate_w, axis=0, keepdims=True), np.finfo(float).eps)
    similarity = reference_norm.T @ candidate_norm
    rows, columns = linear_sum_assignment(-similarity)
    assignment = {int(row): int(column) for row, column in zip(rows, columns, strict=True)}
    order = [assignment[index] for index in range(reference_w.shape[1])]
    return candidate_w[:, order], candidate_h[order, :], float(np.mean(similarity[rows, columns]))


def _fit_rank(values: np.ndarray, rank: int, restarts: int, max_iter: int, tolerance: float, seed: int, features: list[str]) -> dict[str, object]:
    runs = []
    norm = float(np.linalg.norm(values))
    for restart in range(restarts):
        model = NMF(
            n_components=rank,
            init="random",
            solver="cd",
            beta_loss="frobenius",
            tol=tolerance,
            max_iter=max_iter,
            random_state=seed + rank * 1009 + restart,
            alpha_W=0.0,
            alpha_H=0.0,
            l1_ratio=0.0,
            shuffle=False,
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ConvergenceWarning)
            w = model.fit_transform(values)
            h = model.components_
        w, h = _normalize_factors(w, h, features)
        error = float(np.linalg.norm(values - w @ h))
        assignments = np.argmax(h, axis=0)
        runs.append(
            {
                "w": w,
                "h": h,
                "error": error,
                "relative_error": error / norm,
                "iterations": int(model.n_iter_),
                "converged": not any(issubclass(item.category, ConvergenceWarning) for item in caught),
                "assignments": assignments,
            }
        )
    best_index = min(range(len(runs)), key=lambda index: (runs[index]["relative_error"], index))
    reference = runs[best_index]
    similarities = []
    assignment_agreements = []
    for run in runs:
        aligned_w, aligned_h, similarity = _align(reference["w"], run["w"], run["h"])
        similarities.append(similarity)
        assignment_agreements.append(float(np.mean(np.argmax(aligned_h, axis=0) == reference["assignments"])))
    return {
        "rank": rank,
        "best": reference,
        "relative_errors": [run["relative_error"] for run in runs],
        "iterations": [run["iterations"] for run in runs],
        "converged_restarts": sum(run["converged"] for run in runs),
        "component_stability": float(np.mean(similarities)),
        "assignment_stability": float(np.mean(assignment_agreements)),
    }


def _write_matrix(path: Path, row_name: str, row_ids: list[str], column_ids: list[str], values: np.ndarray) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow([row_name, *column_ids])
        for identifier, row in zip(row_ids, values, strict=True):
            writer.writerow([identifier, *(format(float(value), ".17g") for value in row)])


def factorize(
    matrix_path: Path,
    feature_path: Path,
    sample_path: Path,
    loadings_path: Path,
    exposures_path: Path,
    report_path: Path,
    *,
    ranks_text: str,
    restarts: int,
    max_iter: int,
    tolerance: float,
    top_genes: int,
    selection_error_gap: float,
    minimum_component_stability: float,
    minimum_assignment_stability: float,
    maximum_component_similarity: float,
    seed: int,
) -> None:
    try:
        ranks = sorted({int(value) for value in ranks_text.split(",")})
    except ValueError as exc:
        raise NMFError("candidate ranks must be comma-separated integers") from exc
    if (
        not ranks
        or ranks[0] < 2
        or restarts < 2
        or max_iter < 100
        or not 0 < tolerance < 1
        or top_genes < 1
        or not 0 <= selection_error_gap <= 1
        or not 0 <= minimum_component_stability <= 1
        or not 0 <= minimum_assignment_stability <= 1
        or not 0 <= maximum_component_similarity <= 1
        or seed < 0
    ):
        raise NMFError("NMF parameters are outside validated bounds")
    features = _identifiers(feature_path, "feature")
    samples = _identifiers(sample_path, "sample")
    values = _matrix(matrix_path, len(features), len(samples))
    if ranks[-1] > min(values.shape):
        raise NMFError("candidate rank exceeds the smaller matrix dimension")
    nonzero = np.sum(values, axis=1) > 0
    variable = np.var(values, axis=1) > 0
    retained = nonzero & variable
    removed_features = [feature for feature, keep in zip(features, retained, strict=True) if not keep]
    features = [feature for feature, keep in zip(features, retained, strict=True) if keep]
    values = values[retained, :]
    if len(features) < ranks[-1] or np.linalg.norm(values) <= 0:
        raise NMFError("too few informative features remain for requested ranks")
    rank_results = [_fit_rank(values, rank, restarts, max_iter, tolerance, seed, features) for rank in ranks]
    best_error = min(item["best"]["relative_error"] for item in rank_results)
    eligible = [item for item in rank_results if item["best"]["relative_error"] <= best_error + selection_error_gap + 1e-15]
    selected = min(eligible, key=lambda item: (-item["component_stability"], -item["assignment_stability"], item["rank"]))
    w = selected["best"]["w"]
    h = selected["best"]["h"]
    components = [f"Metagene_{index + 1}" for index in range(selected["rank"])]
    _write_matrix(loadings_path, "feature_id", features, components, w)
    _write_matrix(exposures_path, "component_id", components, samples, h)
    top = {}
    for index, component in enumerate(components):
        order = np.argsort(-w[:, index], kind="stable")[: min(top_genes, len(features))]
        top[component] = [{"feature": features[int(row)], "weight": float(w[int(row), index])} for row in order]
    h_norm = h / np.maximum(np.linalg.norm(h, axis=1, keepdims=True), np.finfo(float).eps)
    component_similarity = h_norm @ h_norm.T
    np.fill_diagonal(component_similarity, 0)
    maximum_similarity = float(np.max(component_similarity)) if selected["rank"] > 1 else 0.0
    quality_findings = []
    if selected["converged_restarts"] != restarts:
        quality_findings.append("nonconverged-restarts")
    if selected["component_stability"] < minimum_component_stability:
        quality_findings.append("component-instability")
    if selected["assignment_stability"] < minimum_assignment_stability:
        quality_findings.append("assignment-instability")
    if maximum_similarity > maximum_component_similarity:
        quality_findings.append("redundant-components")
    report = {
        "schema_version": 1,
        "method": "sklearn-nmf-cd-frobenius-random-multistart-v1",
        "input_feature_count": int(retained.size),
        "retained_feature_count": len(features),
        "removed_features": removed_features,
        "sample_count": len(samples),
        "candidate_ranks": ranks,
        "selected_rank": selected["rank"],
        "selection_rule": "highest component then assignment stability within an additive relative-reconstruction-error gap; smaller rank breaks ties",
        "selection_error_gap": selection_error_gap,
        "quality_thresholds": {
            "minimum_component_stability": minimum_component_stability,
            "minimum_assignment_stability": minimum_assignment_stability,
            "maximum_component_similarity": maximum_component_similarity,
        },
        "restarts": restarts,
        "max_iter": max_iter,
        "tolerance": tolerance,
        "seed": seed,
        "rank_metrics": [
            {
                "rank": item["rank"],
                "best_relative_error": item["best"]["relative_error"],
                "mean_relative_error": float(np.mean(item["relative_errors"])),
                "relative_error_sd": float(np.std(item["relative_errors"], ddof=0)),
                "component_stability": item["component_stability"],
                "assignment_stability": item["assignment_stability"],
                "converged_restarts": item["converged_restarts"],
                "iterations": item["iterations"],
            }
            for item in rank_results
        ],
        "selected_relative_error": selected["best"]["relative_error"],
        "selected_mse": float(np.mean((values - w @ h) ** 2)),
        "maximum_component_similarity": maximum_similarity,
        "top_features": top,
        "dominant_component_by_sample": {sample: components[int(index)] for sample, index in zip(samples, np.argmax(h, axis=0), strict=True)},
        "quality_findings": quality_findings,
        "quality_status": "passed" if not quality_findings else "warning",
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--loadings", type=Path, required=True)
    parser.add_argument("--exposures", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--ranks", required=True)
    parser.add_argument("--restarts", type=int, required=True)
    parser.add_argument("--max-iter", type=int, required=True)
    parser.add_argument("--tolerance", type=float, required=True)
    parser.add_argument("--top-genes", type=int, required=True)
    parser.add_argument("--selection-error-gap", type=float, required=True)
    parser.add_argument("--minimum-component-stability", type=float, required=True)
    parser.add_argument("--minimum-assignment-stability", type=float, required=True)
    parser.add_argument("--maximum-component-similarity", type=float, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    factorize(
        args.matrix, args.features, args.samples, args.loadings, args.exposures, args.report,
        ranks_text=args.ranks, restarts=args.restarts, max_iter=args.max_iter, tolerance=args.tolerance,
        top_genes=args.top_genes,
        selection_error_gap=args.selection_error_gap,
        minimum_component_stability=args.minimum_component_stability,
        minimum_assignment_stability=args.minimum_assignment_stability,
        maximum_component_similarity=args.maximum_component_similarity,
        seed=args.seed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
