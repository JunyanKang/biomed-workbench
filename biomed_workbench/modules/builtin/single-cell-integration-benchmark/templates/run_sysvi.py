#!/usr/bin/env python3
"""Run sysVI on pre-normalized shared features with explicit system covariates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import scanpy as sc


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-h5ad", required=True)
    parser.add_argument("--output-h5ad", required=True)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--system-key", required=True)
    parser.add_argument("--categorical-covariates", default="")
    parser.add_argument("--continuous-covariates", default="")
    parser.add_argument("--n-latent", type=int, default=20)
    parser.add_argument("--n-prior-components", type=int, default=10)
    parser.add_argument("--cycle-weight", type=float, default=2.0)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fields(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> int:
    args = arguments()
    from scvi import __version__ as scvi_version, settings
    from scvi.external import SysVI

    source = Path(args.input_h5ad).resolve(strict=True)
    output = Path(args.output_h5ad)
    model_dir = Path(args.model_dir)
    report = Path(args.report)
    for path in (output, model_dir, report):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite: {path.name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    model_dir.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    if args.n_latent < 2 or args.n_prior_components < 2 or args.epochs < 1:
        raise ValueError("latent, prior-component and epoch parameters are invalid")
    if not np.isfinite(args.cycle_weight) or args.cycle_weight < 0:
        raise ValueError("cycle weight must be finite and nonnegative")

    settings.seed = args.seed
    adata = sc.read_h5ad(source)
    if args.system_key not in adata.obs:
        raise ValueError("system key is absent")
    systems = adata.obs[args.system_key].astype(str)
    if systems.isna().any() or systems.nunique() < 2:
        raise ValueError("sysVI requires at least two systems")
    if not np.isfinite(np.asarray(adata.X.data if hasattr(adata.X, "data") else adata.X)).all():
        raise ValueError("model matrix contains nonfinite values")
    categorical = fields(args.categorical_covariates)
    continuous = fields(args.continuous_covariates)
    missing = sorted(set(categorical + continuous) - set(adata.obs))
    if missing:
        raise ValueError(f"covariates are absent: {', '.join(missing)}")
    source_cells = adata.obs_names.copy()
    source_genes = adata.var_names.copy()

    SysVI.setup_anndata(
        adata,
        batch_key=args.system_key,
        categorical_covariate_keys=categorical or None,
        continuous_covariate_keys=continuous or None,
    )
    model = SysVI(
        adata,
        n_latent=args.n_latent,
        n_prior_components=args.n_prior_components,
        embed_categorical_covariates=True,
    )
    model.train(
        max_epochs=args.epochs,
        batch_size=args.batch_size,
        plan_kwargs={"z_distance_cycle_weight": args.cycle_weight},
    )
    latent = model.get_latent_representation()
    if latent.shape != (adata.n_obs, args.n_latent) or not np.isfinite(latent).all():
        raise ValueError("sysVI latent representation is invalid")
    adata.obsm["X_sysVI"] = latent
    adata.uns["sysvi_integration"] = {
        "system_key": args.system_key,
        "categorical_covariates": categorical,
        "continuous_covariates": continuous,
        "cycle_weight": args.cycle_weight,
        "seed": args.seed,
    }
    model.save(model_dir, overwrite=False, save_anndata=False)
    adata.write_h5ad(output)
    reloaded = sc.read_h5ad(output)
    if not source_cells.equals(reloaded.obs_names) or not source_genes.equals(reloaded.var_names):
        raise ValueError("output reload changed cells or features")
    payload = {
        "schema_version": 1,
        "passed": True,
        "source_sha256": sha256(source),
        "output_sha256": sha256(output),
        "cells": adata.n_obs,
        "features": adata.n_vars,
        "systems": int(systems.nunique()),
        "latent_dimensions": int(latent.shape[1]),
        "parameters": vars(args),
        "versions": {"scvi-tools": scvi_version, "scanpy": sc.__version__},
        "preservation": {
            "cell_identity": True,
            "feature_identity": True,
            "output_reloaded": True,
            "labels_not_used": True,
        },
    }
    payload["parameters"].pop("input_h5ad")
    payload["parameters"].pop("output_h5ad")
    payload["parameters"].pop("model_dir")
    payload["parameters"].pop("report")
    report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

