#!/usr/bin/env python3
"""Map query cells to a frozen SCVI or SCANVI reference with scArches."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import scanpy as sc


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-h5ad", required=True)
    parser.add_argument("--reference-model", required=True)
    parser.add_argument("--output-h5ad", required=True)
    parser.add_argument("--query-model-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--model", choices=("scvi", "scanvi"), required=True)
    parser.add_argument("--latent-key", default="X_scArches")
    parser.add_argument("--prediction-key", default="scarches_suggested_label")
    parser.add_argument("--unknown-label", default="Unknown")
    parser.add_argument("--minimum-feature-overlap", type=float, default=0.80)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = arguments()
    import scvi

    query_path = Path(args.query_h5ad).resolve(strict=True)
    reference_model = Path(args.reference_model).resolve(strict=True)
    output = Path(args.output_h5ad)
    query_model_dir = Path(args.query_model_dir)
    report = Path(args.report)
    for path in (output, query_model_dir, report):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite: {path.name}")
    if not 0 < args.minimum_feature_overlap <= 1 or args.epochs < 1:
        raise ValueError("feature-overlap and epoch parameters are invalid")
    if args.weight_decay != 0:
        raise ValueError("scArches query mapping requires weight_decay=0 to protect the reference")

    scvi.settings.seed = args.seed
    query = sc.read_h5ad(query_path)
    if not query.obs_names.is_unique or not query.var_names.is_unique:
        raise ValueError("query cells and features must be unique")
    source_cells = query.obs_names.copy()
    source_features = query.var_names.copy()
    model_class = scvi.model.SCVI if args.model == "scvi" else scvi.model.SCANVI
    registry = model_class.load_registry(reference_model)
    reference_features = list(registry.get("field_registries", {}).get("X", {}).get("state_registry", {}).get("column_names", []))
    if reference_features:
        overlap = len(set(reference_features) & set(query.var_names)) / len(reference_features)
        if overlap < args.minimum_feature_overlap:
            raise ValueError(f"reference feature overlap is below threshold: {overlap:.3f}")
    else:
        overlap = None

    model_class.prepare_query_anndata(query, reference_model)
    query_model = model_class.load_query_data(query, reference_model)
    query_model.train(
        max_epochs=args.epochs,
        plan_kwargs={"weight_decay": args.weight_decay},
        check_val_every_n_epoch=max(1, min(10, args.epochs)),
    )
    latent = query_model.get_latent_representation()
    if latent.shape[0] != query.n_obs or not np.isfinite(latent).all():
        raise ValueError("query latent representation is invalid")
    query.obsm[args.latent_key] = latent
    if args.model == "scanvi":
        predictions = np.asarray(query_model.predict(), dtype=str)
        if len(predictions) != query.n_obs:
            raise ValueError("scANVI prediction length differs from query cells")
        query.obs[args.prediction_key] = predictions
    else:
        query.obs[args.prediction_key] = args.unknown_label
    query.uns["scarches_mapping"] = {
        "model": args.model,
        "minimum_feature_overlap": args.minimum_feature_overlap,
        "observed_feature_overlap": overlap,
        "epochs": args.epochs,
        "weight_decay": args.weight_decay,
        "seed": args.seed,
    }
    query_model.save(query_model_dir, overwrite=False, save_anndata=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    query.write_h5ad(output)
    reloaded = sc.read_h5ad(output)
    if not source_cells.equals(reloaded.obs_names):
        raise ValueError("output reload changed query cells")
    original_present = source_features.intersection(reloaded.var_names)
    if len(original_present) != len(source_features):
        raise ValueError("query preparation lost original query features")
    payload = {
        "schema_version": 1,
        "passed": True,
        "query_sha256": sha256(query_path),
        "output_sha256": sha256(output),
        "cells": query.n_obs,
        "original_query_features": len(source_features),
        "reference_feature_overlap": overlap,
        "model": args.model,
        "versions": {"scvi-tools": scvi.__version__, "scanpy": sc.__version__},
        "preservation": {
            "reference_model_not_overwritten": True,
            "query_cells_preserved": True,
            "original_query_features_preserved": True,
            "output_reloaded": True,
            "predictions_are_suggestions": True,
        },
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

