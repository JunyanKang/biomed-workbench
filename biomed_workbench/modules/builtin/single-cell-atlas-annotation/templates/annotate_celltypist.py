#!/usr/bin/env python3
"""Map query cells with a declared CellTypist model and preserve low-confidence unknowns."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform

import anndata
import celltypist
import numpy as np
import pandas as pd
import scanpy as sc
from scipy import sparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-h5ad", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output-h5ad", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--raw-count-location", required=True)
    parser.add_argument("--mode", choices=("best match", "prob match"), default="best match")
    parser.add_argument("--probability-threshold", type=float, default=0.5)
    parser.add_argument("--unknown-threshold", type=float, default=0.5)
    parser.add_argument("--cluster-key", default="")
    parser.add_argument("--majority-voting", choices=("false", "true"), default="false")
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def counts_from(adata: anndata.AnnData, location: str):
    if location == "X":
        matrix = adata.X
    elif location.startswith("layers.") and location[7:] in adata.layers:
        matrix = adata.layers[location[7:]]
    else:
        raise ValueError("raw-count-location must be X or an existing layers.NAME")
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix).reshape(-1)
    if values.size == 0 or not np.isfinite(values).all() or np.any(values < 0) or not np.allclose(values, np.rint(values), rtol=0, atol=1e-8):
        raise ValueError("CellTypist mapping requires finite nonnegative integer-like counts")
    return matrix.copy()


def main() -> int:
    args = parse_args()
    source, model_path = Path(args.query_h5ad).resolve(strict=True), Path(args.model).resolve(strict=True)
    output, report_path = Path(args.output_h5ad), Path(args.report)
    if output.exists() or report_path.exists():
        raise FileExistsError("refusing to overwrite declared outputs")
    if not 0 < args.probability_threshold < 1 or not 0 < args.unknown_threshold < 1:
        raise ValueError("probability thresholds must be in (0, 1)")
    query = anndata.read_h5ad(source)
    if not query.obs_names.is_unique or not query.var_names.is_unique:
        raise ValueError("query cells and genes must be unique")
    counts = counts_from(query, args.raw_count_location)
    query.layers["counts"] = counts
    work = anndata.AnnData(X=counts.copy(), obs=query.obs.copy(), var=query.var.copy())
    sc.pp.normalize_total(work, target_sum=10_000)
    sc.pp.log1p(work)
    majority = args.majority_voting == "true"
    over_clustering = None
    if majority:
        if not args.cluster_key or args.cluster_key not in work.obs or work.obs[args.cluster_key].isna().any():
            raise ValueError("majority voting requires a complete declared cluster-key")
        over_clustering = args.cluster_key
    model = celltypist.models.Model.load(str(model_path))
    model_overlap = int(query.var_names.intersection(pd.Index(model.features)).size)
    if model_overlap < 20:
        raise ValueError("query and CellTypist model have insufficient feature overlap")
    predictions = celltypist.annotate(work, model=model, mode=args.mode, p_thres=args.probability_threshold, majority_voting=majority, over_clustering=over_clustering, use_GPU=False)
    probabilities = predictions.probability_matrix.reindex(index=query.obs_names)
    predicted = predictions.predicted_labels.reindex(index=query.obs_names)
    label_field = "majority_voting" if majority and "majority_voting" in predicted else "predicted_labels"
    raw_labels = predicted[label_field].astype(str)
    confidence = probabilities.max(axis=1).astype(float)
    if confidence.isna().any() or np.any((confidence < 0) | (confidence > 1)):
        raise RuntimeError("CellTypist probabilities are absent or invalid")
    reviewed = raw_labels.where(confidence >= args.unknown_threshold, "Unknown")
    query.obs["celltypist_label_raw"] = pd.Categorical(raw_labels)
    query.obs["celltypist_confidence"] = confidence
    query.obs["celltypist_label_review"] = pd.Categorical(reviewed)
    query.obsm["celltypist_probabilities"] = probabilities
    query.uns["celltypist_mapping"] = {"model_sha256": sha256(model_path), "model_name": model_path.name, "mode": args.mode, "probability_threshold": args.probability_threshold, "unknown_threshold": args.unknown_threshold, "majority_voting": majority, "raw_count_location": args.raw_count_location}
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    query.write_h5ad(output, compression="gzip")
    reloaded = anndata.read_h5ad(output)
    restored = reloaded.layers["counts"]
    left = restored.toarray() if sparse.issparse(restored) else np.asarray(restored)
    right = counts.toarray() if sparse.issparse(counts) else np.asarray(counts)
    if reloaded.shape != query.shape or not np.array_equal(reloaded.obs_names, query.obs_names) or not np.array_equal(left, right) or "celltypist_probabilities" not in reloaded.obsm:
        raise RuntimeError("CellTypist output did not reload with source counts, cells, and probabilities")
    report = {"input_sha256": sha256(source), "model_sha256": sha256(model_path), "cells": int(query.n_obs), "features": int(query.n_vars), "model_feature_overlap": model_overlap, "prediction_label_count": int(probabilities.shape[1]), "raw_label_counts": {str(k): int(v) for k, v in raw_labels.value_counts().items()}, "review_label_counts": {str(k): int(v) for k, v in reviewed.value_counts().items()}, "unknown_cells": int((reviewed == "Unknown").sum()), "median_confidence": float(confidence.median()), "raw_counts_preserved": True, "output_reloaded": True, "versions": {"python": platform.python_version(), "celltypist": importlib.metadata.version("celltypist"), "anndata": importlib.metadata.version("anndata")}, "quality_status": "review-required"}
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
