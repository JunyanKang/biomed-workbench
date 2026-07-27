#!/usr/bin/env python3
"""Benchmark one classical single-cell integration method without label leakage.

Codex must inspect and adapt this project template before execution. Labels are
used only for post hoc biological-conservation metrics, never for integration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
from pathlib import Path

import anndata
import numpy as np
import pandas as pd
import scanpy as sc
import scanpy.external as sce
import scipy
from scipy import sparse
from scipy.sparse.csgraph import connected_components
import sklearn
from sklearn.metrics import silhouette_score
from sklearn.neighbors import NearestNeighbors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-h5ad", required=True)
    parser.add_argument("--output-h5ad", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--method", choices=("harmony", "scanorama", "bbknn"), required=True)
    parser.add_argument("--raw-count-location", required=True)
    parser.add_argument("--batch-key", required=True)
    parser.add_argument("--sample-key", required=True)
    parser.add_argument("--evaluation-label-key", required=True)
    parser.add_argument("--unknown-label", required=True)
    parser.add_argument("--n-top-genes", type=int, required=True)
    parser.add_argument("--n-pcs", type=int, required=True)
    parser.add_argument("--n-neighbors", type=int, required=True)
    parser.add_argument("--maximum-label-purity-loss", type=float, required=True)
    parser.add_argument("--minimum-batch-entropy-gain", type=float, required=True)
    parser.add_argument("--minimum-label-connectivity", type=float, required=True)
    parser.add_argument("--silhouette-max-cells", type=int, default=5000)
    parser.add_argument("--seed", type=int, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def matrix_values(matrix) -> np.ndarray:
    return np.asarray(matrix.data) if sparse.issparse(matrix) else np.asarray(matrix).reshape(-1)


def raw_counts(adata: anndata.AnnData, location: str):
    if location == "X":
        return adata.X
    if location.startswith("layers.") and location[7:] in adata.layers:
        return adata.layers[location[7:]]
    raise ValueError("raw-count-location must be X or an existing layers.NAME entry")


def validate_counts(matrix) -> None:
    values = matrix_values(matrix)
    if values.size and (not np.isfinite(values).all() or float(values.min()) < 0):
        raise ValueError("raw counts must contain finite nonnegative values")
    if values.size and not np.allclose(values, np.rint(values), rtol=0, atol=1e-8):
        raise ValueError("raw count location is not integer-like")


def normalized_metadata(adata: anndata.AnnData, fields: list[str]) -> pd.DataFrame:
    missing = [field for field in fields if field not in adata.obs]
    if missing:
        raise ValueError(f"required observation metadata is missing: {', '.join(missing)}")
    result = adata.obs.loc[:, fields].copy()
    for field in fields:
        if result[field].isna().any():
            raise ValueError(f"metadata field contains missing values: {field}")
        result[field] = result[field].astype(str).str.strip()
        if result[field].eq("").any():
            raise ValueError(f"metadata field contains empty values: {field}")
    return result


def representation_neighbors(representation: np.ndarray, count: int) -> np.ndarray:
    model = NearestNeighbors(n_neighbors=count + 1, metric="euclidean")
    indices = model.fit(representation).kneighbors(representation, return_distance=False)
    rows = []
    for index, row in enumerate(indices):
        selected = row[row != index][:count]
        if len(selected) != count:
            raise ValueError("baseline or integrated representation has insufficient distinct neighbors")
        rows.append(selected)
    return np.asarray(rows, dtype=int)


def graph_neighbors(distances: sparse.spmatrix, count: int) -> np.ndarray:
    matrix = sparse.csr_matrix(distances)
    rows = []
    for row_index in range(matrix.shape[0]):
        start, stop = matrix.indptr[row_index], matrix.indptr[row_index + 1]
        indices = matrix.indices[start:stop]
        values = matrix.data[start:stop]
        order = np.argsort(values, kind="stable")
        selected = indices[order[:count]]
        if len(selected) < count:
            raise ValueError("integrated graph has fewer neighbors than the declared evaluation count")
        rows.append(selected)
    return np.asarray(rows, dtype=int)


def batch_entropy(neighbors: np.ndarray, batches: np.ndarray) -> float:
    levels = sorted(set(batches.tolist()))
    denominator = math.log(len(levels))
    values = []
    for row in neighbors:
        counts = np.asarray([(batches[row] == level).sum() for level in levels], dtype=float)
        probabilities = counts[counts > 0] / counts.sum()
        values.append(float(-(probabilities * np.log(probabilities)).sum() / denominator))
    return float(np.mean(values))


def label_purity(neighbors: np.ndarray, labels: np.ndarray, known: np.ndarray) -> float:
    values = []
    for index in np.flatnonzero(known):
        selected = neighbors[index]
        selected = selected[known[selected]]
        if selected.size:
            values.append(float(np.mean(labels[selected] == labels[index])))
    if not values:
        raise ValueError("no known-label neighborhood is available for biological-conservation evaluation")
    return float(np.mean(values))


def label_connectivity(neighbors: np.ndarray, labels: np.ndarray, known: np.ndarray) -> tuple[float, dict[str, float]]:
    n_obs = len(labels)
    source = np.repeat(np.arange(n_obs), neighbors.shape[1])
    target = neighbors.reshape(-1)
    graph = sparse.csr_matrix((np.ones(len(source)), (source, target)), shape=(n_obs, n_obs))
    graph = graph.maximum(graph.transpose())
    scores = {}
    for label in sorted(set(labels[known].tolist())):
        indices = np.flatnonzero(known & (labels == label))
        if len(indices) < 2:
            continue
        _, components = connected_components(graph[indices][:, indices], directed=False)
        largest = int(np.bincount(components).max())
        scores[str(label)] = largest / len(indices)
    if not scores:
        raise ValueError("known labels do not support graph-connectivity evaluation")
    return float(np.mean(list(scores.values()))), scores


def safe_silhouette(
    representation: np.ndarray,
    groups: np.ndarray,
    max_cells: int,
    seed: int,
) -> float | None:
    if len(set(groups.tolist())) < 2 or len(groups) <= len(set(groups.tolist())):
        return None
    if len(groups) > max_cells:
        selected = np.sort(
            np.random.default_rng(seed).choice(len(groups), max_cells, replace=False)
        )
        representation = representation[selected]
        groups = groups[selected]
    return float(silhouette_score(representation, groups, metric="euclidean"))


def metrics(
    representation: np.ndarray,
    neighbors: np.ndarray,
    batches: np.ndarray,
    labels: np.ndarray,
    known: np.ndarray,
    silhouette_max_cells: int,
    seed: int,
) -> dict[str, object]:
    connectivity, by_label = label_connectivity(neighbors, labels, known)
    return {
        "batch_neighbor_entropy": batch_entropy(neighbors, batches),
        "label_neighbor_purity": label_purity(neighbors, labels, known),
        "mean_label_graph_connectivity": connectivity,
        "label_graph_connectivity": by_label,
        "batch_silhouette": safe_silhouette(
            representation, batches, silhouette_max_cells, seed
        ),
        "label_silhouette": safe_silhouette(
            representation[known],
            labels[known],
            silhouette_max_cells,
            seed + 1,
        ),
    }


def package_version(name: str) -> str:
    from importlib.metadata import version
    return version(name)


def main() -> int:
    args = parse_args()
    source = Path(args.input_h5ad).resolve(strict=True)
    source_digest = sha256(source)
    output = Path(args.output_h5ad)
    report_path = Path(args.report)
    for path in (output, report_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f"refusing to overwrite output: {path.name}")
    if (
        args.n_top_genes < 3
        or args.n_pcs < 2
        or args.n_neighbors < 2
        or args.silhouette_max_cells < 100
    ):
        raise ValueError("feature, component, and neighbor parameters are too small")
    if not 0 <= args.maximum_label_purity_loss <= 1 or not -1 <= args.minimum_batch_entropy_gain <= 1 or not 0 <= args.minimum_label_connectivity <= 1:
        raise ValueError("integration quality thresholds are invalid")

    source_adata = sc.read_h5ad(source)
    if source_adata.n_obs <= args.n_neighbors + 1 or source_adata.n_vars < 4:
        raise ValueError("input is too small for the declared integration benchmark")
    if not source_adata.obs_names.is_unique or not source_adata.var_names.is_unique:
        raise ValueError("cell and feature identifiers must be unique")
    metadata = normalized_metadata(source_adata, [args.batch_key, args.sample_key, args.evaluation_label_key])
    batches = metadata[args.batch_key].to_numpy()
    samples = metadata[args.sample_key].to_numpy()
    labels = metadata[args.evaluation_label_key].to_numpy()
    if len(set(batches.tolist())) < 2 or len(set(samples.tolist())) < 2:
        raise ValueError("integration requires at least two batches and biological samples")
    sample_batch_counts = metadata.groupby(args.sample_key, observed=True)[args.batch_key].nunique()
    if not bool((sample_batch_counts == 1).all()):
        raise ValueError("each biological sample must map to exactly one declared batch")
    known = labels != args.unknown_label
    if int(known.sum()) < 4 or len(set(labels[known].tolist())) < 2:
        raise ValueError("at least two known evaluation labels are required while unknown labels remain retained")
    label_batch_table = pd.crosstab(metadata.loc[known, args.evaluation_label_key], metadata.loc[known, args.batch_key])
    labels_spanning_batches = {str(label): int((row > 0).sum()) for label, row in label_batch_table.iterrows()}
    if any(count < 2 for count in labels_spanning_batches.values()):
        raise ValueError("evaluation label is structurally confined to one batch; integration cannot be adjudicated")

    counts = raw_counts(source_adata, args.raw_count_location)
    validate_counts(counts)
    original_counts = sparse.csr_matrix(counts, dtype=np.int64)
    integration_obs = source_adata.obs.drop(
        columns=[args.evaluation_label_key]
    ).copy()
    if args.evaluation_label_key in integration_obs:
        raise RuntimeError("evaluation labels remain visible to integration backends")
    adata = anndata.AnnData(
        X=original_counts.copy(),
        obs=integration_obs,
        var=source_adata.var.copy(),
    )
    adata.layers["counts"] = original_counts.copy()
    sc.pp.normalize_total(adata, target_sum=10000)
    sc.pp.log1p(adata)
    top_genes = min(args.n_top_genes, adata.n_vars)
    sc.pp.highly_variable_genes(adata, n_top_genes=top_genes, flavor="cell_ranger", batch_key=args.batch_key)
    hvg_count = int(adata.var["highly_variable"].sum())
    if hvg_count < 3:
        raise ValueError("fewer than three batch-aware highly variable genes were selected")
    component_count = min(args.n_pcs, hvg_count - 1, adata.n_obs - 1)
    pca_data = adata[:, adata.var["highly_variable"]].copy()
    sc.pp.scale(pca_data, zero_center=True, max_value=10)
    sc.tl.pca(pca_data, n_comps=component_count, use_highly_variable=False, random_state=args.seed)
    adata.obsm["X_pca"] = np.asarray(pca_data.obsm["X_pca"])
    baseline_representation = np.asarray(adata.obsm["X_pca"])
    baseline_neighbors = representation_neighbors(baseline_representation, args.n_neighbors)
    baseline = metrics(
        baseline_representation,
        baseline_neighbors,
        batches,
        labels,
        known,
        args.silhouette_max_cells,
        args.seed,
    )

    if args.method == "harmony":
        import harmonypy

        harmony = harmonypy.run_harmony(adata.obsm["X_pca"], adata.obs, args.batch_key, random_state=args.seed)
        corrected = np.asarray(harmony.Z_corr)
        if corrected.shape == adata.obsm["X_pca"].shape:
            adata.obsm["X_integrated"] = corrected
        elif corrected.transpose().shape == adata.obsm["X_pca"].shape:
            adata.obsm["X_integrated"] = corrected.transpose()
        else:
            raise ValueError("Harmony corrected representation does not match cells by principal components")
        integrated_representation = np.asarray(adata.obsm["X_integrated"])
        sc.pp.neighbors(adata, n_neighbors=args.n_neighbors, use_rep="X_integrated", random_state=args.seed)
        integrated_neighbors = representation_neighbors(integrated_representation, args.n_neighbors)
    elif args.method == "scanorama":
        # Scanpy's Scanorama wrapper requires contiguous batches. Run it on a
        # stable internal ordering, then restore the original cell order.
        batch_order = np.argsort(batches, kind="stable")
        ordered = adata[batch_order].copy()
        sce.pp.scanorama_integrate(
            ordered,
            args.batch_key,
            basis="X_pca",
            adjusted_basis="X_integrated",
            approx=False,
        )
        corrected = np.asarray(ordered.obsm["X_integrated"])
        integrated_representation = np.empty_like(corrected)
        integrated_representation[batch_order] = corrected
        adata.obsm["X_integrated"] = integrated_representation
        sc.pp.neighbors(adata, n_neighbors=args.n_neighbors, use_rep="X_integrated", random_state=args.seed)
        integrated_neighbors = representation_neighbors(integrated_representation, args.n_neighbors)
    else:
        within_batch = max(1, math.ceil(args.n_neighbors / len(set(batches.tolist()))))
        sce.pp.bbknn(
            adata, batch_key=args.batch_key, use_rep="X_pca", approx=False, use_faiss=False,
            neighbors_within_batch=within_batch, n_pcs=component_count, trim=None,
            pynndescent_random_state=args.seed,
        )
        integrated_representation = baseline_representation.copy()
        adata.obsm["X_integrated"] = integrated_representation
        integrated_neighbors = graph_neighbors(adata.obsp["distances"], args.n_neighbors)
    sc.tl.umap(adata, random_state=args.seed)
    integrated = metrics(
        integrated_representation,
        integrated_neighbors,
        batches,
        labels,
        known,
        args.silhouette_max_cells,
        args.seed,
    )

    entropy_gain = float(integrated["batch_neighbor_entropy"] - baseline["batch_neighbor_entropy"])
    purity_loss = float(baseline["label_neighbor_purity"] - integrated["label_neighbor_purity"])
    gates = {
        "label_spans_multiple_batches": all(count >= 2 for count in labels_spanning_batches.values()),
        "batch_mixing_gain": entropy_gain >= args.minimum_batch_entropy_gain,
        "label_purity_preserved": purity_loss <= args.maximum_label_purity_loss,
        "label_graph_connected": float(integrated["mean_label_graph_connectivity"]) >= args.minimum_label_connectivity,
        "unknown_labels_retained": True,
        "raw_counts_preserved": bool((adata.layers["counts"] != original_counts).nnz == 0),
    }
    adata.obs[args.evaluation_label_key] = pd.Categorical(labels)
    adata.uns["biomed_integration"] = {
        "method": args.method,
        "batch_key": args.batch_key,
        "sample_key": args.sample_key,
        "evaluation_label_key": args.evaluation_label_key,
        "labels_used_for_training": False,
        "quality_status": "passed" if all(gates.values()) else "blocked",
    }
    adata.write_h5ad(output)
    reloaded = sc.read_h5ad(output)
    reload_valid = (
        reloaded.shape == adata.shape
        and "counts" in reloaded.layers
        and "X_integrated" in reloaded.obsm
        and "X_umap" in reloaded.obsm
        and "connectivities" in reloaded.obsp
        and np.array_equal(reloaded.obs_names, source_adata.obs_names)
        and np.array_equal(reloaded.var_names, source_adata.var_names)
        and all(
            np.array_equal(
                reloaded.obs[column].astype(str).to_numpy(),
                source_adata.obs[column].astype(str).to_numpy(),
            )
            for column in source_adata.obs.columns
        )
        and (sparse.csr_matrix(reloaded.layers["counts"]) != original_counts).nnz == 0
    )
    if not reload_valid:
        raise RuntimeError("integrated h5ad failed structural or raw-count reload validation")

    report = {
        "schema_version": 2,
        "method": args.method,
        "quality_status": "passed" if all(gates.values()) else "blocked",
        "input": {"filename": source.name, "sha256": source_digest, "cells": adata.n_obs, "features": adata.n_vars, "raw_count_location": args.raw_count_location},
        "design": {
            "batch_key": args.batch_key, "sample_key": args.sample_key,
            "evaluation_label_key": args.evaluation_label_key, "unknown_label": args.unknown_label,
            "batch_count": len(set(batches.tolist())), "sample_count": len(set(samples.tolist())),
            "known_label_count": len(set(labels[known].tolist())), "unknown_cells": int((~known).sum()),
            "labels_spanning_batches": labels_spanning_batches, "labels_used_for_training": False,
            "evaluation_label_removed_before_backend_execution": True,
        },
        "parameters": {
            "n_top_genes": args.n_top_genes, "selected_hvgs": hvg_count, "n_pcs": component_count,
            "n_neighbors": args.n_neighbors, "seed": args.seed,
            "maximum_label_purity_loss": args.maximum_label_purity_loss,
            "minimum_batch_entropy_gain": args.minimum_batch_entropy_gain,
            "minimum_label_connectivity": args.minimum_label_connectivity,
            "silhouette_max_cells": args.silhouette_max_cells,
        },
        "baseline_metrics": baseline,
        "integrated_metrics": integrated,
        "metric_deltas": {"batch_neighbor_entropy_gain": entropy_gain, "label_neighbor_purity_loss": purity_loss},
        "quality_gates": gates,
        "source_immutable": sha256(source) == source_digest,
        "cell_feature_and_metadata_identity_preserved": True,
        "reload_validation_passed": True,
        "output": {"filename": output.name, "sha256": sha256(output)},
        "versions": {
            "python": platform.python_version(), "scanpy": sc.__version__, "anndata": anndata.__version__,
            "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__, "scikit-learn": sklearn.__version__,
            "harmonypy": package_version("harmonypy"), "scanorama": package_version("scanorama"), "bbknn": package_version("bbknn"),
            "umap-learn": package_version("umap-learn"),
        },
    }
    if not report["source_immutable"]:
        raise RuntimeError("source H5AD changed during integration")
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"method": args.method, "quality_status": report["quality_status"], "entropy_gain": entropy_gain, "purity_loss": purity_loss}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
