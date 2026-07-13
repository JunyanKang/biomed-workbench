#!/usr/bin/env python3
"""Fit and validate scVelo dynamics with independent temporal direction checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path

import anndata
import numpy as np
import pandas as pd
import scanpy as sc
import scipy
from scipy import sparse
from scipy.stats import spearmanr
import scvelo as scv
import sklearn


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-h5ad", required=True)
    parser.add_argument("--output-h5ad", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--spliced-layer", required=True)
    parser.add_argument("--unspliced-layer", required=True)
    parser.add_argument("--sample-key", required=True)
    parser.add_argument("--experimental-time-key", required=True)
    parser.add_argument("--root-score-key", required=True)
    parser.add_argument("--terminal-score-key", required=True)
    parser.add_argument("--n-top-genes", type=int, required=True)
    parser.add_argument("--n-pcs", type=int, required=True)
    parser.add_argument("--n-neighbors", type=int, required=True)
    parser.add_argument("--max-dynamics-iterations", type=int, required=True)
    parser.add_argument("--minimum-modeled-genes", type=int, required=True)
    parser.add_argument("--minimum-latent-time-correlation", type=float, required=True)
    parser.add_argument("--minimum-velocity-pseudotime-correlation", type=float, required=True)
    parser.add_argument("--minimum-root-terminal-separation", type=float, required=True)
    parser.add_argument("--minimum-median-velocity-confidence", type=float, required=True)
    parser.add_argument("--seed", type=int, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_layer(adata: anndata.AnnData, key: str) -> sparse.csr_matrix:
    if key not in adata.layers:
        raise ValueError(f"required layer is missing: {key}")
    matrix = sparse.csr_matrix(adata.layers[key])
    values = matrix.data
    if values.size and (not np.isfinite(values).all() or float(values.min()) < 0):
        raise ValueError(f"layer contains negative or nonfinite values: {key}")
    if values.size and not np.allclose(values, np.rint(values), rtol=0, atol=1e-8):
        raise ValueError(f"layer is not integer-like: {key}")
    return matrix.astype(np.int64)


def obs_text(adata: anndata.AnnData, key: str) -> np.ndarray:
    if key not in adata.obs or adata.obs[key].isna().any():
        raise ValueError(f"required observation field is missing or incomplete: {key}")
    values = adata.obs[key].astype(str).str.strip().to_numpy()
    if np.any(values == ""):
        raise ValueError(f"observation field contains empty values: {key}")
    return values


def obs_numeric(adata: anndata.AnnData, key: str) -> np.ndarray:
    if key not in adata.obs:
        raise ValueError(f"required numeric observation field is missing: {key}")
    values = pd.to_numeric(adata.obs[key], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"numeric observation field contains nonfinite values: {key}")
    return values


def copy_mapping(source, target, keys: list[str]) -> None:
    for key in keys:
        if key in source:
            target[key] = source[key].copy() if hasattr(source[key], "copy") else source[key]


def main() -> int:
    args = parse_args()
    source_path = Path(args.input_h5ad).resolve(strict=True)
    output_path = Path(args.output_h5ad)
    report_path = Path(args.report)
    for path in (output_path, report_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite output: {path.name}")
        path.parent.mkdir(parents=True, exist_ok=True)
    if args.n_top_genes < args.minimum_modeled_genes or args.n_pcs < 2 or args.n_neighbors < 3:
        raise ValueError("feature, component, or neighborhood parameters are inconsistent")
    if args.max_dynamics_iterations < 5:
        raise ValueError("dynamics iteration limit is too small")

    source = sc.read_h5ad(source_path)
    if source.n_obs <= args.n_neighbors + 1 or source.n_vars < args.n_top_genes:
        raise ValueError("input is too small for the declared trajectory model")
    if not source.obs_names.is_unique or not source.var_names.is_unique:
        raise ValueError("cell and feature identifiers must be unique")
    samples = obs_text(source, args.sample_key)
    if len(set(samples.tolist())) < 2:
        raise ValueError("trajectory validation requires multiple biological samples")
    experimental_time = obs_numeric(source, args.experimental_time_key)
    root_scores = obs_numeric(source, args.root_score_key)
    terminal_scores = obs_numeric(source, args.terminal_score_key)
    if len(np.unique(experimental_time)) < 3 or np.max(root_scores) <= 0 or np.max(terminal_scores) <= 0:
        raise ValueError("experimental time, root, or terminal anchors are not informative")
    if np.any((root_scores > 0) & (terminal_scores > 0)):
        raise ValueError("root and terminal anchors overlap")
    spliced = count_layer(source, args.spliced_layer)
    unspliced = count_layer(source, args.unspliced_layer)
    if spliced.shape != unspliced.shape or spliced.nnz == 0 or unspliced.nnz == 0:
        raise ValueError("spliced and unspliced layers are empty or misaligned")

    work = anndata.AnnData(X=spliced.copy(), obs=source.obs.copy(), var=source.var.copy())
    work.layers["spliced"] = spliced.copy()
    work.layers["unspliced"] = unspliced.copy()
    scv.settings.seed = args.seed
    scv.settings.verbosity = 1
    scv.pp.filter_and_normalize(work, layers_normalize=["spliced", "unspliced"])
    sc.pp.log1p(work)
    sc.pp.highly_variable_genes(work, n_top_genes=args.n_top_genes, flavor="seurat")
    selected_genes = int(work.var["highly_variable"].sum())
    component_count = min(args.n_pcs, selected_genes - 1, work.n_obs - 1)
    if selected_genes < args.minimum_modeled_genes or component_count < 2:
        raise ValueError("insufficient highly variable genes for velocity modeling")
    sc.pp.pca(work, n_comps=component_count, use_highly_variable=True, random_state=args.seed)
    sc.pp.neighbors(work, n_neighbors=args.n_neighbors, n_pcs=component_count, random_state=args.seed)
    scv.pp.moments(work, n_neighbors=None, n_pcs=None)
    sc.tl.umap(work, random_state=args.seed)
    scv.tl.recover_dynamics(work, max_iter=args.max_dynamics_iterations, n_jobs=1, show_progress_bar=False)
    scv.tl.velocity(work, mode="dynamical")
    scv.tl.velocity_graph(work, n_jobs=1, show_progress_bar=False)
    scv.tl.velocity_pseudotime(work, root_key=args.root_score_key, end_key=args.terminal_score_key)
    scv.tl.latent_time(work, root_key=args.root_score_key, end_key=args.terminal_score_key)
    scv.tl.velocity_confidence(work)
    scv.tl.velocity_embedding(work, basis="umap", autoscale=False)

    velocity_pseudotime = work.obs["velocity_pseudotime"].to_numpy(dtype=float)
    latent_time = work.obs["latent_time"].to_numpy(dtype=float)
    confidence = work.obs["velocity_confidence"].to_numpy(dtype=float)
    latent_rho = float(spearmanr(latent_time, experimental_time).statistic)
    pseudotime_rho = float(spearmanr(velocity_pseudotime, experimental_time).statistic)
    root_mask = root_scores > 0
    terminal_mask = terminal_scores > 0
    root_mean = float(np.mean(latent_time[root_mask]))
    terminal_mean = float(np.mean(latent_time[terminal_mask]))
    root_terminal_separation = terminal_mean - root_mean
    median_confidence = float(np.median(confidence))
    modeled_genes = int(np.sum(work.var.get("velocity_genes", pd.Series(False, index=work.var_names)).fillna(False).to_numpy(dtype=bool)))
    fit_likelihood = pd.to_numeric(work.var.get("fit_likelihood", pd.Series(np.nan, index=work.var_names)), errors="coerce").to_numpy(dtype=float)
    finite_fit_genes = int(np.isfinite(fit_likelihood).sum())

    gates = {
        "modeled_gene_count": modeled_genes >= args.minimum_modeled_genes,
        "finite_dynamics_fits": finite_fit_genes >= args.minimum_modeled_genes,
        "latent_time_direction": latent_rho >= args.minimum_latent_time_correlation,
        "velocity_pseudotime_direction": pseudotime_rho >= args.minimum_velocity_pseudotime_correlation,
        "root_before_terminal": root_terminal_separation >= args.minimum_root_terminal_separation,
        "velocity_confidence": median_confidence >= args.minimum_median_velocity_confidence,
        "spliced_counts_preserved": True,
        "unspliced_counts_preserved": True,
    }
    quality_status = "passed" if all(gates.values()) else "blocked"

    output = source.copy()
    for key in ("velocity_pseudotime", "latent_time", "velocity_length", "velocity_confidence", "velocity_confidence_transition", "velocity_self_transition"):
        if key in work.obs:
            output.obs[key] = work.obs[key].to_numpy()
    copy_mapping(work.obsm, output.obsm, ["X_pca", "X_umap", "velocity_umap"])
    copy_mapping(work.obsp, output.obsp, ["distances", "connectivities"])
    copy_mapping(work.uns, output.uns, ["neighbors", "umap", "velocity_params", "velocity_graph", "velocity_graph_neg", "recover_dynamics"])
    for key in ("velocity", "velocity_u"):
        if key in work.layers:
            output.layers[key] = work.layers[key].copy()
    for key in work.var.columns:
        if key.startswith("fit_") or key == "velocity_genes":
            output.var[key] = work.var[key].to_numpy()
    output.uns["biomed_trajectory_velocity"] = {
        "engine": "scVelo", "mode": "dynamical", "experimental_time_used_for_fitting": False,
        "root_score_key": args.root_score_key, "terminal_score_key": args.terminal_score_key,
        "quality_status": quality_status,
    }
    spliced_preserved = (sparse.csr_matrix(output.layers[args.spliced_layer]) != spliced).nnz == 0
    unspliced_preserved = (sparse.csr_matrix(output.layers[args.unspliced_layer]) != unspliced).nnz == 0
    gates["spliced_counts_preserved"] = bool(spliced_preserved)
    gates["unspliced_counts_preserved"] = bool(unspliced_preserved)
    quality_status = "passed" if all(gates.values()) else "blocked"
    output.uns["biomed_trajectory_velocity"]["quality_status"] = quality_status
    output.write_h5ad(output_path)
    reloaded = sc.read_h5ad(output_path)
    reload_valid = (
        reloaded.shape == source.shape
        and np.array_equal(reloaded.obs_names.to_numpy(), source.obs_names.to_numpy())
        and np.array_equal(reloaded.var_names.to_numpy(), source.var_names.to_numpy())
        and all(key in reloaded.obs for key in ("velocity_pseudotime", "latent_time", "velocity_confidence"))
        and all(key in reloaded.obsm for key in ("X_umap", "velocity_umap"))
        and "velocity_graph" in reloaded.uns
        and (sparse.csr_matrix(reloaded.layers[args.spliced_layer]) != spliced).nnz == 0
        and (sparse.csr_matrix(reloaded.layers[args.unspliced_layer]) != unspliced).nnz == 0
        and reloaded.uns["biomed_trajectory_velocity"]["quality_status"] == quality_status
    )
    if not reload_valid:
        raise RuntimeError("velocity h5ad failed identity, count, graph, or trajectory reload validation")

    report = {
        "schema_version": 1, "quality_status": quality_status,
        "input": {"filename": source_path.name, "sha256": sha256(source_path), "cells": source.n_obs, "genes": source.n_vars, "samples": len(set(samples.tolist())), "spliced_layer": args.spliced_layer, "unspliced_layer": args.unspliced_layer},
        "model": {"mode": "dynamical", "selected_hvgs": selected_genes, "modeled_genes": modeled_genes, "finite_fit_genes": finite_fit_genes, "n_pcs": component_count, "n_neighbors": args.n_neighbors, "max_dynamics_iterations": args.max_dynamics_iterations, "seed": args.seed},
        "direction_validation": {
            "experimental_time_key": args.experimental_time_key, "experimental_time_used_for_fitting": False,
            "latent_time_spearman": latent_rho, "velocity_pseudotime_spearman": pseudotime_rho,
            "root_cells": int(root_mask.sum()), "terminal_cells": int(terminal_mask.sum()),
            "root_mean_latent_time": root_mean, "terminal_mean_latent_time": terminal_mean,
            "root_terminal_separation": root_terminal_separation,
        },
        "confidence": {"median_velocity_confidence": median_confidence, "minimum": float(np.min(confidence)), "maximum": float(np.max(confidence))},
        "quality_thresholds": {
            "minimum_modeled_genes": args.minimum_modeled_genes,
            "minimum_latent_time_correlation": args.minimum_latent_time_correlation,
            "minimum_velocity_pseudotime_correlation": args.minimum_velocity_pseudotime_correlation,
            "minimum_root_terminal_separation": args.minimum_root_terminal_separation,
            "minimum_median_velocity_confidence": args.minimum_median_velocity_confidence,
        },
        "quality_gates": {**gates, "output_reload_valid": True},
        "output": {"filename": output_path.name, "sha256": sha256(output_path)},
        "versions": {"python": platform.python_version(), "scvelo": scv.__version__, "scanpy": sc.__version__, "anndata": anndata.__version__, "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__, "scikit-learn": sklearn.__version__, "numba": version("numba"), "umap-learn": version("umap-learn")},
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"quality_status": quality_status, "modeled_genes": modeled_genes, "latent_time_spearman": latent_rho, "velocity_pseudotime_spearman": pseudotime_rho}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
