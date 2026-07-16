#!/usr/bin/env python3
"""Fit CellRank fate probabilities from pseudotime or real-time optimal transport."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path

import anndata
import cellrank as cr
import moscot
import numpy as np
import pandas as pd
import scanpy as sc
import scipy
from scipy import sparse
from scipy.stats import spearmanr


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-h5ad", required=True)
    parser.add_argument("--output-h5ad", required=True)
    parser.add_argument("--fate-table", required=True)
    parser.add_argument("--driver-table", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--raw-count-location", required=True)
    parser.add_argument("--sample-key", required=True)
    parser.add_argument("--time-key", required=True)
    parser.add_argument("--pseudotime-key", required=True)
    parser.add_argument("--terminal-state-key", required=True)
    parser.add_argument("--terminal-states", required=True)
    parser.add_argument("--mode", choices=("pseudotime", "real-time-optimal-transport"), required=True)
    parser.add_argument("--n-top-genes", type=int, required=True)
    parser.add_argument("--n-pcs", type=int, required=True)
    parser.add_argument("--n-neighbors", type=int, required=True)
    parser.add_argument("--ot-epsilon", type=float, required=True)
    parser.add_argument("--ot-threshold", type=float, required=True)
    parser.add_argument("--minimum-terminal-own-fate", type=float, required=True)
    parser.add_argument("--minimum-time-direction", type=float, required=True)
    parser.add_argument("--seed", type=int, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def comma_list(value: str) -> list[str]:
    values = [item.strip() for item in value.split(",")]
    if len(values) < 2 or any(not item for item in values) or len(values) != len(set(values)):
        raise ValueError("terminal states must contain at least two unique names")
    return values


def count_matrix(adata: anndata.AnnData, location: str) -> sparse.csr_matrix:
    if location == "X":
        matrix = adata.X
    elif location.startswith("layers.") and location[7:] in adata.layers:
        matrix = adata.layers[location[7:]]
    else:
        raise ValueError("declared raw count location is absent")
    matrix = sparse.csr_matrix(matrix)
    if matrix.data.size and (
        not np.isfinite(matrix.data).all() or matrix.data.min() < 0
        or not np.allclose(matrix.data, np.rint(matrix.data), rtol=0, atol=1e-8)
    ):
        raise ValueError("raw counts must be finite, nonnegative, and integer-like")
    return matrix.astype(np.int64)


def obs_text(adata: anndata.AnnData, key: str) -> pd.Series:
    if key not in adata.obs or adata.obs[key].isna().any():
        raise ValueError(f"required observation field is missing or incomplete: {key}")
    values = adata.obs[key].astype(str).str.strip()
    if (values == "").any():
        raise ValueError(f"observation field contains empty values: {key}")
    return values


def obs_numeric(adata: anndata.AnnData, key: str) -> np.ndarray:
    if key not in adata.obs:
        raise ValueError(f"required numeric observation field is missing: {key}")
    values = pd.to_numeric(adata.obs[key], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"observation field contains nonfinite values: {key}")
    return values


def build_kernel(work: anndata.AnnData, args: argparse.Namespace):
    if args.mode == "pseudotime":
        kernel = cr.kernels.PseudotimeKernel(work, time_key=args.pseudotime_key)
        return kernel.compute_transition_matrix(
            threshold_scheme="soft", b=10.0, nu=0.5, n_jobs=1, show_progress_bar=False,
        ), None

    work.obs[args.time_key] = pd.Categorical(
        work.obs[args.time_key], categories=sorted(work.obs[args.time_key].unique()), ordered=True,
    )
    problem = moscot.problems.time.TemporalProblem(work)
    problem = problem.prepare(time_key=args.time_key, joint_attr="X_pca", policy="sequential")
    problem = problem.solve(
        epsilon=args.ot_epsilon, threshold=args.ot_threshold, min_iterations=20,
        max_iterations=500, jit=True, device="cpu",
    )
    kernel = cr.kernels.RealTimeKernel.from_moscot(problem, sparse_mode="min_row")
    kernel = kernel.compute_transition_matrix(
        threshold="auto_local", self_transitions="connectivities",
        conn_kwargs={"n_neighbors": args.n_neighbors, "n_pcs": args.n_pcs},
    )
    return kernel, problem


def main() -> int:
    args = parse_args()
    source_path = Path(args.input_h5ad).resolve(strict=True)
    output_paths = [Path(item) for item in (args.output_h5ad, args.fate_table, args.driver_table, args.report)]
    if any(path.exists() for path in output_paths):
        raise FileExistsError("refusing to overwrite declared outputs")
    for path in output_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
    if args.n_top_genes < 20 or args.n_pcs < 2 or args.n_neighbors < 3:
        raise ValueError("feature, component, or neighborhood parameters are too small")
    if args.ot_epsilon <= 0 or args.ot_threshold <= 0 or not 0 < args.minimum_terminal_own_fate <= 1:
        raise ValueError("optimal-transport or fate thresholds are invalid")

    terminal_states = comma_list(args.terminal_states)
    source = sc.read_h5ad(source_path)
    if not source.obs_names.is_unique or not source.var_names.is_unique:
        raise ValueError("cell and feature identifiers must be unique")
    counts = count_matrix(source, args.raw_count_location)
    samples = obs_text(source, args.sample_key)
    times = obs_numeric(source, args.time_key)
    pseudotime = obs_numeric(source, args.pseudotime_key)
    terminal_labels = obs_text(source, args.terminal_state_key)
    if samples.nunique() < 2 or len(np.unique(times)) < 3:
        raise ValueError("fate mapping requires multiple samples and at least three experimental times")
    missing_states = sorted(set(terminal_states) - set(terminal_labels))
    if missing_states:
        raise ValueError(f"terminal states are absent from the terminal-state field: {missing_states}")
    terminal_cells = {state: source.obs_names[terminal_labels == state].tolist() for state in terminal_states}
    if any(len(cells) < 3 for cells in terminal_cells.values()):
        raise ValueError("each declared terminal state requires at least three cells")

    work = anndata.AnnData(X=counts.copy(), obs=source.obs.copy(), var=source.var.copy())
    work.layers["counts"] = counts.copy()
    sc.pp.normalize_total(work, target_sum=10_000)
    sc.pp.log1p(work)
    work.layers["log1p"] = work.X.copy()
    sc.pp.highly_variable_genes(work, n_top_genes=min(args.n_top_genes, work.n_vars), flavor="seurat")
    selected = int(work.var["highly_variable"].sum())
    components = min(args.n_pcs, selected - 1, work.n_obs - 1)
    if components < 2:
        raise ValueError("too few variable genes for fate mapping")
    sc.pp.pca(work, n_comps=components, mask_var="highly_variable", random_state=args.seed)
    sc.pp.neighbors(work, n_neighbors=args.n_neighbors, n_pcs=components, random_state=args.seed)
    kernel, transport_problem = build_kernel(work, args)
    transition = sparse.csr_matrix(kernel.transition_matrix)
    if transition.shape != (work.n_obs, work.n_obs) or not np.allclose(np.asarray(transition.sum(axis=1)).ravel(), 1.0, atol=1e-6):
        raise RuntimeError("CellRank transition matrix is not cell-aligned and row stochastic")

    estimator = cr.estimators.GPCCA(kernel)
    estimator.set_terminal_states(terminal_cells, n_cells=max(len(value) for value in terminal_cells.values()))
    estimator.compute_fate_probabilities(solver="direct", use_petsc=False, n_jobs=1, show_progress_bar=False)
    fate = np.asarray(estimator.fate_probabilities)
    fate_names = [str(item) for item in estimator.fate_probabilities.names]
    if fate.shape != (work.n_obs, len(terminal_states)) or set(fate_names) != set(terminal_states):
        raise RuntimeError("CellRank fate probabilities do not align to cells and declared terminal states")
    fate = fate[:, [fate_names.index(state) for state in terminal_states]]
    if not np.isfinite(fate).all() or np.min(fate) < -1e-8 or not np.allclose(fate.sum(axis=1), 1.0, atol=1e-3):
        raise RuntimeError("fate probabilities are nonfinite, negative, or do not sum to one")

    driver_result = estimator.compute_lineage_drivers(
        lineages=terminal_states, method="fisher", layer="log1p", use_raw=False, nan_policy="propagate",
    )
    drivers = driver_result.reset_index(names="gene_id")
    drivers.to_csv(output_paths[2], sep="\t", index=False)
    fate_table = pd.DataFrame(fate, index=work.obs_names, columns=[f"fate_{state}" for state in terminal_states])
    fate_table.insert(0, "cell_id", work.obs_names)
    fate_table[args.sample_key] = samples.to_numpy()
    fate_table[args.time_key] = times
    fate_table[args.terminal_state_key] = terminal_labels.to_numpy()
    fate_table.to_csv(output_paths[1], sep="\t", index=False)

    own_fates = {}
    for index, state in enumerate(terminal_states):
        mask = terminal_labels.to_numpy() == state
        own_fates[state] = float(np.mean(fate[mask, index]))
    source_indices = np.repeat(np.arange(work.n_obs), np.diff(transition.indptr))
    target_indices = transition.indices
    weights = transition.data
    time_delta = times[target_indices] - times[source_indices]
    expected_time_delta = float(np.average(time_delta, weights=weights))
    pseudotime_delta = pseudotime[target_indices] - pseudotime[source_indices]
    expected_pseudotime_delta = float(np.average(pseudotime_delta, weights=weights))
    max_fate = fate.max(axis=1)
    fate_time_rho = float(spearmanr(max_fate, times).statistic)
    gates = {
        "transition_rows_sum_to_one": True,
        "fate_rows_sum_to_one": True,
        "terminal_own_fate": all(value >= args.minimum_terminal_own_fate for value in own_fates.values()),
        "time_direction": expected_time_delta >= args.minimum_time_direction,
        "pseudotime_direction": expected_pseudotime_delta > 0,
        "multiple_samples": samples.nunique() >= 2,
        "source_counts_preserved": True,
    }
    quality_status = "passed" if all(gates.values()) else "blocked"

    output = source.copy()
    output.obsm["biomed_fate_probabilities"] = fate
    output.obsp["biomed_fate_transition"] = transition
    output.uns["biomed_fate_mapping"] = {
        "engine": "CellRank-GPCCA", "mode": args.mode, "terminal_states": terminal_states,
        "quality_status": quality_status, "experimental_time_used": args.mode == "real-time-optimal-transport",
    }
    output.write_h5ad(output_paths[0])
    reloaded = sc.read_h5ad(output_paths[0])
    reload_valid = (
        reloaded.shape == source.shape
        and np.array_equal(reloaded.obs_names, source.obs_names)
        and np.array_equal(reloaded.var_names, source.var_names)
        and np.allclose(reloaded.obsm["biomed_fate_probabilities"], fate)
        and (sparse.csr_matrix(reloaded.obsp["biomed_fate_transition"]) != transition).nnz == 0
        and (count_matrix(reloaded, args.raw_count_location) != counts).nnz == 0
        and reloaded.uns["biomed_fate_mapping"]["quality_status"] == quality_status
    )
    reloaded_fates = pd.read_csv(output_paths[1], sep="\t")
    reloaded_drivers = pd.read_csv(output_paths[2], sep="\t")
    if not reload_valid or len(reloaded_fates) != source.n_obs or reloaded_drivers.empty:
        raise RuntimeError("fate object or evidence tables failed reload validation")

    report = {
        "schema_version": 1, "quality_status": quality_status,
        "input": {"filename": source_path.name, "sha256": sha256(source_path), "cells": source.n_obs, "genes": source.n_vars, "samples": int(samples.nunique()), "time_points": int(len(np.unique(times))), "raw_count_location": args.raw_count_location},
        "model": {"mode": args.mode, "kernel": type(kernel).__name__, "estimator": "GPCCA", "selected_hvgs": selected, "n_pcs": components, "n_neighbors": args.n_neighbors, "terminal_states": terminal_states, "transport_pairs": 0 if transport_problem is None else len(transport_problem.solutions), "ot_epsilon": args.ot_epsilon if transport_problem is not None else None, "ot_threshold": args.ot_threshold if transport_problem is not None else None, "seed": args.seed},
        "results": {"terminal_own_fate": own_fates, "expected_experimental_time_delta": expected_time_delta, "expected_pseudotime_delta": expected_pseudotime_delta, "maximum_fate_vs_time_spearman": fate_time_rho, "driver_rows": len(drivers), "transition_nonzero": int(transition.nnz)},
        "quality_thresholds": {"minimum_terminal_own_fate": args.minimum_terminal_own_fate, "minimum_time_direction": args.minimum_time_direction},
        "quality_gates": {**gates, "outputs_reloaded": True},
        "output": {"h5ad_filename": output_paths[0].name, "h5ad_sha256": sha256(output_paths[0]), "fate_table_filename": output_paths[1].name, "fate_table_sha256": sha256(output_paths[1]), "driver_table_filename": output_paths[2].name, "driver_table_sha256": sha256(output_paths[2])},
        "versions": {"python": platform.python_version(), "cellrank": version("cellrank"), "moscot": version("moscot"), "scanpy": version("scanpy"), "anndata": version("anndata"), "numpy": version("numpy"), "pandas": version("pandas"), "scipy": version("scipy"), "jax": version("jax"), "ott-jax": version("ott-jax")},
    }
    output_paths[3].write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"quality_status": quality_status, "mode": args.mode, "terminal_own_fate": own_fates}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
