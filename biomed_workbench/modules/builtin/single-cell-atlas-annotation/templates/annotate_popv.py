#!/usr/bin/env python3
"""Run a declared popV expert ensemble and preserve consensus disagreement as Unknown."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform

import anndata
import numpy as np
import pandas as pd
import popv
from scipy import sparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-h5ad", required=True)
    parser.add_argument("--reference-h5ad", required=True)
    parser.add_argument("--output-h5ad", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--query-count-layer", required=True)
    parser.add_argument("--reference-count-layer", required=True)
    parser.add_argument("--reference-label-key", required=True)
    parser.add_argument("--reference-batch-key", required=True)
    parser.add_argument("--query-batch-key", required=True)
    parser.add_argument("--methods", required=True)
    parser.add_argument("--minimum-consensus", type=int, required=True)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--seed", type=int, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_counts(adata: anndata.AnnData, layer: str, label: str):
    if layer not in adata.layers:
        raise ValueError(f"{label} count layer is absent")
    matrix = adata.layers[layer]
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix).reshape(-1)
    if values.size == 0 or not np.isfinite(values).all() or np.any(values < 0) or not np.allclose(values, np.rint(values), rtol=0, atol=1e-8):
        raise ValueError(f"{label} counts must be finite nonnegative and integer-like")
    return matrix.copy()


def main() -> int:
    args = parse_args()
    query_path, reference_path = Path(args.query_h5ad).resolve(strict=True), Path(args.reference_h5ad).resolve(strict=True)
    output, report_path, model_dir = Path(args.output_h5ad), Path(args.report), Path(args.model_dir)
    if output.exists() or report_path.exists() or model_dir.exists():
        raise FileExistsError("refusing to overwrite declared outputs")
    methods = [item.strip() for item in args.methods.split(",") if item.strip()]
    available_methods = set(popv.annotation.algorithms_nt.ALL_ALGORITHMS)
    if len(methods) != len(set(methods)):
        raise ValueError("popV methods must be distinct")
    unknown_methods = sorted(set(methods) - available_methods)
    if unknown_methods:
        raise ValueError(f"unknown popV methods: {', '.join(unknown_methods)}")
    if len(methods) < 2 or args.minimum_consensus < 1 or args.minimum_consensus > len(methods):
        raise ValueError("popV requires at least two distinct experts and a valid consensus threshold")
    query, reference = anndata.read_h5ad(query_path), anndata.read_h5ad(reference_path)
    query_counts = validate_counts(query, args.query_count_layer, "query")
    reference_counts = validate_counts(reference, args.reference_count_layer, "reference")
    if not query.obs_names.is_unique or not reference.obs_names.is_unique or not query.var_names.is_unique or not reference.var_names.is_unique:
        raise ValueError("query and reference identifiers must be unique")
    if args.reference_label_key not in reference.obs or reference.obs[args.reference_label_key].isna().any() or reference.obs[args.reference_label_key].nunique() < 2:
        raise ValueError("reference labels are absent, incomplete, or uninformative")
    for adata, key, label in ((reference, args.reference_batch_key, "reference"), (query, args.query_batch_key, "query")):
        if key not in adata.obs or adata.obs[key].isna().any():
            raise ValueError(f"{label} batch field is absent or incomplete")
    overlap = query.var_names.intersection(reference.var_names)
    if overlap.size < 20:
        raise ValueError("query-reference feature overlap is insufficient")
    model_dir.parent.mkdir(parents=True, exist_ok=True)
    popv.settings.seed = args.seed
    popv.settings.n_jobs = 1
    popv.settings.cuml = False
    popv.settings.compute_umap_embedding = False
    popv.settings.return_probabilities = True
    processor = popv.preprocessing.Process_Query(query.copy(), reference.copy(), ref_labels_key=args.reference_label_key, ref_batch_key=args.reference_batch_key, cl_obo_folder=False, query_batch_key=args.query_batch_key, query_layer_key=args.query_count_layer, ref_layer_key=args.reference_count_layer, prediction_mode="retrain", unknown_celltype_label="Unknown", n_samples_per_label=None, save_path_trained_models=str(model_dir), hvg=None)
    combined = processor.adata
    popv.annotation.annotate_data(combined, methods=methods, save_path=None)
    query_result = combined[combined.obs["_dataset"] == "query"].copy()
    if query_result.n_obs == 0 or "popv_majority_vote_prediction" not in query_result.obs or "popv_majority_vote_score" not in query_result.obs:
        raise RuntimeError("popV did not produce query consensus evidence")
    unexpected_cells = query_result.obs_names.difference(query.obs_names)
    if len(unexpected_cells):
        raise RuntimeError("popV returned cells that are absent from the declared query")
    mapped_names = query_result.obs_names
    omitted_names = query.obs_names.difference(mapped_names)
    scores = pd.Series(0, index=query.obs_names, dtype=int)
    scores.loc[mapped_names] = pd.to_numeric(
        query_result.obs["popv_majority_vote_score"].astype(str), errors="raise"
    ).astype(int)
    raw_labels = pd.Series("Unknown", index=query.obs_names, dtype=object)
    raw_labels.loc[mapped_names] = query_result.obs["popv_majority_vote_prediction"].astype(str)
    reviewed = raw_labels.where(scores >= args.minimum_consensus, "Unknown")
    query.obs["popv_label_raw"] = pd.Categorical(raw_labels)
    query.obs["popv_consensus_count"] = scores
    query.obs["popv_label_review"] = pd.Categorical(reviewed)
    query.obs["popv_mapping_status"] = pd.Categorical(
        pd.Series("mapped", index=query.obs_names).where(~query.obs_names.isin(omitted_names), "not-mapped-by-popv-preprocessing")
    )
    prediction_keys = list(combined.uns["prediction_keys"])
    for method_key in prediction_keys:
        method_labels = pd.Series("Unknown", index=query.obs_names, dtype=object)
        method_labels.loc[mapped_names] = query_result.obs[method_key].astype(str)
        query.obs[method_key] = pd.Categorical(method_labels)
        probability_key = f"{method_key}_probabilities"
        if probability_key in query_result.obs:
            method_confidence = pd.Series(np.nan, index=query.obs_names, dtype=float)
            method_confidence.loc[mapped_names] = pd.to_numeric(
                query_result.obs[probability_key], errors="coerce"
            ).to_numpy()
            query.obs[probability_key] = method_confidence
        if probability_key in query_result.obsm:
            probabilities = query_result.obsm[probability_key]
            columns = probabilities.columns if isinstance(probabilities, pd.DataFrame) else None
            values = probabilities.to_numpy() if isinstance(probabilities, pd.DataFrame) else np.asarray(probabilities)
            complete = np.full((query.n_obs, values.shape[1]), np.nan, dtype=float)
            positions = query.obs_names.get_indexer(mapped_names)
            complete[positions, :] = values
            query.obsm[probability_key] = pd.DataFrame(complete, index=query.obs_names, columns=columns)
    query.uns["popv_mapping"] = {"reference_sha256": sha256(reference_path), "reference_label_key": args.reference_label_key, "methods": methods, "minimum_consensus": args.minimum_consensus, "feature_overlap": int(overlap.size), "seed": args.seed}
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    query.write_h5ad(output, compression="gzip")
    reloaded = anndata.read_h5ad(output)
    restored = reloaded.layers[args.query_count_layer]
    left = restored.toarray() if sparse.issparse(restored) else np.asarray(restored)
    right = query_counts.toarray() if sparse.issparse(query_counts) else np.asarray(query_counts)
    if reloaded.shape != query.shape or not np.array_equal(reloaded.obs_names, query.obs_names) or not np.array_equal(left, right) or "popv_label_review" not in reloaded.obs:
        raise RuntimeError("popV output did not reload with source counts and query identities")
    report = {"query_sha256": sha256(query_path), "reference_sha256": sha256(reference_path), "query_cells": int(query.n_obs), "reference_cells": int(reference.n_obs), "mapped_query_cells": int(len(mapped_names)), "not_mapped_query_cells": int(len(omitted_names)), "feature_overlap": int(overlap.size), "methods": methods, "prediction_keys": prediction_keys, "minimum_consensus": args.minimum_consensus, "unknown_cells": int((reviewed == "Unknown").sum()), "consensus_distribution": {str(k): int(v) for k, v in scores.value_counts().sort_index().items()}, "review_label_counts": {str(k): int(v) for k, v in reviewed.value_counts().items()}, "raw_counts_preserved": True, "output_reloaded": True, "versions": {"python": platform.python_version(), "popv": importlib.metadata.version("popv"), "anndata": importlib.metadata.version("anndata")}, "quality_status": "review-required"}
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
