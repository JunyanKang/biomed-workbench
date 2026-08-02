#!/usr/bin/env python3
"""Native SpaGCN or STAGATE domain arm with exact-K label-blind clustering."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture


def validate_input(adata: ad.AnnData, spatial_key: str, clusters: int) -> None:
    """Validate spatial geometry and the requested label-blind partition."""
    if spatial_key not in adata.obsm or clusters < 2 or clusters >= adata.n_obs:
        raise ValueError("invalid coordinates or cluster count")
    coords = np.asarray(adata.obsm[spatial_key], dtype=float)
    if coords.shape != (adata.n_obs, 2) or not np.isfinite(coords).all():
        raise ValueError("spatial coordinates must be finite observations by two")


def package_version(distribution: str) -> str:
    """Return exact method version provenance."""
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "source-checkout"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=("spagcn", "stagate"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clusters", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--spatial-key", default="spatial")
    parser.add_argument("--radius", type=float, default=150.0)
    parser.add_argument("--epochs", type=int, default=1000)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    adata = ad.read_h5ad(args.input)
    validate_input(adata, args.spatial_key, args.clusters)
    adata.obsm["spatial"] = np.asarray(adata.obsm[args.spatial_key], dtype=float)
    if args.method == "stagate":
        import STAGATE_pyG as STAGATE
        STAGATE.Cal_Spatial_Net(adata, rad_cutoff=args.radius)
        model = STAGATE.train_STAGATE(adata, random_seed=args.seed, n_epochs=args.epochs)
        embedding = np.asarray(model.obsm["STAGATE"])
    else:
        import SpaGCN
        x, y = adata.obsm["spatial"][:, 0], adata.obsm["spatial"][:, 1]
        adjacency = SpaGCN.calculate_adj_matrix(x=x, y=y, histology=False)
        model = SpaGCN.SpaGCN()
        model.set_l(1.0)
        model.train(adata, adjacency, init_spa=True, init="louvain", res=0.5, tol=5e-3, lr=0.05, max_epochs=args.epochs)
        prediction, probabilities = model.predict()
        embedding = np.asarray(probabilities)
    labels = GaussianMixture(n_components=args.clusters, covariance_type="full", random_state=args.seed).fit_predict(embedding)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"observation_id": adata.obs_names.astype(str), "domain": labels.astype(str)}).to_csv(args.output, sep="\t", index=False)
    metadata = {
        "method": args.method,
        "method_version": package_version("SpaGCN" if args.method == "spagcn" else "STAGATE-pyG"),
        "clusters": args.clusters,
        "seed": args.seed,
        "observations": adata.n_obs,
        "finite_embedding": bool(np.isfinite(embedding).all()),
    }
    args.output.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
