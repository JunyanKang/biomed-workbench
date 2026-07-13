#!/usr/bin/env python3
"""Project template for a traceable Scanpy single-cell foundation workflow.

Codex must inspect and adapt this template to the project before execution.
It intentionally does not install dependencies or infer missing scientific metadata.
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
from scipy import sparse
from sklearn.metrics import adjusted_rand_score


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--input-format", required=True, choices=("h5ad", "10x-hdf5", "matrix-market"))
    parser.add_argument("--output-h5ad", required=True)
    parser.add_argument("--qc-report", required=True)
    parser.add_argument("--cluster-report", required=True)
    parser.add_argument("--sample-key", required=True)
    parser.add_argument("--batch-key", default="none")
    parser.add_argument("--raw-count-location", required=True)
    parser.add_argument("--mitochondrial-prefixes", default="MT-,mt-")
    parser.add_argument("--min-counts", type=int, required=True)
    parser.add_argument("--max-counts", type=int, default=0)
    parser.add_argument("--min-genes", type=int, required=True)
    parser.add_argument("--max-genes", type=int, default=0)
    parser.add_argument("--max-mito-percent", type=float, required=True)
    parser.add_argument("--min-cells-per-gene", type=int, required=True)
    parser.add_argument("--target-sum", type=float, default=10000.0)
    parser.add_argument("--n-top-genes", type=int, required=True)
    parser.add_argument("--n-pcs", type=int, required=True)
    parser.add_argument("--n-neighbors", type=int, required=True)
    parser.add_argument("--cluster-method", choices=("leiden", "louvain"), required=True)
    parser.add_argument("--resolutions", required=True)
    parser.add_argument("--seed", type=int, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_input(path: Path, input_format: str) -> anndata.AnnData:
    if input_format == "h5ad":
        return sc.read_h5ad(path)
    if input_format == "10x-hdf5":
        return sc.read_10x_h5(path, gex_only=False)
    if not path.is_dir():
        raise ValueError("matrix-market input must be a 10x-style directory containing matrix, features, and barcodes")
    return sc.read_10x_mtx(path, var_names="gene_ids", make_unique=False, gex_only=False)


def matrix_values(matrix):
    return matrix.data if sparse.issparse(matrix) else np.asarray(matrix).reshape(-1)


def validate_counts(matrix) -> None:
    values = matrix_values(matrix)
    if values.size == 0 or not np.isfinite(values).all() or float(values.min(initial=0)) < 0:
        raise ValueError("raw counts must contain finite nonnegative observations")
    if not np.allclose(values, np.rint(values), rtol=0, atol=1e-8):
        raise ValueError("raw count location is not integer-like")


def raw_counts(adata: anndata.AnnData, location: str):
    if location == "X":
        return adata.X.copy()
    prefix = "layers."
    if location.startswith(prefix) and location[len(prefix):] in adata.layers:
        return adata.layers[location[len(prefix):]].copy()
    raise ValueError("raw-count-location must be X or an existing layers.NAME entry")


def versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "scanpy": sc.__version__,
        "anndata": anndata.__version__,
        "numpy": np.__version__,
        "pandas": pd.__version__,
    }


def main() -> int:
    args = parse_args()
    source = Path(args.input).resolve(strict=True)
    outputs = [Path(args.output_h5ad), Path(args.qc_report), Path(args.cluster_report)]
    for output in outputs:
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise FileExistsError(f"refusing to overwrite output: {output.name}")
    if args.min_counts < 0 or args.min_genes < 0 or args.min_cells_per_gene < 1:
        raise ValueError("count and feature thresholds are invalid")
    if args.max_counts and args.max_counts <= args.min_counts:
        raise ValueError("max-counts must exceed min-counts")
    if args.max_genes and args.max_genes <= args.min_genes:
        raise ValueError("max-genes must exceed min-genes")
    if not 0 <= args.max_mito_percent <= 100 or args.target_sum <= 0:
        raise ValueError("mitochondrial and normalization thresholds are invalid")

    adata = read_input(source, args.input_format)
    if adata.n_obs < 3 or adata.n_vars < 3:
        raise ValueError("single-cell workflow requires at least three observations and three features")
    if not adata.obs_names.is_unique or not adata.var_names.is_unique:
        raise ValueError("cell and feature identifiers must be unique before analysis")
    if any(not str(value).strip() for value in adata.obs_names) or any(not str(value).strip() for value in adata.var_names):
        raise ValueError("cell and feature identifiers must be nonempty")
    if args.sample_key not in adata.obs or adata.obs[args.sample_key].isna().any():
        raise ValueError("biological sample key is absent or incomplete")
    if args.batch_key != "none" and (args.batch_key not in adata.obs or adata.obs[args.batch_key].isna().any()):
        raise ValueError("batch key is absent or incomplete")

    counts = raw_counts(adata, args.raw_count_location)
    validate_counts(counts)
    adata.layers["counts"] = counts
    prefixes = tuple(value for value in args.mitochondrial_prefixes.split(",") if value)
    if not prefixes:
        raise ValueError("at least one mitochondrial prefix is required")
    adata.var["mt"] = [any(str(gene).startswith(prefix) for prefix in prefixes) for gene in adata.var_names]
    sc.pp.calculate_qc_metrics(adata, qc_vars=["mt"], percent_top=None, log1p=False, inplace=True, layer="counts")

    reasons = [[] for _ in range(adata.n_obs)]
    metrics = adata.obs
    rules = (
        (metrics["total_counts"].to_numpy() < args.min_counts, "low-counts"),
        (metrics["n_genes_by_counts"].to_numpy() < args.min_genes, "low-features"),
        (metrics["pct_counts_mt"].fillna(0).to_numpy() > args.max_mito_percent, "high-mitochondrial-fraction"),
    )
    optional_rules = []
    if args.max_counts:
        optional_rules.append((metrics["total_counts"].to_numpy() > args.max_counts, "high-counts"))
    if args.max_genes:
        optional_rules.append((metrics["n_genes_by_counts"].to_numpy() > args.max_genes, "high-features"))
    for mask, label in (*rules, *optional_rules):
        for index in np.flatnonzero(mask):
            reasons[int(index)].append(label)
    retained = np.array([not value for value in reasons], dtype=bool)
    if retained.sum() < max(3, args.n_neighbors + 1):
        raise ValueError("QC retains too few cells for the requested neighbor graph")
    accounting = pd.DataFrame({
        "cell_id": adata.obs_names.astype(str),
        "sample": adata.obs[args.sample_key].astype(str).to_numpy(),
        "retained": retained,
        "exclusion_reasons": [";".join(value) for value in reasons],
    })
    adata = adata[retained].copy()
    sc.pp.filter_genes(adata, min_cells=args.min_cells_per_gene)
    if adata.n_vars < max(3, args.n_pcs + 1):
        raise ValueError("feature filtering leaves too few genes for the requested PCA")
    validate_counts(adata.layers["counts"])

    adata.X = adata.layers["counts"].copy()
    sc.pp.normalize_total(adata, target_sum=args.target_sum)
    sc.pp.log1p(adata)
    batch_key = None if args.batch_key == "none" else args.batch_key
    sc.pp.highly_variable_genes(
        adata,
        n_top_genes=min(args.n_top_genes, adata.n_vars),
        flavor="seurat",
        batch_key=batch_key,
        inplace=True,
    )
    if int(adata.var["highly_variable"].sum()) < max(3, args.n_pcs + 1):
        raise ValueError("too few highly variable genes for the requested PCA")
    model = adata[:, adata.var["highly_variable"]].copy()
    sc.pp.scale(model, zero_center=True, max_value=10)
    n_pcs = min(args.n_pcs, model.n_obs - 1, model.n_vars - 1)
    if n_pcs < 2:
        raise ValueError("PCA requires at least two usable components")
    sc.tl.pca(model, n_comps=n_pcs, svd_solver="arpack", random_state=args.seed)
    adata.obsm["X_pca"] = model.obsm["X_pca"].copy()
    adata.uns["pca"] = dict(model.uns["pca"])
    sc.pp.neighbors(adata, n_neighbors=min(args.n_neighbors, adata.n_obs - 1), n_pcs=n_pcs, use_rep="X_pca", random_state=args.seed)
    sc.tl.umap(adata, random_state=args.seed)

    resolution_values = sorted({float(value) for value in args.resolutions.split(",")})
    if not resolution_values or any(not math.isfinite(value) or value <= 0 for value in resolution_values):
        raise ValueError("resolutions must be comma-separated positive finite numbers")
    cluster_keys = []
    for resolution in resolution_values:
        key = f"{args.cluster_method}_{resolution:g}"
        if args.cluster_method == "leiden":
            sc.tl.leiden(adata, resolution=resolution, key_added=key, random_state=args.seed)
        else:
            sc.tl.louvain(adata, resolution=resolution, key_added=key, random_state=args.seed)
        cluster_keys.append(key)

    adjacent_ari = []
    for left, right in zip(cluster_keys, cluster_keys[1:]):
        adjacent_ari.append({"left": left, "right": right, "adjusted_rand_index": float(adjusted_rand_score(adata.obs[left], adata.obs[right]))})
    cluster_summaries = []
    for key in cluster_keys:
        sizes = adata.obs[key].value_counts().sort_index()
        composition = pd.crosstab(adata.obs[key], adata.obs[args.sample_key])
        cluster_summaries.append({
            "key": key,
            "cluster_count": int(sizes.size),
            "cluster_sizes": {str(index): int(value) for index, value in sizes.items()},
            "sample_composition": {
                str(cluster): {str(sample): int(value) for sample, value in row.items()}
                for cluster, row in composition.iterrows()
            },
        })

    adata.uns["biomed_workbench"] = {
        "template": "scanpy_foundation.py",
        "versions": versions(),
        "parameters": vars(args),
        "input_sha256": sha256(source) if source.is_file() else None,
        "raw_count_location": "layers.counts",
        "cluster_keys": cluster_keys,
    }
    adata.write_h5ad(outputs[0], compression="gzip")
    reloaded = sc.read_h5ad(outputs[0])
    if reloaded.shape != adata.shape or "counts" not in reloaded.layers or any(key not in reloaded.obs for key in cluster_keys):
        raise RuntimeError("reloaded h5ad failed structural validation")
    validate_counts(reloaded.layers["counts"])

    sample_accounting = []
    for sample, frame in accounting.groupby("sample", sort=True):
        sample_accounting.append({"sample": sample, "input_cells": int(len(frame)), "retained_cells": int(frame["retained"].sum()), "excluded_cells": int((~frame["retained"]).sum())})
    qc_report = {
        "input_cells": int(len(accounting)),
        "retained_cells": int(retained.sum()),
        "excluded_cells": int((~retained).sum()),
        "input_features": int(counts.shape[1]),
        "retained_features": int(adata.n_vars),
        "sample_accounting": sample_accounting,
        "exclusion_reason_counts": accounting.loc[~accounting["retained"], "exclusion_reasons"].value_counts().sort_index().to_dict(),
        "methods": {"empty_droplet": "not-run", "ambient_rna": "not-run", "doublet": "not-run"},
        "thresholds": {key: value for key, value in vars(args).items() if key in {"min_counts", "max_counts", "min_genes", "max_genes", "max_mito_percent", "min_cells_per_gene"}},
        "versions": versions(),
        "output_h5ad_sha256": sha256(outputs[0]),
    }
    cluster_report = {
        "cluster_method": args.cluster_method,
        "cluster_keys": cluster_keys,
        "adjacent_resolution_ari": adjacent_ari,
        "clusters": cluster_summaries,
        "n_pcs": n_pcs,
        "n_neighbors": min(args.n_neighbors, adata.n_obs - 1),
        "random_seed": args.seed,
        "interpretation_ready": all(min(item["cluster_sizes"].values()) >= 2 for item in cluster_summaries),
    }
    outputs[1].write_text(json.dumps(qc_report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    outputs[2].write_text(json.dumps(cluster_report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
