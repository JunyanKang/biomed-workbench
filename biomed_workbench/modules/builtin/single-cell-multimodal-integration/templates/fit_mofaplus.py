#!/usr/bin/env python3
"""Fit a reproducible MOFA+ model from declared H5MU modality layers."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path

import h5py
import mudata
import numpy as np
import pandas as pd
from scipy import sparse
from mofapy2.run.entry_point import entry_point


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-h5mu", required=True); parser.add_argument("--view-config", required=True)
    parser.add_argument("--model-output", required=True); parser.add_argument("--factor-table", required=True)
    parser.add_argument("--weight-table", required=True); parser.add_argument("--variance-table", required=True); parser.add_argument("--report", required=True)
    parser.add_argument("--factors", type=int, required=True); parser.add_argument("--iterations", type=int, required=True)
    parser.add_argument("--convergence-mode", choices=("fast", "medium", "slow"), required=True); parser.add_argument("--seed", type=int, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matrix_from_location(adata, location: str):
    if location == "X": matrix = adata.X
    elif location.startswith("layers.") and location[7:] in adata.layers: matrix = adata.layers[location[7:]]
    else: raise ValueError(f"declared model matrix is absent: {location}")
    matrix = sparse.csr_matrix(matrix).toarray() if sparse.issparse(matrix) else np.asarray(matrix)
    matrix = matrix.astype(np.float64, copy=False)
    if matrix.ndim != 2 or not np.isfinite(matrix).all(): raise ValueError("MOFA+ view matrix must be finite and two-dimensional")
    return matrix


def decode(values):
    return [item.decode() if isinstance(item, bytes) else str(item) for item in values]


def main() -> int:
    args = parse_args(); source = Path(args.input_h5mu).resolve(strict=True); config_path = Path(args.view_config).resolve(strict=True)
    outputs = [Path(item) for item in (args.model_output, args.factor_table, args.weight_table, args.variance_table, args.report)]
    if any(path.exists() for path in outputs): raise FileExistsError("refusing to overwrite declared outputs")
    for path in outputs: path.parent.mkdir(parents=True, exist_ok=True)
    if args.factors < 2 or args.iterations < 50: raise ValueError("MOFA+ factors or iterations are too small")
    config = json.loads(config_path.read_text())
    if not isinstance(config, list) or len(config) < 2: raise ValueError("view config requires at least two views")
    names = [item.get("name") for item in config]
    if any(not isinstance(name, str) or not name for name in names) or len(names) != len(set(names)): raise ValueError("view names must be unique nonempty strings")
    mdata = mudata.read_h5mu(source)
    if not all(name in mdata.mod for name in names): raise ValueError("configured modalities are absent from H5MU")
    cells = list(mdata.mod[names[0]].obs_names)
    matrices, features, feature_counts = [], [], {}
    for item in config:
        adata = mdata.mod[item["name"]]
        if list(adata.obs_names) != cells: raise ValueError("all MOFA+ views must contain identical cells in identical order")
        matrix = matrix_from_location(adata, item["location"])
        variance = np.var(matrix, axis=0)
        keep = np.isfinite(variance) & (variance > 1e-12)
        if int(keep.sum()) < 15: raise ValueError(f"view has fewer than 15 nonconstant features: {item['name']}")
        requested = int(item.get("top_variable_features", int(keep.sum())))
        selected = np.flatnonzero(keep)[np.argsort(variance[keep])[-min(requested, int(keep.sum())):]]
        matrices.append([matrix[:, selected]])
        selected_names = [str(adata.var_names[index]) for index in selected]
        features.append(selected_names); feature_counts[item["name"]] = len(selected_names)
    if len(cells) < 15 or args.factors >= len(cells): raise ValueError("too few cells or too many factors")

    model = entry_point(); model.set_data_options(scale_views=True, scale_groups=False, center_groups=True, use_float32=False)
    model.set_data_matrix(matrices, likelihoods=["gaussian"] * len(names), views_names=names, groups_names=["all_cells"], samples_names=[cells], features_names=features)
    model.set_model_options(factors=args.factors, spikeslab_factors=False, spikeslab_weights=True, ard_factors=False, ard_weights=True)
    model.set_train_options(iter=args.iterations, convergence_mode=args.convergence_mode, startELBO=1, freqELBO=1, dropR2=None, nostop=False, verbose=False, quiet=True, seed=args.seed, gpu_mode=False)
    model.build(); model.run(); model.save(outfile=str(outputs[0]), save_data=True, save_parameters=False)

    with h5py.File(outputs[0], "r") as handle:
        factor_matrix = np.asarray(handle["expectations/Z/all_cells"])
        if factor_matrix.shape[1] == len(cells): factor_matrix = factor_matrix.T
        factor_names = [f"Factor{index + 1}" for index in range(factor_matrix.shape[1])]
        factor_table = pd.DataFrame(factor_matrix, index=cells, columns=factor_names).rename_axis("cell_id").reset_index()
        weight_frames = []
        for view in names:
            weights = np.asarray(handle[f"expectations/W/{view}"])
            if weights.shape[1] == len(features[names.index(view)]): weights = weights.T
            frame = pd.DataFrame(weights, index=features[names.index(view)], columns=factor_names).rename_axis("feature_id").reset_index(); frame.insert(0, "view", view); weight_frames.append(frame)
        r2 = np.asarray(handle["variance_explained/r2_per_factor/all_cells"])
        if r2.shape[0] == len(names): variance_table = pd.DataFrame(r2, index=names, columns=factor_names).rename_axis("view").reset_index()
        else: variance_table = pd.DataFrame(r2.T, index=names, columns=factor_names).rename_axis("view").reset_index()
    weights = pd.concat(weight_frames, ignore_index=True)
    factor_table.to_csv(outputs[1], sep="\t", index=False); weights.to_csv(outputs[2], sep="\t", index=False); variance_table.to_csv(outputs[3], sep="\t", index=False)
    reloaded = [pd.read_csv(path, sep="\t") for path in outputs[1:4]]
    if len(reloaded[0]) != len(cells) or set(reloaded[1]["view"]) != set(names) or set(reloaded[2]["view"]) != set(names) or not np.isfinite(reloaded[0].iloc[:, 1:].to_numpy()).all(): raise RuntimeError("MOFA+ outputs failed reload validation")
    report = {"schema_version": 1, "quality_status": "passed", "input": {"filename": source.name, "sha256": sha256(source), "view_config_filename": config_path.name, "view_config_sha256": sha256(config_path), "cells": len(cells), "views": names, "selected_features": feature_counts}, "model": {"factors_requested": args.factors, "factors_retained": factor_matrix.shape[1], "iterations": args.iterations, "convergence_mode": args.convergence_mode, "scale_views": True, "center_groups": True, "gpu_mode": False, "seed": args.seed}, "results": {"factor_variance": {name: float(np.var(factor_matrix[:, index])) for index, name in enumerate(factor_names)}, "variance_explained_rows": len(variance_table), "weight_rows": len(weights)}, "quality_gates": {"cells_aligned_across_views": True, "nonconstant_features_selected": True, "factor_matrix_finite": True, "all_views_have_weights_and_variance": True, "outputs_reloaded": True}, "output": {"model_filename": outputs[0].name, "model_sha256": sha256(outputs[0]), "factor_table_filename": outputs[1].name, "factor_table_sha256": sha256(outputs[1]), "weight_table_filename": outputs[2].name, "weight_table_sha256": sha256(outputs[2]), "variance_table_filename": outputs[3].name, "variance_table_sha256": sha256(outputs[3])}, "versions": {"python": platform.python_version(), "mofapy2": version("mofapy2"), "mudata": version("mudata"), "anndata": version("anndata"), "numpy": version("numpy"), "pandas": version("pandas"), "scipy": version("scipy"), "h5py": version("h5py")}}
    outputs[4].write_text(json.dumps(report, indent=2, sort_keys=True) + "\n"); print(json.dumps({"quality_status": "passed", "factors": factor_matrix.shape[1], "views": names}, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
