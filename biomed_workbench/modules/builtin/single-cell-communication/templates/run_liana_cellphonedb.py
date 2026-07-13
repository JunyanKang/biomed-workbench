#!/usr/bin/env python3
"""Run sample-aware LIANA and CellPhoneDB cell-cell communication analysis.

Codex must inspect the real count-backed h5ad, biological design, gene symbols,
and database release before adapting this template. Cells are observations;
biological samples are the units used to assess reproducibility.
"""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import tempfile
from typing import Any

import anndata
import numpy as np
import pandas as pd
import scanpy as sc
from scipy import sparse
from scipy.stats import combine_pvalues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-h5ad", required=True)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--method", choices=("liana", "cellphonedb", "both"), required=True)
    parser.add_argument("--cell-type-key", required=True)
    parser.add_argument("--sample-key", required=True)
    parser.add_argument("--condition-key", required=True)
    parser.add_argument("--raw-count-location", required=True)
    parser.add_argument("--species", choices=("human", "mouse"), required=True)
    parser.add_argument("--cellphonedb-database")
    parser.add_argument("--minimum-cells", type=int, required=True)
    parser.add_argument("--minimum-samples", type=int, required=True)
    parser.add_argument("--expression-proportion", type=float, required=True)
    parser.add_argument("--permutations", type=int, required=True)
    parser.add_argument("--fdr", type=float, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--jobs", type=int, default=1)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def matrix_values(matrix: Any) -> np.ndarray:
    return np.asarray(matrix.data) if sparse.issparse(matrix) else np.asarray(matrix).reshape(-1)


def raw_counts(adata: anndata.AnnData, location: str):
    if location == "X":
        return adata.X
    if location.startswith("layers.") and location[7:] in adata.layers:
        return adata.layers[location[7:]]
    raise ValueError("raw-count-location must be X or an existing layers.NAME entry")


def validate_input(adata: anndata.AnnData, args: argparse.Namespace) -> pd.DataFrame:
    if not adata.obs_names.is_unique or not adata.var_names.is_unique:
        raise ValueError("cell and gene identifiers must be unique")
    if adata.n_obs < 2 * args.minimum_cells or adata.n_vars < 2:
        raise ValueError("input is too small for communication analysis")
    required = [args.cell_type_key, args.sample_key, args.condition_key]
    missing = [field for field in required if field not in adata.obs]
    if missing:
        raise ValueError(f"required observation metadata is missing: {', '.join(missing)}")
    metadata = adata.obs.loc[:, required].copy()
    for field in required:
        if metadata[field].isna().any():
            raise ValueError(f"metadata contains missing values: {field}")
        metadata[field] = metadata[field].astype(str).str.strip()
        if metadata[field].eq("").any():
            raise ValueError(f"metadata contains empty values: {field}")
    sample_condition = metadata.groupby(args.sample_key, observed=True)[args.condition_key].nunique()
    if not bool((sample_condition == 1).all()):
        raise ValueError("each biological sample must map to exactly one condition")
    counts = raw_counts(adata, args.raw_count_location)
    values = matrix_values(counts)
    if values.size and (not np.isfinite(values).all() or float(values.min()) < 0):
        raise ValueError("raw counts must be finite and nonnegative")
    if values.size and not np.allclose(values, np.rint(values), rtol=0, atol=1e-8):
        raise ValueError("declared raw counts are not integer-like")
    if args.minimum_cells < 3 or args.minimum_samples < 2:
        raise ValueError("minimum cells and biological samples are too small")
    if not 0 < args.expression_proportion <= 1 or not 0 < args.fdr < 1:
        raise ValueError("expression proportion and FDR thresholds are invalid")
    if args.permutations < 100 or args.jobs < 1:
        raise ValueError("permutations or jobs are below the validated minimum")
    return metadata


def working_sample(adata: anndata.AnnData, indices: np.ndarray, counts) -> anndata.AnnData:
    matrix = sparse.csr_matrix(counts[indices], dtype=np.float64)
    return anndata.AnnData(X=matrix, obs=adata.obs.iloc[indices].copy(), var=adata.var.copy())


def run_liana(sample: anndata.AnnData, args: argparse.Namespace) -> pd.DataFrame:
    cache_root = Path(tempfile.gettempdir()) / "biomed-workbench-communication-cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("NUMBA_CACHE_DIR", str(cache_root / "numba"))
    os.environ.setdefault("MPLCONFIGDIR", str(cache_root / "matplotlib"))
    import liana as li

    sc.pp.normalize_total(sample, target_sum=10000)
    sc.pp.log1p(sample)
    result = li.mt.rank_aggregate(
        sample,
        groupby=args.cell_type_key,
        resource_name="consensus",
        expr_prop=args.expression_proportion,
        min_cells=args.minimum_cells,
        use_raw=False,
        n_perms=args.permutations,
        seed=args.seed,
        n_jobs=args.jobs,
        inplace=False,
        verbose=False,
    )
    if result is None or result.empty:
        return pd.DataFrame()
    required = {"source", "target", "ligand_complex", "receptor_complex"}
    if not required <= set(result):
        raise ValueError("LIANA result lacks required sender, receiver, ligand, or receptor fields")
    magnitude = next((name for name in ("magnitude_rank", "lr_means", "magnitude") if name in result), None)
    specificity = next((name for name in ("specificity_rank", "cellphone_pvals", "specificity") if name in result), None)
    if magnitude is None:
        raise ValueError("LIANA result lacks a recognized interaction magnitude")
    output = pd.DataFrame(
        {
            "sender": result["source"].astype(str),
            "receiver": result["target"].astype(str),
            "ligand": result["ligand_complex"].astype(str),
            "receptor": result["receptor_complex"].astype(str),
            "score": pd.to_numeric(result[magnitude], errors="coerce"),
            "p_value": pd.to_numeric(result[specificity], errors="coerce") if specificity else np.nan,
            "method": "liana-rank-aggregate",
        }
    )
    return output.replace([np.inf, -np.inf], np.nan).dropna(subset=["score"])


def _cellphonedb_long(table: pd.DataFrame, value_name: str) -> pd.DataFrame:
    pair_columns = [name for name in table if "|" in str(name)]
    if not pair_columns:
        raise ValueError("CellPhoneDB result has no sender-receiver columns")
    ligand_column = next((name for name in ("gene_a", "partner_a", "interacting_pair") if name in table), None)
    receptor_column = next((name for name in ("gene_b", "partner_b") if name in table), None)
    if ligand_column is None:
        raise ValueError("CellPhoneDB result lacks interaction identifiers")
    interaction_column = next((name for name in ("id_cp_interaction", "interacting_pair") if name in table), None)
    interaction_id = table[interaction_column].astype(str) if interaction_column else table.index.astype(str)
    identity = table[ligand_column].astype(str)
    ligand = identity.str.split("_", n=1).str[0] if receptor_column is None else identity
    receptor = identity.str.split("_", n=1).str[-1] if receptor_column is None else table[receptor_column].astype(str)
    base = pd.DataFrame({"interaction_id": interaction_id, "ligand": ligand, "receptor": receptor})
    long = pd.concat([base, table[pair_columns]], axis=1).melt(
        id_vars=["interaction_id", "ligand", "receptor"], var_name="cell_pair", value_name=value_name
    )
    split = long["cell_pair"].str.split("|", n=1, expand=True)
    long["sender"], long["receiver"] = split[0], split[1]
    long[value_name] = pd.to_numeric(long[value_name], errors="coerce")
    return long.drop(columns="cell_pair")


def run_cellphonedb(sample: anndata.AnnData, args: argparse.Namespace, workspace: Path) -> pd.DataFrame:
    if args.species != "human":
        raise ValueError("CellPhoneDB v5 template is restricted to human gene symbols")
    if not args.cellphonedb_database:
        raise ValueError("CellPhoneDB analysis requires an explicit versioned database zip")
    database = Path(args.cellphonedb_database).resolve(strict=True)
    from cellphonedb.src.core.methods import cpdb_statistical_analysis_method

    sample.obs_names = sample.obs_names.astype(str)
    counts_path = workspace / "counts.h5ad"
    meta_path = workspace / "meta.tsv"
    output_path = workspace / "output"
    output_path.mkdir()
    sample.write_h5ad(counts_path, compression="gzip")
    pd.DataFrame({"Cell": sample.obs_names, "cell_type": sample.obs[args.cell_type_key].astype(str).values}).to_csv(
        meta_path, sep="\t", index=False
    )
    result = cpdb_statistical_analysis_method.call(
        cpdb_file_path=str(database),
        meta_file_path=str(meta_path),
        counts_file_path=str(counts_path),
        counts_data="gene_name",
        output_path=str(output_path),
        iterations=args.permutations,
        threshold=args.expression_proportion,
        threads=args.jobs,
        debug_seed=args.seed,
        pvalue=args.fdr,
        score_interactions=True,
    )
    if not isinstance(result, dict) or "pvalues" not in result or "means" not in result:
        raise ValueError("CellPhoneDB did not return p-value and mean interaction tables")
    pvalues = _cellphonedb_long(result["pvalues"], "p_value")
    means = _cellphonedb_long(result["means"], "score")
    merged = means.merge(
        pvalues,
        on=["interaction_id", "sender", "receiver", "ligand", "receptor"],
        how="inner",
        validate="one_to_one",
    )
    merged["method"] = "cellphonedb-statistical"
    return merged.dropna(subset=["score", "p_value"])


def adjust_bh(values: pd.Series) -> pd.Series:
    array = values.to_numpy(dtype=float)
    valid = np.isfinite(array)
    adjusted = np.full(len(array), np.nan)
    if valid.any():
        order = np.argsort(array[valid])
        ranked = array[valid][order]
        corrected = np.minimum.accumulate((ranked * len(ranked) / np.arange(1, len(ranked) + 1))[::-1])[::-1]
        restored = np.empty(len(ranked))
        restored[order] = np.clip(corrected, 0, 1)
        adjusted[valid] = restored
    return pd.Series(adjusted, index=values.index)


def summarize_replicates(interactions: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    keys = ["condition", "method", "sender", "receiver", "ligand", "receptor"]
    rows = []
    for identity, frame in interactions.groupby(keys, observed=True, sort=True):
        pvalues = frame["p_value"].dropna().clip(lower=np.finfo(float).tiny, upper=1)
        combined = float(combine_pvalues(pvalues, method="fisher").pvalue) if len(pvalues) >= args.minimum_samples else math.nan
        rows.append(
            {
                **dict(zip(keys, identity, strict=True)),
                "sample_support": int(frame["sample"].nunique()),
                "median_score": float(frame["score"].median()),
                "combined_p_value": combined,
            }
        )
    result = pd.DataFrame(rows)
    result["fdr"] = result.groupby(["condition", "method"], observed=True)["combined_p_value"].transform(adjust_bh)
    result["replicated"] = (result["sample_support"] >= args.minimum_samples) & (result["fdr"] <= args.fdr)
    return result


def main() -> int:
    args = parse_args()
    source = Path(args.input_h5ad).resolve(strict=True)
    output_directory = Path(args.output_directory).resolve()
    report_path = Path(args.report).resolve()
    if output_directory.exists() or report_path.exists():
        raise FileExistsError("refusing to overwrite communication outputs")
    output_directory.mkdir(parents=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    adata = sc.read_h5ad(source)
    metadata = validate_input(adata, args)
    counts = sparse.csr_matrix(raw_counts(adata, args.raw_count_location))
    methods = ("liana", "cellphonedb") if args.method == "both" else (args.method,)
    rows = []
    sample_records = []
    for sample_id, sample_frame in metadata.groupby(args.sample_key, observed=True, sort=True):
        indices = adata.obs_names.get_indexer(sample_frame.index)
        group_counts = sample_frame[args.cell_type_key].value_counts()
        eligible = set(group_counts[group_counts >= args.minimum_cells].index)
        keep = sample_frame[args.cell_type_key].isin(eligible).to_numpy()
        indices = indices[keep]
        if len(eligible) < 2:
            sample_records.append({"sample": sample_id, "status": "blocked", "reason": "fewer-than-two-eligible-cell-types"})
            continue
        condition = str(sample_frame[args.condition_key].iloc[0])
        for method in methods:
            sample = working_sample(adata, indices, counts)
            with tempfile.TemporaryDirectory(prefix=f"communication-{method}-") as temporary:
                result = run_liana(sample, args) if method == "liana" else run_cellphonedb(sample, args, Path(temporary))
            if result.empty:
                sample_records.append({"sample": sample_id, "method": method, "status": "blocked", "reason": "no-interactions"})
                continue
            result["sample"] = str(sample_id)
            result["condition"] = condition
            result["within_sample_fdr"] = adjust_bh(result["p_value"])
            rows.append(result)
            sample_records.append({"sample": sample_id, "method": method, "status": "observed", "interaction_count": len(result)})
    if not rows:
        raise ValueError("no sample produced communication evidence")
    interactions = pd.concat(rows, ignore_index=True)
    summary = summarize_replicates(interactions, args)
    interactions_path = output_directory / "sample_interactions.tsv"
    summary_path = output_directory / "replicated_interactions.tsv"
    interactions.to_csv(interactions_path, sep="\t", index=False)
    summary.to_csv(summary_path, sep="\t", index=False)
    sample_counts = metadata.groupby(args.condition_key, observed=True)[args.sample_key].nunique().to_dict()
    condition_inference_allowed = bool(sample_counts) and min(sample_counts.values()) >= args.minimum_samples
    report = {
        "schema_version": 1,
        "input": {"sha256": sha256(source), "cells": adata.n_obs, "genes": adata.n_vars},
        "design": {"sample_counts_by_condition": sample_counts, "condition_inference_allowed": condition_inference_allowed},
        "methods": list(methods),
        "sample_runs": sample_records,
        "outputs": {
            "sample_interactions": {"path": interactions_path.name, "sha256": sha256(interactions_path), "rows": len(interactions)},
            "replicated_interactions": {"path": summary_path.name, "sha256": sha256(summary_path), "rows": len(summary)},
        },
        "quality": {
            "status": "passed" if condition_inference_allowed and bool(summary["replicated"].any()) else "descriptive-only",
            "replicated_interaction_count": int(summary["replicated"].sum()),
            "source_counts_preserved": bool((counts != sparse.csr_matrix(raw_counts(adata, args.raw_count_location))).nnz == 0),
        },
        "parameters": vars(args),
        "versions": {
            "python": platform.python_version(),
            "anndata": version("anndata"),
            "scanpy": version("scanpy"),
            **({"liana": version("liana")} if "liana" in methods else {}),
            **({"cellphonedb": version("cellphonedb")} if "cellphonedb" in methods else {}),
        },
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    reloaded = pd.read_csv(summary_path, sep="\t")
    if len(reloaded) != len(summary) or sha256(source) != report["input"]["sha256"]:
        raise ValueError("communication output reload or source preservation failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
