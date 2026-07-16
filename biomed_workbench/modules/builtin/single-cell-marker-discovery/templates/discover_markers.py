#!/usr/bin/env python3
"""Discover cluster markers with count validation and biological-sample stability checks."""

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
import scanpy as sc
from scipy import sparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-h5ad", required=True)
    parser.add_argument("--output-tsv", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--cluster-key", required=True)
    parser.add_argument("--sample-key", required=True)
    parser.add_argument("--raw-count-location", required=True)
    parser.add_argument("--method", choices=("wilcoxon", "t-test", "logreg"), default="wilcoxon")
    parser.add_argument("--top-per-cluster", type=int, default=100)
    parser.add_argument("--min-in-fraction", type=float, default=0.25)
    parser.add_argument("--max-out-fraction", type=float, default=0.5)
    parser.add_argument("--min-logfc", type=float, default=0.25)
    parser.add_argument("--max-adjusted-p", type=float, default=0.05)
    parser.add_argument("--min-sample-support", type=int, default=2)
    parser.add_argument("--seed", type=int, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raw_counts(adata: anndata.AnnData, location: str):
    if location == "X":
        matrix = adata.X
    elif location.startswith("layers.") and location[7:] in adata.layers:
        matrix = adata.layers[location[7:]]
    else:
        raise ValueError("raw-count-location must be X or an existing layers.NAME")
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix).reshape(-1)
    if values.size == 0 or not np.isfinite(values).all() or np.any(values < 0) or not np.allclose(values, np.rint(values), rtol=0, atol=1e-8):
        raise ValueError("marker discovery requires finite nonnegative integer-like counts")
    return matrix.copy()


def expression_fraction(matrix, rows: np.ndarray) -> np.ndarray:
    selected = matrix[rows, :]
    return np.asarray((selected > 0).mean(axis=0)).reshape(-1)


def sample_support(matrix, clusters: np.ndarray, samples: np.ndarray, cluster: str, gene_index: int) -> tuple[int, int, str]:
    directions: list[int] = []
    for sample in sorted(pd.unique(samples)):
        sample_rows = samples == sample
        inside = sample_rows & (clusters == cluster)
        outside = sample_rows & (clusters != cluster)
        if inside.sum() < 3 or outside.sum() < 3:
            continue
        inside_fraction = float(np.asarray((matrix[inside, gene_index] > 0).mean()).reshape(-1)[0])
        outside_fraction = float(np.asarray((matrix[outside, gene_index] > 0).mean()).reshape(-1)[0])
        directions.append(1 if inside_fraction > outside_fraction else (-1 if inside_fraction < outside_fraction else 0))
    positive = sum(value > 0 for value in directions)
    negative = sum(value < 0 for value in directions)
    status = "stable-positive" if positive > negative and positive >= 2 else ("discordant" if positive and negative else "insufficient-support")
    return positive, len(directions), status


def main() -> int:
    args = parse_args()
    source = Path(args.input_h5ad).resolve(strict=True)
    output, report_path = Path(args.output_tsv), Path(args.report)
    if output.exists() or report_path.exists():
        raise FileExistsError("refusing to overwrite declared outputs")
    if args.top_per_cluster < 5 or args.min_sample_support < 1:
        raise ValueError("top-per-cluster and sample-support thresholds are invalid")
    if not 0 <= args.min_in_fraction <= 1 or not 0 <= args.max_out_fraction <= 1 or not 0 < args.max_adjusted_p <= 1:
        raise ValueError("fraction or adjusted-p thresholds are invalid")
    adata = anndata.read_h5ad(source)
    for key in (args.cluster_key, args.sample_key):
        if key not in adata.obs or adata.obs[key].isna().any():
            raise ValueError(f"required observation field is absent or incomplete: {key}")
    if not adata.obs_names.is_unique or not adata.var_names.is_unique:
        raise ValueError("cell and feature identifiers must be unique")
    counts = raw_counts(adata, args.raw_count_location)
    clusters = adata.obs[args.cluster_key].astype(str).to_numpy()
    samples = adata.obs[args.sample_key].astype(str).to_numpy()
    cluster_sizes = pd.Series(clusters).value_counts().sort_index()
    if cluster_sizes.size < 2 or int(cluster_sizes.min()) < 10 or pd.unique(samples).size < 2:
        raise ValueError("marker discovery requires at least two clusters, ten cells per cluster, and two biological samples")

    work = anndata.AnnData(X=counts.copy(), obs=adata.obs[[args.cluster_key, args.sample_key]].copy(), var=adata.var.copy())
    work.obs[args.cluster_key] = pd.Categorical(clusters)
    sc.pp.normalize_total(work, target_sum=10_000)
    sc.pp.log1p(work)
    np.random.seed(args.seed)
    sc.tl.rank_genes_groups(work, groupby=args.cluster_key, method=args.method, n_genes=min(args.top_per_cluster, work.n_vars), use_raw=False, pts=False)
    marker_rows: list[dict[str, object]] = []
    for cluster in work.obs[args.cluster_key].cat.categories:
        ranked = sc.get.rank_genes_groups_df(work, group=str(cluster))
        inside = clusters == str(cluster)
        outside = ~inside
        inside_fraction = expression_fraction(counts, inside)
        outside_fraction = expression_fraction(counts, outside)
        for rank, row in ranked.iterrows():
            gene = str(row["names"])
            gene_index = int(adata.var_names.get_loc(gene))
            support, evaluable, stability = sample_support(counts, clusters, samples, str(cluster), gene_index)
            logfc = float(row.get("logfoldchanges", np.nan))
            adjusted = float(row.get("pvals_adj", np.nan))
            passes = bool(
                np.isfinite(logfc) and np.isfinite(adjusted)
                and logfc >= args.min_logfc and adjusted <= args.max_adjusted_p
                and inside_fraction[gene_index] >= args.min_in_fraction
                and outside_fraction[gene_index] <= args.max_out_fraction
                and support >= args.min_sample_support
            )
            marker_rows.append({
                "cluster": str(cluster), "rank": int(rank + 1), "gene": gene,
                "score": float(row["scores"]), "log2_fold_change": logfc,
                "p_value": float(row.get("pvals", np.nan)), "adjusted_p_value": adjusted,
                "fraction_in": float(inside_fraction[gene_index]), "fraction_out": float(outside_fraction[gene_index]),
                "supporting_samples": int(support), "evaluable_samples": int(evaluable),
                "sample_stability": stability, "admitted_marker": passes,
            })
    markers = pd.DataFrame(marker_rows)
    if markers.empty or set(markers["cluster"]) != set(cluster_sizes.index):
        raise RuntimeError("ranked marker output does not cover every cluster")
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    markers.to_csv(output, sep="\t", index=False)
    reloaded = pd.read_csv(output, sep="\t")
    if reloaded.shape != markers.shape or reloaded["gene"].isna().any() or not set(cluster_sizes.index) <= set(reloaded["cluster"].astype(str)):
        raise RuntimeError("serialized marker table failed reload validation")
    report = {
        "input_sha256": sha256(source), "cells": int(adata.n_obs), "features": int(adata.n_vars),
        "clusters": {str(key): int(value) for key, value in cluster_sizes.items()},
        "biological_samples": int(pd.unique(samples).size), "tested_rows": int(markers.shape[0]),
        "admitted_rows": int(markers["admitted_marker"].sum()),
        "clusters_with_admitted_markers": int(markers.loc[markers["admitted_marker"], "cluster"].nunique()),
        "parameters": {"method": args.method, "top_per_cluster": args.top_per_cluster, "min_in_fraction": args.min_in_fraction, "max_out_fraction": args.max_out_fraction, "min_logfc": args.min_logfc, "max_adjusted_p": args.max_adjusted_p, "min_sample_support": args.min_sample_support, "seed": args.seed},
        "raw_counts_preserved": True, "output_reloaded": True,
        "versions": {"python": platform.python_version(), "scanpy": importlib.metadata.version("scanpy"), "anndata": importlib.metadata.version("anndata")},
        "quality_status": "review-required",
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
