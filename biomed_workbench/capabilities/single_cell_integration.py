"""Shared scientific contracts for advanced single-cell integration.

The functions in this module deliberately do not perform batch correction.
They validate designs, standardize orthology evidence, compute method-neutral
neighbourhood diagnostics, and adjudicate outputs produced by native tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.csgraph import connected_components
from scipy.spatial.distance import jensenshannon
from scipy.stats import chi2
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    adjusted_rand_score,
    balanced_accuracy_score,
    f1_score,
    normalized_mutual_info_score,
    silhouette_score,
)
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.neighbors import KNeighborsClassifier, NearestNeighbors


SCIB_BATCH_METRICS = (
    "batch_asw",
    "graph_connectivity",
    "ilisi",
    "kbet",
    "pcr_comparison",
)
SCIB_BIOLOGY_METRICS = (
    "ari",
    "cell_cycle_conservation",
    "clisi",
    "hvg_conservation",
    "isolated_label_asw",
    "isolated_label_f1",
    "label_asw",
    "nmi",
    "trajectory_conservation",
)
ORTHOLOGY_RELATIONS = frozenset({"one-to-one", "one-to-many", "many-to-many"})
FORBIDDEN_INFERENCE_INPUTS = frozenset(
    {
        "integrated",
        "integrated_expression",
        "corrected_expression",
        "denoised_expression",
        "imputed_expression",
        "latent",
        "embedding",
    }
)


@dataclass(frozen=True)
class IntegrationThresholds:
    minimum_batch_score: float = 0.50
    minimum_biology_score: float = 0.60
    maximum_label_purity_loss: float = 0.10
    minimum_unknown_retention: float = 1.0

    def validate(self) -> None:
        for name, value in vars(self).items():
            if not np.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be finite and between zero and one")


def _clean_series(frame: pd.DataFrame, key: str) -> pd.Series:
    if key not in frame:
        raise ValueError(f"required metadata field is missing: {key}")
    values = frame[key]
    if values.isna().any():
        raise ValueError(f"metadata field contains missing values: {key}")
    values = values.astype(str).str.strip()
    if values.eq("").any():
        raise ValueError(f"metadata field contains empty values: {key}")
    return values


def validate_crossed_design(
    observations: pd.DataFrame,
    *,
    sample_key: str,
    batch_key: str,
    biology_keys: Sequence[str],
    species_key: str | None = None,
) -> dict[str, object]:
    """Validate sample nesting and reject perfect technical confounding."""

    if observations.empty or not observations.index.is_unique:
        raise ValueError("observations must be nonempty with unique cell identifiers")
    samples = _clean_series(observations, sample_key)
    batches = _clean_series(observations, batch_key)
    if samples.nunique() < 2 or batches.nunique() < 2:
        raise ValueError("integration requires at least two samples and batches")
    nesting = pd.crosstab(samples, batches)
    if (nesting.gt(0).sum(axis=1) != 1).any():
        raise ValueError("each biological sample must map to exactly one batch")
    biology_summary: dict[str, object] = {}
    for key in biology_keys:
        biology = _clean_series(observations, key)
        table = pd.crosstab(biology, batches)
        if table.shape[0] > 1 and table.shape[1] > 1:
            perfectly_confounded = all((row > 0).sum() == 1 for _, row in table.iterrows())
            if perfectly_confounded:
                raise ValueError(f"target biology is perfectly confounded with batch: {key}")
        biology_summary[key] = {
            "levels": int(biology.nunique()),
            "batch_support": {
                str(level): int((row > 0).sum()) for level, row in table.iterrows()
            },
        }
    species = None
    if species_key is not None:
        species = _clean_series(observations, species_key)
        if species.nunique() < 2:
            raise ValueError("cross-species integration requires at least two species")
    return {
        "cells": int(len(observations)),
        "samples": int(samples.nunique()),
        "batches": int(batches.nunique()),
        "species": int(species.nunique()) if species is not None else None,
        "biology": biology_summary,
        "sample_to_batch_is_one_to_one": True,
    }


def build_orthology_ledger(records: pd.DataFrame) -> pd.DataFrame:
    """Normalize an auditable one-to-one/one-to-many/many-to-many ledger."""

    required = {
        "source_species",
        "source_gene",
        "target_species",
        "target_gene",
        "orthogroup_id",
        "relation",
        "confidence",
        "evidence_source",
        "release",
    }
    missing = sorted(required - set(records.columns))
    if missing:
        raise ValueError(f"orthology ledger is missing fields: {', '.join(missing)}")
    result = records.loc[:, sorted(required)].copy()
    for key in required - {"confidence"}:
        result[key] = result[key].astype(str).str.strip()
        if result[key].eq("").any():
            raise ValueError(f"orthology ledger contains empty values: {key}")
    result["confidence"] = pd.to_numeric(result["confidence"], errors="raise")
    if not np.isfinite(result["confidence"]).all() or not result["confidence"].between(0, 1).all():
        raise ValueError("orthology confidence must be finite and between zero and one")
    invalid = sorted(set(result["relation"]) - ORTHOLOGY_RELATIONS)
    if invalid:
        raise ValueError(f"unsupported orthology relations: {', '.join(invalid)}")
    if (result["source_species"] == result["target_species"]).any():
        raise ValueError("orthology ledger must connect different species")
    pair_columns = ["source_species", "source_gene", "target_species", "target_gene"]
    duplicated = result.duplicated(pair_columns, keep=False)
    if duplicated.any():
        competing = result.loc[duplicated].groupby(pair_columns, observed=True).size()
        if (competing > 1).any():
            raise ValueError("duplicate cross-species gene pairs require prior evidence reconciliation")
    return result.sort_values(
        ["orthogroup_id", "source_species", "source_gene", "target_species", "target_gene"],
        kind="stable",
    ).reset_index(drop=True)


def orthology_coverage(
    ledger: pd.DataFrame,
    feature_sets: Mapping[str, Iterable[str]],
) -> dict[str, object]:
    normalized = build_orthology_ledger(ledger)
    result: dict[str, object] = {"relations": normalized["relation"].value_counts().to_dict()}
    for species, features in feature_sets.items():
        feature_set = set(map(str, features))
        mapped = set(
            normalized.loc[normalized["source_species"] == species, "source_gene"]
        ) | set(normalized.loc[normalized["target_species"] == species, "target_gene"])
        result[species] = {
            "features": len(feature_set),
            "mapped_features": len(feature_set & mapped),
            "coverage": len(feature_set & mapped) / len(feature_set) if feature_set else 0.0,
        }
    return result


def projection_jsd(
    observed: pd.DataFrame,
    expected: pd.DataFrame,
) -> dict[str, object]:
    """Compare matched probability/abundance matrices by spot and cell type.

    JSD is an accuracy metric only when ``expected`` is independent truth or a
    held-out mixture. Between two inferred matrices it measures concordance.
    """

    if observed.empty or expected.empty:
        raise ValueError("JSD matrices must be nonempty")
    if not observed.index.is_unique or not expected.index.is_unique:
        raise ValueError("JSD matrix row identifiers must be unique")
    if not observed.columns.is_unique or not expected.columns.is_unique:
        raise ValueError("JSD matrix columns must be unique")
    if set(observed.index) != set(expected.index) or set(observed.columns) != set(expected.columns):
        raise ValueError("JSD matrices must contain the same rows and columns")
    right = expected.loc[observed.index, observed.columns]
    left_values = observed.to_numpy(dtype=float)
    right_values = right.to_numpy(dtype=float)
    if (
        not np.isfinite(left_values).all()
        or not np.isfinite(right_values).all()
        or (left_values < 0).any()
        or (right_values < 0).any()
    ):
        raise ValueError("JSD inputs must be finite and nonnegative")
    if (left_values.sum(axis=1) <= 0).any() or (right_values.sum(axis=1) <= 0).any():
        raise ValueError("each JSD matrix row must have positive mass")
    left_rows = left_values / left_values.sum(axis=1, keepdims=True)
    right_rows = right_values / right_values.sum(axis=1, keepdims=True)
    spot_scores = np.asarray(
        [jensenshannon(left_rows[i], right_rows[i], base=2.0) ** 2 for i in range(len(left_rows))]
    )
    if (left_values.sum(axis=0) <= 0).any() or (right_values.sum(axis=0) <= 0).any():
        type_scores = {
            str(column): None
            for column, left_total, right_total in zip(
                observed.columns, left_values.sum(axis=0), right_values.sum(axis=0)
            )
            if left_total <= 0 or right_total <= 0
        }
    else:
        type_scores = {}
    for index, column in enumerate(observed.columns):
        if str(column) in type_scores:
            continue
        left = left_values[:, index] / left_values[:, index].sum()
        right = right_values[:, index] / right_values[:, index].sum()
        type_scores[str(column)] = float(jensenshannon(left, right, base=2.0) ** 2)
    return {
        "spot_jsd": {str(key): float(value) for key, value in zip(observed.index, spot_scores)},
        "mean_spot_jsd": float(np.mean(spot_scores)),
        "median_spot_jsd": float(np.median(spot_scores)),
        "cell_type_jsd": type_scores,
        "mean_cell_type_jsd": float(
            np.mean([value for value in type_scores.values() if value is not None])
        ),
        "range": [0.0, 1.0],
        "lower_is_more_similar": True,
    }


def _neighbors(embedding: np.ndarray, n_neighbors: int) -> np.ndarray:
    matrix = np.asarray(embedding, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] <= n_neighbors or matrix.shape[1] < 2:
        raise ValueError("embedding has insufficient cells or dimensions")
    if not np.isfinite(matrix).all():
        raise ValueError("embedding contains nonfinite values")
    model = NearestNeighbors(n_neighbors=n_neighbors + 1).fit(matrix)
    indices = model.kneighbors(matrix, return_distance=False)
    return np.asarray([row[row != index][:n_neighbors] for index, row in enumerate(indices)])


def _normalized_entropy(values: np.ndarray) -> float:
    _, counts = np.unique(values, return_counts=True)
    if len(counts) < 2:
        return 0.0
    probabilities = counts / counts.sum()
    return float(-(probabilities * np.log(probabilities)).sum() / log(len(counts)))


def _local_inverse_simpson(neighbors: np.ndarray, groups: np.ndarray) -> float:
    maximum = len(np.unique(groups))
    if maximum < 2:
        return 0.0
    scores = []
    for row in neighbors:
        _, counts = np.unique(groups[row], return_counts=True)
        probabilities = counts / counts.sum()
        raw = 1.0 / np.square(probabilities).sum()
        scores.append((raw - 1.0) / (maximum - 1.0))
    return float(np.median(scores))


def _kbet_acceptance(neighbors: np.ndarray, batches: np.ndarray, alpha: float = 0.05) -> float:
    levels, global_counts = np.unique(batches, return_counts=True)
    expected = global_counts / global_counts.sum() * neighbors.shape[1]
    accepted = []
    for row in neighbors:
        observed = np.asarray([(batches[row] == level).sum() for level in levels])
        statistic = float(np.sum(np.square(observed - expected) / np.maximum(expected, 1e-12)))
        p_value = float(chi2.sf(statistic, len(levels) - 1))
        accepted.append(p_value >= alpha)
    return float(np.mean(accepted))


def _graph_connectivity(neighbors: np.ndarray, labels: np.ndarray) -> float:
    n = len(labels)
    source = np.repeat(np.arange(n), neighbors.shape[1])
    target = neighbors.reshape(-1)
    graph = sparse.csr_matrix((np.ones(len(source)), (source, target)), shape=(n, n))
    graph = graph.maximum(graph.T)
    scores = []
    for label in np.unique(labels):
        selected = np.flatnonzero(labels == label)
        if len(selected) < 2:
            continue
        _, components = connected_components(graph[selected][:, selected], directed=False)
        scores.append(np.bincount(components).max() / len(selected))
    if not scores:
        raise ValueError("labels do not support graph-connectivity evaluation")
    return float(np.mean(scores))


def _safe_silhouette(embedding: np.ndarray, groups: np.ndarray) -> float | None:
    if len(np.unique(groups)) < 2 or len(groups) <= len(np.unique(groups)):
        return None
    return float(silhouette_score(embedding, groups))


def integration_diagnostics(
    embedding: np.ndarray,
    *,
    batch: Sequence[object],
    labels: Sequence[object],
    clusters: Sequence[object] | None = None,
    n_neighbors: int = 30,
) -> dict[str, float | None]:
    """Compute deterministic scIB-aligned neighbourhood diagnostics."""

    batch_values = np.asarray(batch, dtype=str)
    label_values = np.asarray(labels, dtype=str)
    if len(batch_values) != len(label_values) or len(batch_values) != len(embedding):
        raise ValueError("embedding and metadata lengths differ")
    neighbors = _neighbors(embedding, n_neighbors)
    local_batch_entropy = float(
        np.mean([_normalized_entropy(batch_values[row]) for row in neighbors])
    )
    local_label_purity = float(
        np.mean([np.mean(label_values[row] == label_values[index]) for index, row in enumerate(neighbors)])
    )
    batch_asw_raw = _safe_silhouette(np.asarray(embedding), batch_values)
    label_asw_raw = _safe_silhouette(np.asarray(embedding), label_values)
    result: dict[str, float | None] = {
        "batch_entropy": local_batch_entropy,
        "batch_asw": None if batch_asw_raw is None else float(1 - abs(batch_asw_raw)),
        "graph_connectivity": _graph_connectivity(neighbors, label_values),
        "ilisi": _local_inverse_simpson(neighbors, batch_values),
        "clisi": float(1 - _local_inverse_simpson(neighbors, label_values)),
        "kbet": _kbet_acceptance(neighbors, batch_values),
        "label_asw": label_asw_raw,
        "label_neighbor_purity": local_label_purity,
        "ari": None,
        "nmi": None,
    }
    if clusters is not None:
        cluster_values = np.asarray(clusters, dtype=str)
        if len(cluster_values) != len(label_values):
            raise ValueError("cluster and label lengths differ")
        result["ari"] = float(adjusted_rand_score(label_values, cluster_values))
        result["nmi"] = float(normalized_mutual_info_score(label_values, cluster_values))
    return result


def require_complete_scib_metrics(metrics: Mapping[str, object]) -> None:
    missing = sorted((set(SCIB_BATCH_METRICS) | set(SCIB_BIOLOGY_METRICS)) - set(metrics))
    if missing:
        raise ValueError(f"official scIB output is incomplete: {', '.join(missing)}")
    invalid = [
        key for key in SCIB_BATCH_METRICS + SCIB_BIOLOGY_METRICS
        if metrics[key] is not None and not np.isfinite(float(metrics[key]))
    ]
    if invalid:
        raise ValueError(f"official scIB output has nonfinite metrics: {', '.join(invalid)}")


def leave_one_species_out_validation(
    embedding: np.ndarray,
    *,
    species: Sequence[object],
    labels: Sequence[object],
    n_neighbors: int = 15,
) -> dict[str, object]:
    species_values = np.asarray(species, dtype=str)
    label_values = np.asarray(labels, dtype=str)
    matrix = np.asarray(embedding, dtype=float)
    if len(np.unique(species_values)) < 2:
        raise ValueError("leave-one-species-out validation requires at least two species")
    folds = []
    for train, test in LeaveOneGroupOut().split(matrix, label_values, species_values):
        classifier = KNeighborsClassifier(n_neighbors=min(n_neighbors, len(train)))
        classifier.fit(matrix[train], label_values[train])
        predicted = classifier.predict(matrix[test])
        folds.append(
            {
                "held_out_species": str(np.unique(species_values[test])[0]),
                "cells": int(len(test)),
                "balanced_accuracy": float(balanced_accuracy_score(label_values[test], predicted)),
                "macro_f1": float(f1_score(label_values[test], predicted, average="macro")),
                "supported_truth_labels": sorted(set(label_values[test]) & set(label_values[train])),
                "unsupported_truth_labels": sorted(set(label_values[test]) - set(label_values[train])),
            }
        )
    return {
        "folds": folds,
        "mean_balanced_accuracy": float(np.mean([fold["balanced_accuracy"] for fold in folds])),
        "mean_macro_f1": float(np.mean([fold["macro_f1"] for fold in folds])),
    }


def species_predictability(
    embedding: np.ndarray,
    species: Sequence[object],
    *,
    seed: int = 0,
) -> float:
    """Estimate residual species signal without requiring it to vanish."""

    values = np.asarray(species, dtype=str)
    from sklearn.model_selection import StratifiedKFold

    minimum_class = int(pd.Series(values).value_counts().min())
    if minimum_class < 2:
        raise ValueError("species predictability requires at least two observations per species")
    splitter = StratifiedKFold(
        n_splits=min(5, minimum_class),
        shuffle=True,
        random_state=seed,
    )
    scores = []
    matrix = np.asarray(embedding)
    for train, test in splitter.split(matrix, values):
        model = LogisticRegression(max_iter=2000, random_state=seed)
        model.fit(matrix[train], values[train])
        scores.append(float(np.mean(model.predict(matrix[test]) == values[test])))
    return float(np.mean(scores))


def validate_inference_input(
    *,
    expression_semantics: str,
    sample_key: str,
    donor_key: str | None,
    species_key: str | None,
) -> None:
    normalized = expression_semantics.strip().lower().replace("-", "_")
    if normalized in FORBIDDEN_INFERENCE_INPUTS:
        raise ValueError("integrated, corrected, imputed, denoised, latent, or embedding values are forbidden for confirmatory differential inference")
    if normalized not in {"raw_counts", "integer_counts", "count_layer"}:
        raise ValueError("confirmatory differential inference requires an immutable raw-count layer")
    if not sample_key.strip():
        raise ValueError("sample_key is required for biological replication")
    if donor_key is not None and not donor_key.strip():
        raise ValueError("donor_key cannot be empty")
    if species_key is not None and not species_key.strip():
        raise ValueError("species_key cannot be empty")


def adjudicate_integration(
    baseline: Mapping[str, float],
    candidate: Mapping[str, float],
    *,
    unknown_retention: float,
    thresholds: IntegrationThresholds = IntegrationThresholds(),
) -> dict[str, object]:
    thresholds.validate()
    batch_score = float(np.mean([candidate["batch_asw"], candidate["ilisi"], candidate["kbet"]]))
    biology_score = float(
        np.mean([candidate["graph_connectivity"], candidate["label_neighbor_purity"], candidate["clisi"]])
    )
    purity_loss = float(baseline["label_neighbor_purity"] - candidate["label_neighbor_purity"])
    gates = {
        "batch_score": batch_score >= thresholds.minimum_batch_score,
        "biology_score": biology_score >= thresholds.minimum_biology_score,
        "label_purity_preserved": purity_loss <= thresholds.maximum_label_purity_loss,
        "unknowns_retained": unknown_retention >= thresholds.minimum_unknown_retention,
    }
    return {
        "batch_score": batch_score,
        "biology_score": biology_score,
        "label_purity_loss": purity_loss,
        "quality_gates": gates,
        "quality_status": "passed" if all(gates.values()) else "blocked",
        "failed_gates": sorted(key for key, passed in gates.items() if not passed),
    }
