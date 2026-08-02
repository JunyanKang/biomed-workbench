#!/usr/bin/env python3
"""Run pairwise CAME with an explicit many-to-many orthology table."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import torch
from came import pipeline, pp
from scipy import sparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-h5ad", type=Path, required=True)
    parser.add_argument("--query-h5ad", type=Path, required=True)
    parser.add_argument("--orthology-tsv", type=Path, required=True)
    parser.add_argument("--one-to-one-tsv", type=Path)
    parser.add_argument("--reference-label-key", required=True)
    parser.add_argument("--query-label-key")
    parser.add_argument("--reference-species", required=True)
    parser.add_argument("--query-species", required=True)
    parser.add_argument("--ntop-deg", type=int, default=50)
    parser.add_argument("--ntop-deg-nodes", type=int, default=50)
    parser.add_argument("--n-epochs", type=int, default=300)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--result-directory", type=Path, required=True)
    parser.add_argument("--cell-output-h5ad", type=Path, required=True)
    parser.add_argument("--gene-output-h5ad", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_expression(adata: ad.AnnData, path: Path) -> None:
    values = adata.X.data if sparse.issparse(adata.X) else np.asarray(adata.X).ravel()
    if values.size == 0 or not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError(f"{path.name}: expression must be finite and nonnegative")
    if not adata.obs_names.is_unique or not adata.var_names.is_unique:
        raise ValueError(f"{path.name}: cell and gene identifiers must be unique")


def read_mapping(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t")
    if frame.shape[1] < 2:
        raise ValueError(f"{path.name}: orthology table requires at least two columns")
    result = frame.iloc[:, :2].astype(str)
    result.columns = ["reference_gene", "query_gene"]
    if result.isna().any().any() or result.eq("").any().any():
        raise ValueError(f"{path.name}: orthology identifiers must be complete")
    return result.drop_duplicates().reset_index(drop=True)


def main() -> int:
    args = parse_args()
    outputs = [args.cell_output_h5ad, args.gene_output_h5ad, args.report]
    if any(path.exists() for path in outputs):
        raise FileExistsError("refusing to overwrite declared outputs")
    if args.result_directory.exists() and any(args.result_directory.iterdir()):
        raise FileExistsError("CAME result directory must be absent or empty")
    if args.reference_species == args.query_species:
        raise ValueError("reference and query species must differ")
    if args.ntop_deg < 1 or args.ntop_deg_nodes < 1 or args.n_epochs < 1:
        raise ValueError("CAME feature and epoch settings must be positive")

    reference = ad.read_h5ad(args.reference_h5ad)
    query = ad.read_h5ad(args.query_h5ad)
    validate_expression(reference, args.reference_h5ad)
    validate_expression(query, args.query_h5ad)
    if (
        args.reference_label_key not in reference.obs
        or reference.obs[args.reference_label_key].isna().any()
    ):
        raise ValueError("reference labels must be complete")
    query_label_key = args.query_label_key
    if query_label_key is not None and (
        query_label_key not in query.obs or query.obs[query_label_key].isna().any()
    ):
        raise ValueError("declared query labels must be complete")

    mapping = read_mapping(args.orthology_tsv)
    mapping_1v1 = read_mapping(args.one_to_one_tsv) if args.one_to_one_tsv else None
    mapping = mapping.loc[
        mapping["reference_gene"].isin(reference.var_names)
        & mapping["query_gene"].isin(query.var_names)
    ].copy()
    if mapping.empty:
        raise ValueError("orthology table has no feature overlap with both datasets")
    if mapping_1v1 is not None:
        mapping_1v1 = mapping_1v1.loc[
            mapping_1v1["reference_gene"].isin(reference.var_names)
            & mapping_1v1["query_gene"].isin(query.var_names)
        ].copy()
        if mapping_1v1.empty:
            raise ValueError("one-to-one table has no feature overlap with both datasets")

    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    args.result_directory.mkdir(parents=True, exist_ok=True)

    came_inputs, _ = pipeline.preprocess_unaligned(
        [reference, query],
        key_class=args.reference_label_key,
        use_scnets=True,
        ntop_deg=args.ntop_deg,
        ntop_deg_nodes=args.ntop_deg_nodes,
        node_source="deg,hvg",
    )
    outputs_native = pipeline.main_for_unaligned(
        **came_inputs,
        df_varmap=mapping,
        df_varmap_1v1=mapping_1v1,
        dataset_names=(args.reference_species, args.query_species),
        key_class1=args.reference_label_key,
        key_class2=query_label_key,
        do_normalize=True,
        keep_non1v1_feats=True,
        n_epochs=args.n_epochs,
        resdir=str(args.result_directory),
        n_pass=100,
        batch_size=args.batch_size,
        plot_results=False,
    )
    required = {"dpair", "h_dict", "predictor"}
    if not required.issubset(outputs_native):
        raise RuntimeError("CAME output contract changed: missing dpair, h_dict or predictor")
    dpair = outputs_native["dpair"]
    h_dict = outputs_native["h_dict"]
    cell_adata = pp.make_adata(
        h_dict["cell"], obs=dpair.obs, assparse=False, ignore_index=True
    )
    gene_adata = pp.make_adata(
        h_dict["gene"], obs=dpair.var.iloc[:, :2], assparse=False, ignore_index=True
    )
    if cell_adata.n_obs != reference.n_obs + query.n_obs:
        raise RuntimeError("scientific validation failed: CAME changed the cell count")
    args.cell_output_h5ad.parent.mkdir(parents=True, exist_ok=True)
    args.gene_output_h5ad.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    cell_adata.write_h5ad(args.cell_output_h5ad)
    gene_adata.write_h5ad(args.gene_output_h5ad)
    payload = {
        "schema_version": 1,
        "passed": True,
        "backend": "CAME",
        "reference_species": args.reference_species,
        "query_species": args.query_species,
        "reference_cells": reference.n_obs,
        "query_cells": query.n_obs,
        "orthology_pairs_used": len(mapping),
        "one_to_one_pairs_used": None if mapping_1v1 is None else len(mapping_1v1),
        "parameters": {
            "ntop_deg": args.ntop_deg,
            "ntop_deg_nodes": args.ntop_deg_nodes,
            "n_epochs": args.n_epochs,
            "batch_size": args.batch_size,
            "seed": args.seed,
        },
        "input_sha256": {
            "reference": sha256(args.reference_h5ad),
            "query": sha256(args.query_h5ad),
            "orthology": sha256(args.orthology_tsv),
            "one_to_one": sha256(args.one_to_one_tsv) if args.one_to_one_tsv else None,
        },
        "scientific_boundary": [
            "CAME is a pairwise graph method that can retain one-to-many and many-to-many gene relations.",
            "Transferred labels remain predictions until held-out query labels or orthogonal evidence validate them.",
            "Cross-condition differential inference must return to species-specific raw counts and biological samples.",
        ],
    }
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if (
        ad.read_h5ad(args.cell_output_h5ad).n_obs != cell_adata.n_obs
        or ad.read_h5ad(args.gene_output_h5ad).n_obs != gene_adata.n_obs
    ):
        raise RuntimeError("CAME outputs failed reload validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
