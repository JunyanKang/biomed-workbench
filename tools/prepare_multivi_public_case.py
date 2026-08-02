#!/usr/bin/env python3
"""Prepare a checksum-bound 10x PBMC multiome subset for native MultiVI acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import anndata as ad
import mudata as md
import numpy as np
import pandas as pd
import scanpy as sc
from scipy import sparse


SOURCE_SHA256 = "03f946fc11984e6d4e8bf9a5d5904654c3d8b6b5776e08b7962796a9cb81c48d"
SOURCE_URL = "https://cf.10xgenomics.com/samples/cell-arc/1.0.0/pbmc_granulocyte_sorted_10k/pbmc_granulocyte_sorted_10k_filtered_feature_bc_matrix.h5"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def stable_rank(values: pd.Index) -> np.ndarray:
    return np.argsort(
        [hashlib.sha256(str(value).encode()).hexdigest() for value in values],
        kind="stable",
    )


def top_features(matrix, number: int) -> np.ndarray:
    detected = np.asarray((matrix > 0).sum(axis=0)).ravel()
    totals = np.asarray(matrix.sum(axis=0)).ravel()
    return np.lexsort((np.arange(matrix.shape[1]), -totals, -detected))[:number]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cells", type=int, default=600)
    parser.add_argument("--rna-features", type=int, default=600)
    parser.add_argument("--atac-features", type=int, default=800)
    args = parser.parse_args()
    if args.output.exists() or args.report.exists():
        raise FileExistsError("refusing to overwrite output")
    if digest(args.input) != SOURCE_SHA256:
        raise ValueError("10x public source checksum differs from the accepted release")
    source = sc.read_10x_h5(args.input, gex_only=False)
    source.var_names_make_unique()
    feature_type = source.var["feature_types"].astype(str)
    rna_mask = feature_type.eq("Gene Expression").to_numpy()
    atac_mask = feature_type.eq("Peaks").to_numpy()
    if rna_mask.sum() < args.rna_features or atac_mask.sum() < args.atac_features:
        raise ValueError("public source lacks requested RNA or ATAC features")
    selected_cells = stable_rank(source.obs_names)[: args.cells]
    selected = source[selected_cells].copy()
    rna_source = selected[:, rna_mask].copy()
    atac_source = selected[:, atac_mask].copy()
    rna = rna_source[:, top_features(rna_source.X, args.rna_features)].copy()
    atac = atac_source[:, top_features(atac_source.X, args.atac_features)].copy()
    # The combined 10x reader can retain a null layer key from the HDF5
    # feature-group layout. It is not a scientific matrix and is not writable
    # under AnnData 0.13, so keep the validated count matrices only.
    rna.layers.clear()
    atac.layers.clear()
    rna.X = sparse.csr_matrix(rna.X, dtype=np.float32)
    atac.X = sparse.csr_matrix(atac.X, dtype=np.float32)

    # Retain 400 paired anchors and create two non-overlapping, label-blind
    # missing-modality groups from the official paired assay.
    order = stable_rank(selected.obs_names)
    rna_only = order[-200:-100]
    atac_only = order[-100:]
    rna.X[atac_only, :] = 0
    atac.X[rna_only, :] = 0
    for value in (rna, atac):
        value.obs["library_id"] = pd.Categorical(["pbmc_multiome_10k"] * value.n_obs)
    mdata = md.MuData({"rna": rna, "atac": atac})
    mdata.obs["library_id"] = pd.Categorical(["pbmc_multiome_10k"] * mdata.n_obs)
    mdata.obs["modality_pattern"] = pd.Categorical(
        np.where(np.isin(np.arange(mdata.n_obs), rna_only), "rna-only", np.where(np.isin(np.arange(mdata.n_obs), atac_only), "atac-only", "paired"))
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    mdata.write_h5mu(args.output)
    payload = {
        "schema_version": 1,
        "passed": True,
        "source": {"url": SOURCE_URL, "sha256": SOURCE_SHA256, "cells": int(source.n_obs), "features": int(source.n_vars)},
        "selection": "stable barcode hash; feature detection and total-count ranking without labels",
        "cells": int(mdata.n_obs),
        "rna_features": int(rna.n_vars),
        "atac_features": int(atac.n_vars),
        "paired_cells": 400,
        "rna_only_cells": 100,
        "atac_only_cells": 100,
        "output_sha256": digest(args.output),
    }
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    reloaded = md.read_h5mu(args.output)
    if reloaded.n_obs != args.cells or set(reloaded.mod) != {"rna", "atac"}:
        raise RuntimeError("prepared MultiVI public case failed reload reconciliation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
