#!/usr/bin/env python3
"""Run graph-linked integration for paired or unpaired RNA and ATAC cells."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import anndata as ad
import networkx as nx
import numpy as np
import pandas as pd
import scanpy as sc
import scglue
from scipy import sparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rna-h5ad", type=Path, required=True)
    parser.add_argument("--atac-h5ad", type=Path, required=True)
    parser.add_argument("--guidance-graph", type=Path, required=True)
    parser.add_argument("--batch-key", required=True)
    parser.add_argument("--counts-layer", default="counts")
    parser.add_argument("--rna-hvg", type=int, default=3000)
    parser.add_argument("--atac-features", type=int, default=10000)
    parser.add_argument("--latent-dimensions", type=int, default=20)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--model-output", type=Path, required=True)
    parser.add_argument("--rna-output", type=Path, required=True)
    parser.add_argument("--atac-output", type=Path, required=True)
    parser.add_argument("--latent-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def validate_counts(adata: ad.AnnData, layer: str, label: str):
    if layer not in adata.layers:
        raise ValueError(f"{label} count layer is absent: {layer}")
    matrix = adata.layers[layer]
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix).ravel()
    if (
        values.size == 0
        or not np.isfinite(values).all()
        or np.any(values < 0)
        or not np.allclose(values, np.rint(values), rtol=0, atol=1e-8)
    ):
        raise ValueError(f"{label} requires finite nonnegative integer counts")
    return matrix


def top_nonconstant_features(matrix, limit: int) -> np.ndarray:
    means = np.asarray(matrix.mean(axis=0)).ravel()
    squares = np.asarray(matrix.power(2).mean(axis=0)).ravel() if sparse.issparse(matrix) else np.mean(np.square(matrix), axis=0)
    variances = np.maximum(squares - np.square(means), 0)
    nonconstant = np.flatnonzero(np.isfinite(variances) & (variances > 0))
    if len(nonconstant) < 100:
        raise ValueError("modality has fewer than 100 nonconstant features")
    return nonconstant[np.argsort(variances[nonconstant])[-min(limit, len(nonconstant)):]]


def prepare_rna(adata: ad.AnnData, args: argparse.Namespace) -> None:
    validate_counts(adata, args.counts_layer, "RNA")
    if args.batch_key not in adata.obs or adata.obs[args.batch_key].isna().any():
        raise ValueError("RNA batch metadata is absent or incomplete")
    work = adata.copy()
    work.X = work.layers[args.counts_layer].copy()
    sc.pp.normalize_total(work, target_sum=1e4)
    sc.pp.log1p(work)
    sc.pp.highly_variable_genes(
        work,
        n_top_genes=min(args.rna_hvg, work.n_vars),
        flavor="seurat",
        batch_key=args.batch_key,
    )
    if int(work.var["highly_variable"].sum()) < 100:
        raise ValueError("RNA highly variable feature selection is inadequate")
    sc.pp.scale(work, max_value=10)
    sc.tl.pca(
        work,
        n_comps=min(100, work.n_obs - 1, int(work.var["highly_variable"].sum()) - 1),
        use_highly_variable=True,
        random_state=args.seed,
    )
    adata.X = work.X
    adata.var["highly_variable"] = work.var["highly_variable"].to_numpy()
    adata.obsm["X_pca"] = work.obsm["X_pca"]


def prepare_atac(adata: ad.AnnData, args: argparse.Namespace) -> None:
    matrix = validate_counts(adata, args.counts_layer, "ATAC")
    if args.batch_key not in adata.obs or adata.obs[args.batch_key].isna().any():
        raise ValueError("ATAC batch metadata is absent or incomplete")
    selected = top_nonconstant_features(matrix, args.atac_features)
    adata.var["highly_variable"] = False
    adata.var.iloc[selected, adata.var.columns.get_loc("highly_variable")] = True
    work = adata[:, adata.var["highly_variable"]].copy()
    work.X = work.layers[args.counts_layer].copy()
    scglue.data.lsi(
        work,
        n_components=min(100, work.n_obs - 1, work.n_vars - 1),
        n_iter=15,
        random_state=args.seed,
    )
    adata.obsm["X_lsi"] = work.obsm["X_lsi"]


def validate_guidance(graph: nx.Graph, rna: ad.AnnData, atac: ad.AnnData) -> nx.Graph:
    if graph.number_of_nodes() == 0 or graph.number_of_edges() == 0:
        raise ValueError("guidance graph must contain nodes and edges")
    features = set(map(str, rna.var_names[rna.var["highly_variable"]])) | set(
        map(str, atac.var_names[atac.var["highly_variable"]])
    )
    graph = graph.subgraph(features).copy()
    if graph.number_of_edges() < 100:
        raise ValueError("guidance graph has fewer than 100 retained regulatory edges")
    scglue.graph.check_graph(graph, [rna, atac])
    return graph


def main() -> int:
    args = parse_args()
    outputs = (
        args.model_output,
        args.rna_output,
        args.atac_output,
        args.latent_output,
        args.report,
    )
    if any(path.exists() for path in outputs):
        raise FileExistsError("refusing to overwrite output")
    if args.latent_dimensions < 2:
        raise ValueError("latent dimensions must be at least two")
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    scglue.models.configure_dataset
    np.random.seed(args.seed)
    rna = ad.read_h5ad(args.rna_h5ad)
    atac = ad.read_h5ad(args.atac_h5ad)
    if not rna.obs_names.is_unique or not atac.obs_names.is_unique:
        raise ValueError("cell identifiers must be unique within each modality")
    prepare_rna(rna, args)
    prepare_atac(atac, args)
    graph = nx.read_graphml(args.guidance_graph)
    graph = validate_guidance(graph, rna, atac)
    scglue.models.configure_dataset(
        rna,
        "NB",
        use_highly_variable=True,
        use_layer=args.counts_layer,
        use_rep="X_pca",
        use_batch=args.batch_key,
    )
    scglue.models.configure_dataset(
        atac,
        "NB",
        use_highly_variable=True,
        use_layer=args.counts_layer,
        use_rep="X_lsi",
        use_batch=args.batch_key,
    )
    model = scglue.models.fit_SCGLUE(
        {"rna": rna, "atac": atac},
        graph,
        init_kws={"latent_dim": args.latent_dimensions, "random_seed": args.seed},
        compile_kws={"lam_graph": 0.02},
    )
    rna_latent = np.asarray(model.encode_data("rna", rna))
    atac_latent = np.asarray(model.encode_data("atac", atac))
    if (
        rna_latent.shape != (rna.n_obs, args.latent_dimensions)
        or atac_latent.shape != (atac.n_obs, args.latent_dimensions)
        or not np.isfinite(rna_latent).all()
        or not np.isfinite(atac_latent).all()
    ):
        raise RuntimeError("scientific validation failed: invalid GLUE latent output")
    rna.obsm["X_glue"] = rna_latent
    atac.obsm["X_glue"] = atac_latent
    model.save(args.model_output)
    rna.write_h5ad(args.rna_output)
    atac.write_h5ad(args.atac_output)
    latent_columns = [f"latent_{index + 1}" for index in range(args.latent_dimensions)]
    rna_frame = pd.DataFrame(rna_latent, columns=latent_columns)
    rna_frame.insert(0, "original_cell_id", rna.obs_names.astype(str))
    rna_frame.insert(0, "modality", "rna")
    rna_frame.insert(0, "cell_id", "rna::" + rna.obs_names.astype(str))
    atac_frame = pd.DataFrame(atac_latent, columns=latent_columns)
    atac_frame.insert(0, "original_cell_id", atac.obs_names.astype(str))
    atac_frame.insert(0, "modality", "atac")
    atac_frame.insert(0, "cell_id", "atac::" + atac.obs_names.astype(str))
    latent = pd.concat([rna_frame, atac_frame], axis=0, ignore_index=True)
    latent.to_csv(args.latent_output, sep="\t", index=False)
    shared_cells = set(map(str, rna.obs_names)) & set(map(str, atac.obs_names))
    report = {
        "schema_version": 1,
        "passed": True,
        "backend": "scglue",
        "scglue_version": scglue.__version__,
        "input_sha256": {
            "rna": sha256(args.rna_h5ad),
            "atac": sha256(args.atac_h5ad),
            "guidance_graph": sha256(args.guidance_graph),
        },
        "cells": {
            "rna": rna.n_obs,
            "atac": atac.n_obs,
            "paired_identity_overlap": len(shared_cells),
        },
        "features": {
            "rna_hvg": int(rna.var["highly_variable"].sum()),
            "atac_selected": int(atac.var["highly_variable"].sum()),
            "guidance_nodes": graph.number_of_nodes(),
            "guidance_edges": graph.number_of_edges(),
        },
        "parameters": {
            "latent_dimensions": args.latent_dimensions,
            "lam_graph": 0.02,
            "seed": args.seed,
        },
        "scientific_boundary": [
            "The guidance graph is a declared regulatory prior, not proof of regulation.",
            "GLUE supports unpaired modalities; apparent cross-modal neighbors require paired or external validation.",
            "Integrated embeddings are forbidden as confirmatory differential-expression input.",
        ],
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if len(pd.read_csv(args.latent_output, sep="\t")) != rna.n_obs + atac.n_obs:
        raise RuntimeError("serialized GLUE latent output failed reload validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
