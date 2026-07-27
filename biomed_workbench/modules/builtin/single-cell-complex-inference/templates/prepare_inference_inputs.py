#!/usr/bin/env python3
"""Prepare count-conserving pseudobulk and complete composition inputs."""

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
from scipy import sparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-h5ad", required=True)
    parser.add_argument("--raw-count-location", required=True)
    parser.add_argument("--sample-key", required=True)
    parser.add_argument("--subject-key", required=True)
    parser.add_argument("--cell-type-key", required=True)
    parser.add_argument("--condition-key", required=True)
    parser.add_argument("--time-key", required=True)
    parser.add_argument("--categorical-covariates", default="none")
    parser.add_argument("--continuous-covariates", default="none")
    parser.add_argument("--require-longitudinal", choices=("true", "false"), required=True)
    parser.add_argument("--min-cells-per-pseudobulk", type=int, required=True)
    parser.add_argument("--min-library-size", type=int, required=True)
    parser.add_argument("--output-counts", required=True)
    parser.add_argument("--output-pseudobulk-metadata", required=True)
    parser.add_argument("--output-composition", required=True)
    parser.add_argument("--report", required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def comma_list(value: str, name: str) -> list[str]:
    if value == "none":
        return []
    items = [item.strip() for item in value.split(",")]
    if not items or any(not item for item in items) or len(items) != len(set(items)):
        raise ValueError(f"{name} must be a unique comma-separated list or none")
    return items


def count_matrix(adata: anndata.AnnData, location: str):
    if location == "X":
        matrix = adata.X
    elif location.startswith("layers.") and location[7:] in adata.layers:
        matrix = adata.layers[location[7:]]
    else:
        raise ValueError("raw-count-location must be X or an existing layers.NAME")
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix).reshape(-1)
    if values.size == 0 or not np.isfinite(values).all() or np.any(values < 0) or not np.allclose(values, np.rint(values), rtol=0, atol=1e-8):
        raise ValueError("raw counts must be finite nonnegative and integer-like")
    return sparse.csr_matrix(matrix, dtype=np.int64)


def normalized_metadata(obs: pd.DataFrame, fields: list[str], continuous: set[str]) -> pd.DataFrame:
    missing = sorted(set(fields) - set(obs.columns))
    if missing:
        raise ValueError(f"required observation metadata is missing: {', '.join(missing)}")
    result = obs.loc[:, fields].copy()
    for field in fields:
        if result[field].isna().any():
            raise ValueError(f"metadata field contains missing values: {field}")
        if field in continuous:
            result[field] = pd.to_numeric(result[field], errors="raise").astype(float)
            if not np.isfinite(result[field]).all():
                raise ValueError(f"continuous metadata is nonfinite: {field}")
        else:
            result[field] = result[field].astype(str).str.strip()
            if result[field].eq("").any():
                raise ValueError(f"metadata field contains empty values: {field}")
    return result


def validate_sample_semantics(metadata: pd.DataFrame, sample_key: str, fields: list[str]) -> pd.DataFrame:
    grouped = metadata.groupby(sample_key, observed=True, sort=True)
    inconsistent = {
        field: sorted(str(sample) for sample, count in grouped[field].nunique(dropna=False).items() if int(count) != 1)
        for field in fields
    }
    inconsistent = {field: samples for field, samples in inconsistent.items() if samples}
    if inconsistent:
        raise ValueError(f"biological samples have inconsistent design metadata: {json.dumps(inconsistent, sort_keys=True)}")
    return metadata.drop_duplicates(sample_key).set_index(sample_key).sort_index()


def main() -> int:
    args = parse_args()
    source = Path(args.input_h5ad).resolve(strict=True)
    source_digest = sha256(source)
    outputs = [Path(args.output_counts), Path(args.output_pseudobulk_metadata), Path(args.output_composition), Path(args.report)]
    if len({path.resolve() for path in outputs}) != len(outputs):
        raise ValueError("output paths must be distinct")
    for output in outputs:
        if output.exists():
            raise FileExistsError(f"refusing to overwrite output: {output.name}")
        output.parent.mkdir(parents=True, exist_ok=True)
    if args.min_cells_per_pseudobulk < 1 or args.min_library_size < 1:
        raise ValueError("pseudobulk thresholds must be positive")

    categorical = comma_list(args.categorical_covariates, "categorical-covariates")
    continuous = comma_list(args.continuous_covariates, "continuous-covariates")
    if set(categorical) & set(continuous):
        raise ValueError("categorical and continuous covariates must be disjoint")
    primary = [args.sample_key, args.subject_key, args.cell_type_key, args.condition_key, args.time_key]
    all_fields = [*primary, *categorical, *continuous]
    if len(all_fields) != len(set(all_fields)):
        raise ValueError("sample, subject, cell type, condition, time, and covariate keys must be distinct")

    adata = anndata.read_h5ad(source)
    if adata.n_obs < 2 or adata.n_vars < 2 or not adata.obs_names.is_unique or not adata.var_names.is_unique:
        raise ValueError("input requires unique cells and features and a nontrivial matrix")
    counts = count_matrix(adata, args.raw_count_location)
    metadata = normalized_metadata(adata.obs, all_fields, {args.time_key, *continuous})
    sample_fields = [args.subject_key, args.condition_key, args.time_key, *categorical, *continuous]
    sample_design = validate_sample_semantics(metadata, args.sample_key, sample_fields)
    if sample_design.index.nunique() < 4 or sample_design[args.subject_key].nunique() < 2:
        raise ValueError("complex inference requires at least four biological samples and two subjects")

    repeated = sample_design.groupby(args.subject_key, observed=True).agg(
        samples=(args.subject_key, "size"), unique_times=(args.time_key, "nunique")
    )
    repeated_subjects = repeated.index[(repeated["samples"] >= 2) & (repeated["unique_times"] >= 2)].astype(str).tolist()
    if args.require_longitudinal == "true" and len(repeated_subjects) < 2:
        raise ValueError("longitudinal inference requires at least two subjects observed at two distinct times")

    group_index = pd.MultiIndex.from_frame(metadata[[args.sample_key, args.cell_type_key]])
    group_codes, observed_groups = pd.factorize(group_index, sort=True)
    if np.any(group_codes < 0):
        raise RuntimeError("every cell must map to one sample and cell-type pseudobulk")
    assignment = sparse.csr_matrix(
        (np.ones(adata.n_obs, dtype=np.int64), (group_codes, np.arange(adata.n_obs))),
        shape=(len(observed_groups), adata.n_obs),
    )
    aggregate = (assignment @ counts).tocsr().astype(np.int64)
    if int(assignment.sum()) != adata.n_obs or int(aggregate.sum()) != int(counts.sum()):
        raise RuntimeError("cell or raw-count accounting failed during pseudobulk aggregation")

    pseudobulk_rows = []
    for index, (sample, cell_type) in enumerate(observed_groups):
        sample, cell_type = str(sample), str(cell_type)
        n_cells = int((group_codes == index).sum())
        library_size = int(aggregate[index].sum())
        reasons = []
        if n_cells < args.min_cells_per_pseudobulk:
            reasons.append("insufficient_cells")
        if library_size < args.min_library_size:
            reasons.append("insufficient_library_size")
        design = sample_design.loc[sample]
        row = {
            "pseudobulk_id": f"pb-{index + 1:06d}", "biological_sample": sample, "subject": str(design[args.subject_key]),
            "cell_type": cell_type, "condition": str(design[args.condition_key]), "time": float(design[args.time_key]),
            "n_cells": n_cells, "library_size": library_size, "eligible": not reasons,
            "exclusion_reason": ";".join(reasons) if reasons else "retained",
        }
        row.update({field: design[field] for field in [*categorical, *continuous]})
        pseudobulk_rows.append(row)
    pseudobulk = pd.DataFrame(pseudobulk_rows)
    pseudobulk_ids = pseudobulk["pseudobulk_id"].tolist()
    count_frame = pd.DataFrame.sparse.from_spmatrix(aggregate.transpose(), index=adata.var_names.astype(str), columns=pseudobulk_ids)
    count_frame.index.name = "gene_id"
    count_frame.to_csv(outputs[0], sep="\t")
    pseudobulk.to_csv(outputs[1], sep="\t", index=False)

    samples = sample_design.index.astype(str).tolist()
    cell_types = sorted(metadata[args.cell_type_key].unique().astype(str).tolist())
    observed_counts = metadata.groupby([args.sample_key, args.cell_type_key], observed=True).size()
    composition_rows = []
    sample_totals = metadata.groupby(args.sample_key, observed=True).size().astype(int)
    for sample in samples:
        design = sample_design.loc[sample]
        total = int(sample_totals.loc[sample])
        for cell_type in cell_types:
            cell_count = int(observed_counts.get((sample, cell_type), 0))
            row = {
                "biological_sample": sample, "subject": str(design[args.subject_key]), "condition": str(design[args.condition_key]),
                "time": float(design[args.time_key]), "cell_type": cell_type, "cell_count": cell_count,
                "total_cells": total, "proportion": cell_count / total,
            }
            row.update({field: design[field] for field in [*categorical, *continuous]})
            composition_rows.append(row)
    composition = pd.DataFrame(composition_rows)
    if len(composition) != len(samples) * len(cell_types):
        raise RuntimeError("composition grid is incomplete")
    reconciliation = composition.groupby("biological_sample", observed=True).agg(
        cell_count=("cell_count", "sum"), total_cells=("total_cells", "first"), proportion=("proportion", "sum")
    )
    if not np.array_equal(reconciliation["cell_count"], reconciliation["total_cells"]) or not np.allclose(reconciliation["proportion"], 1.0):
        raise RuntimeError("composition counts and proportions do not reconcile by sample")
    composition.to_csv(outputs[2], sep="\t", index=False)
    reloaded_counts = pd.read_csv(outputs[0], sep="\t")
    reloaded_pseudobulk = pd.read_csv(outputs[1], sep="\t")
    reloaded_composition = pd.read_csv(outputs[2], sep="\t")
    if (
        reloaded_counts.shape != (adata.n_vars, len(pseudobulk) + 1)
        or len(reloaded_pseudobulk) != len(pseudobulk)
        or len(reloaded_composition) != len(composition)
        or int(reloaded_counts.drop(columns=["gene_id"]).to_numpy().sum())
        != int(counts.sum())
        or set(reloaded_pseudobulk["pseudobulk_id"]) != set(pseudobulk_ids)
        or not np.allclose(
            reloaded_composition.groupby("biological_sample", observed=True)[
                "proportion"
            ].sum(),
            1.0,
        )
    ):
        raise RuntimeError("serialized inference inputs failed reload accounting")
    source_immutable = sha256(source) == source_digest
    if not source_immutable:
        raise RuntimeError("source h5ad changed during inference preparation")

    report = {
        "schema_version": 2,
        "input": {"filename": source.name, "sha256": source_digest, "cells": int(adata.n_obs), "features": int(adata.n_vars), "raw_count_location": args.raw_count_location, "raw_count_sum": int(counts.sum()), "source_immutable": source_immutable},
        "design": {"sample_key": args.sample_key, "subject_key": args.subject_key, "cell_type_key": args.cell_type_key, "condition_key": args.condition_key, "time_key": args.time_key, "categorical_covariates": categorical, "continuous_covariates": continuous, "biological_samples": len(samples), "subjects": int(sample_design[args.subject_key].nunique()), "repeated_subjects": repeated_subjects},
        "thresholds": {"min_cells_per_pseudobulk": args.min_cells_per_pseudobulk, "min_library_size": args.min_library_size},
        "accounting": {"input_cells": int(adata.n_obs), "assigned_cells": int(assignment.sum()), "pseudobulks": len(pseudobulk), "eligible_pseudobulks": int(pseudobulk["eligible"].sum()), "excluded_pseudobulks": int((~pseudobulk["eligible"]).sum()), "aggregate_count_sum": int(aggregate.sum()), "composition_rows": len(composition), "zero_count_composition_rows": int((composition["cell_count"] == 0).sum()), "all_cells_accounted": True, "raw_counts_conserved": True, "composition_grid_complete": True, "sample_compositions_sum_to_one": True, "serialized_outputs_reloaded": True},
        "outputs": {"counts_filename": outputs[0].name, "counts_sha256": sha256(outputs[0]), "pseudobulk_metadata_filename": outputs[1].name, "pseudobulk_metadata_sha256": sha256(outputs[1]), "composition_filename": outputs[2].name, "composition_sha256": sha256(outputs[2])},
        "versions": {"python": platform.python_version(), "anndata": importlib.metadata.version("anndata"), "numpy": importlib.metadata.version("numpy"), "pandas": importlib.metadata.version("pandas"), "scipy": importlib.metadata.version("scipy")},
    }
    outputs[3].write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
