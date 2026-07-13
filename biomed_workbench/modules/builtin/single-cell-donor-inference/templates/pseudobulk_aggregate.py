#!/usr/bin/env python3
"""Aggregate validated single-cell raw counts into biological pseudobulks.

Codex must inspect and adapt this project template before execution. The script
does not install software, infer metadata semantics, or modify the source object.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path

import anndata
import numpy as np
import pandas as pd
import scanpy as sc
import scipy
from scipy import sparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-h5ad", required=True)
    parser.add_argument("--raw-count-location", required=True)
    parser.add_argument("--sample-key", required=True)
    parser.add_argument("--cell-type-key", required=True)
    parser.add_argument("--condition-key", required=True)
    parser.add_argument("--covariates", default="none")
    parser.add_argument("--subject-key", default="none")
    parser.add_argument("--min-cells-per-pseudobulk", type=int, required=True)
    parser.add_argument("--min-library-size", type=int, required=True)
    parser.add_argument("--output-counts", required=True)
    parser.add_argument("--output-metadata", required=True)
    parser.add_argument("--accounting-report", required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def comma_list(value: str) -> list[str]:
    if value == "none":
        return []
    items = [item.strip() for item in value.split(",")]
    if not items or any(not item for item in items) or len(items) != len(set(items)):
        raise ValueError("covariates must be a unique comma-separated list or none")
    return items


def matrix_values(matrix) -> np.ndarray:
    if sparse.issparse(matrix):
        return np.asarray(matrix.data)
    return np.asarray(matrix).reshape(-1)


def raw_counts(adata: anndata.AnnData, location: str):
    if location == "X":
        return adata.X
    if location.startswith("layers.") and location[7:] in adata.layers:
        return adata.layers[location[7:]]
    raise ValueError("raw-count-location must be X or an existing layers.NAME entry")


def validate_counts(matrix) -> None:
    values = matrix_values(matrix)
    if values.size and (not np.isfinite(values).all() or float(values.min()) < 0):
        raise ValueError("raw counts must contain only finite nonnegative values")
    if values.size and not np.allclose(values, np.rint(values), rtol=0, atol=1e-8):
        raise ValueError("raw count location is not integer-like")


def normalized_metadata(obs: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
    missing = [field for field in fields if field not in obs.columns]
    if missing:
        raise ValueError(f"required observation metadata is missing: {', '.join(missing)}")
    result = obs.loc[:, fields].copy()
    for field in fields:
        if result[field].isna().any():
            raise ValueError(f"metadata field contains missing values: {field}")
        result[field] = result[field].astype(str).str.strip()
        if result[field].eq("").any():
            raise ValueError(f"metadata field contains empty values: {field}")
    return result


def validate_sample_semantics(metadata: pd.DataFrame, sample_key: str, fields: list[str]) -> None:
    grouped = metadata.groupby(sample_key, observed=True, sort=True)
    inconsistent = {
        field: sorted(str(sample) for sample, count in grouped[field].nunique().items() if int(count) != 1)
        for field in fields
    }
    inconsistent = {field: samples for field, samples in inconsistent.items() if samples}
    if inconsistent:
        raise ValueError(f"biological samples have inconsistent design metadata: {json.dumps(inconsistent, sort_keys=True)}")


def main() -> int:
    args = parse_args()
    source = Path(args.input_h5ad).resolve(strict=True)
    outputs = [Path(args.output_counts), Path(args.output_metadata), Path(args.accounting_report)]
    for output in outputs:
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise FileExistsError(f"refusing to overwrite output: {output.name}")
    if args.min_cells_per_pseudobulk < 1 or args.min_library_size < 1:
        raise ValueError("pseudobulk cell and library thresholds must be positive")

    covariates = comma_list(args.covariates)
    subject_key = None if args.subject_key == "none" else args.subject_key
    if len({args.sample_key, args.cell_type_key, args.condition_key, *covariates, *([subject_key] if subject_key else [])}) != 3 + len(covariates) + (1 if subject_key else 0):
        raise ValueError("sample, cell-type, condition, subject, and covariate keys must be distinct")

    adata = sc.read_h5ad(source, backed=None)
    if adata.n_obs < 2 or adata.n_vars < 1:
        raise ValueError("single-cell input must contain at least two cells and one feature")
    if not adata.obs_names.is_unique or not adata.var_names.is_unique:
        raise ValueError("cell and feature identifiers must be unique")
    fields = [args.sample_key, args.cell_type_key, args.condition_key, *covariates]
    if subject_key:
        fields.append(subject_key)
    metadata = normalized_metadata(adata.obs, fields)
    design_fields = [args.condition_key, *covariates, *([subject_key] if subject_key else [])]
    validate_sample_semantics(metadata, args.sample_key, design_fields)

    counts = raw_counts(adata, args.raw_count_location)
    validate_counts(counts)
    counts = sparse.csr_matrix(counts, dtype=np.int64)
    group_keys = pd.MultiIndex.from_frame(metadata[[args.sample_key, args.cell_type_key]])
    group_codes, unique_groups = pd.factorize(group_keys, sort=True)
    if np.any(group_codes < 0):
        raise ValueError("every cell must map to one pseudobulk group")
    group_count = len(unique_groups)
    assignment = sparse.csr_matrix(
        (np.ones(adata.n_obs, dtype=np.int64), (group_codes, np.arange(adata.n_obs))),
        shape=(group_count, adata.n_obs),
    )
    aggregate = (assignment @ counts).tocsr().astype(np.int64)
    if int(assignment.sum()) != adata.n_obs or int(aggregate.sum()) != int(counts.sum()):
        raise RuntimeError("cell or raw-count accounting failed during aggregation")

    sample_design = metadata.drop_duplicates(args.sample_key).set_index(args.sample_key)
    rows = []
    for index, key in enumerate(unique_groups):
        sample_id, cell_type = map(str, key)
        n_cells = int((group_codes == index).sum())
        library_size = int(aggregate[index].sum())
        reasons = []
        if n_cells < args.min_cells_per_pseudobulk:
            reasons.append("insufficient_cells")
        if library_size < args.min_library_size:
            reasons.append("insufficient_library_size")
        row = {
            "pseudobulk_id": f"pb-{index + 1:06d}",
            "biological_sample": sample_id,
            "cell_type": cell_type,
            "condition": str(sample_design.loc[sample_id, args.condition_key]),
            "n_cells": n_cells,
            "library_size": library_size,
            "eligible": not reasons,
            "exclusion_reason": ";".join(reasons) if reasons else "retained",
        }
        for covariate in covariates:
            row[covariate] = str(sample_design.loc[sample_id, covariate])
        if subject_key:
            row[subject_key] = str(sample_design.loc[sample_id, subject_key])
        rows.append(row)
    pseudobulk_metadata = pd.DataFrame(rows)
    pseudobulk_ids = pseudobulk_metadata["pseudobulk_id"].tolist()

    count_frame = pd.DataFrame.sparse.from_spmatrix(
        aggregate.transpose().tocsr(), index=adata.var_names.astype(str), columns=pseudobulk_ids
    )
    count_frame.index.name = "gene_id"
    count_frame.to_csv(outputs[0], sep="\t")
    pseudobulk_metadata.to_csv(outputs[1], sep="\t", index=False)

    by_cell_type = []
    for cell_type, frame in pseudobulk_metadata.groupby("cell_type", observed=True, sort=True):
        by_cell_type.append({
            "cell_type": str(cell_type),
            "pseudobulks": int(len(frame)),
            "eligible_pseudobulks": int(frame["eligible"].sum()),
            "cells": int(frame["n_cells"].sum()),
            "conditions": sorted(frame["condition"].unique().tolist()),
        })
    report = {
        "schema_version": 1,
        "input": {
            "filename": source.name,
            "sha256": sha256(source),
            "cells": int(adata.n_obs),
            "features": int(adata.n_vars),
            "raw_count_location": args.raw_count_location,
            "raw_count_sum": int(counts.sum()),
        },
        "design": {
            "sample_key": args.sample_key,
            "cell_type_key": args.cell_type_key,
            "condition_key": args.condition_key,
            "covariates": covariates,
            "subject_key": subject_key or "none",
        },
        "thresholds": {
            "min_cells_per_pseudobulk": args.min_cells_per_pseudobulk,
            "min_library_size": args.min_library_size,
        },
        "accounting": {
            "input_cells": int(adata.n_obs),
            "assigned_cells": int(assignment.sum()),
            "pseudobulks": int(group_count),
            "eligible_pseudobulks": int(pseudobulk_metadata["eligible"].sum()),
            "excluded_pseudobulks": int((~pseudobulk_metadata["eligible"]).sum()),
            "aggregate_count_sum": int(aggregate.sum()),
            "all_cells_accounted": bool(int(assignment.sum()) == adata.n_obs),
            "raw_counts_conserved": bool(int(aggregate.sum()) == int(counts.sum())),
        },
        "cell_types": by_cell_type,
        "outputs": {
            "counts_filename": outputs[0].name,
            "counts_sha256": sha256(outputs[0]),
            "metadata_filename": outputs[1].name,
            "metadata_sha256": sha256(outputs[1]),
        },
        "versions": {
            "python": platform.python_version(),
            "scanpy": sc.__version__,
            "anndata": anndata.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
        },
    }
    outputs[2].write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"pseudobulks": group_count, "eligible": report["accounting"]["eligible_pseudobulks"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
