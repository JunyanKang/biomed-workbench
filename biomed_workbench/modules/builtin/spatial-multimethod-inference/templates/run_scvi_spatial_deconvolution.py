#!/usr/bin/env python3
"""Run Stereoscope or DestVI with count-backed single-cell and spatial data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import scvi
from scipy import sparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("stereoscope", "destvi"), required=True)
    parser.add_argument("--spatial-h5ad", type=Path, required=True)
    parser.add_argument("--reference-h5ad", type=Path, required=True)
    parser.add_argument("--cell-type-key", required=True)
    parser.add_argument("--fine-label-key")
    parser.add_argument("--reference-batch-key")
    parser.add_argument("--counts-layer")
    parser.add_argument("--minimum-shared-genes", type=int, default=500)
    parser.add_argument("--reference-epochs", type=int, default=300)
    parser.add_argument("--spatial-epochs", type=int, default=2500)
    parser.add_argument("--accelerator", choices=("cpu", "gpu"), default="cpu")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--proportions-output", type=Path, required=True)
    parser.add_argument("--reference-model-output", type=Path, required=True)
    parser.add_argument("--spatial-model-output", type=Path, required=True)
    parser.add_argument("--spatial-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_counts(adata: ad.AnnData, layer: str | None, name: str) -> None:
    if layer is not None and layer not in adata.layers:
        raise ValueError(f"{name} count layer is absent: {layer}")
    matrix = adata.layers[layer] if layer else adata.X
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix).ravel()
    if (
        values.size == 0
        or not np.isfinite(values).all()
        or np.any(values < 0)
        or not np.allclose(values, np.rint(values), rtol=0, atol=1e-8)
    ):
        raise ValueError(f"{name} requires finite nonnegative integer counts")


def prepare_inputs(args: argparse.Namespace) -> tuple[ad.AnnData, ad.AnnData, list[str]]:
    spatial = ad.read_h5ad(args.spatial_h5ad)
    reference = ad.read_h5ad(args.reference_h5ad)
    validate_counts(spatial, args.counts_layer, "spatial data")
    validate_counts(reference, args.counts_layer, "single-cell reference")
    if args.cell_type_key not in reference.obs:
        raise ValueError("cell-type metadata is absent from the reference")
    labels = reference.obs[args.cell_type_key]
    if labels.isna().any() or labels.astype(str).str.strip().eq("").any() or labels.nunique() < 2:
        raise ValueError("reference requires complete labels for at least two cell types")
    shared = sorted(set(spatial.var_names) & set(reference.var_names))
    if len(shared) < args.minimum_shared_genes:
        raise ValueError(
            f"only {len(shared)} shared genes; require at least {args.minimum_shared_genes}"
        )
    spatial = spatial[:, shared].copy()
    reference = reference[:, shared].copy()
    return spatial, reference, shared


def train_stereoscope(
    spatial: ad.AnnData,
    reference: ad.AnnData,
    args: argparse.Namespace,
) -> tuple[object, object, pd.DataFrame, dict[str, object]]:
    from scvi.external import RNAStereoscope, SpatialStereoscope

    RNAStereoscope.setup_anndata(
        reference,
        layer=args.counts_layer,
        labels_key=args.cell_type_key,
    )
    rna_model = RNAStereoscope(reference)
    rna_model.train(
        max_epochs=args.reference_epochs,
        accelerator=args.accelerator,
        devices=1,
    )
    SpatialStereoscope.setup_anndata(spatial, layer=args.counts_layer)
    spatial_model = SpatialStereoscope.from_rna_model(
        spatial,
        rna_model,
        prior_weight="n_obs",
    )
    spatial_model.train(
        max_epochs=args.spatial_epochs,
        accelerator=args.accelerator,
        devices=1,
    )
    proportions = spatial_model.get_proportions(keep_noise=False)
    if not isinstance(proportions, pd.DataFrame):
        proportions = pd.DataFrame(proportions, index=spatial.obs_names)
    diagnostics = {
        "output_semantics": "cell-type proportions per spatial location",
        "prior_weight": "n_obs",
        "continuous_within_type_state": False,
    }
    return rna_model, spatial_model, proportions, diagnostics


def train_destvi(
    spatial: ad.AnnData,
    reference: ad.AnnData,
    args: argparse.Namespace,
) -> tuple[object, object, pd.DataFrame, dict[str, object]]:
    from scvi.model import CondSCVI, DestVI

    setup = {
        "layer": args.counts_layer,
        "labels_key": args.cell_type_key,
    }
    if args.reference_batch_key:
        if args.reference_batch_key not in reference.obs:
            raise ValueError("reference batch metadata is absent")
        setup["batch_key"] = args.reference_batch_key
    if args.fine_label_key:
        if args.fine_label_key not in reference.obs:
            raise ValueError("fine-label metadata is absent")
        setup["fine_labels_key"] = args.fine_label_key
    CondSCVI.setup_anndata(reference, **setup)
    rna_model = CondSCVI(reference, weight_obs=False)
    rna_model.train(
        max_epochs=args.reference_epochs,
        accelerator=args.accelerator,
        devices=1,
    )
    spatial_model = DestVI.from_rna_model(
        spatial,
        rna_model,
        anndata_setup_kwargs={"layer": args.counts_layer},
    )
    spatial_model.train(
        max_epochs=args.spatial_epochs,
        accelerator=args.accelerator,
        devices=1,
    )
    proportions = spatial_model.get_proportions()
    if not isinstance(proportions, pd.DataFrame):
        proportions = pd.DataFrame(proportions, index=spatial.obs_names)
    for cell_type, gamma in spatial_model.get_gamma().items():
        spatial.obsm[f"destvi_gamma::{cell_type}"] = np.asarray(gamma)
    diagnostics = {
        "output_semantics": "cell-type proportions plus within-cell-type latent states",
        "continuous_within_type_state": True,
        "important_assumption": (
            "Within each spatial location, each declared cell type is represented by one "
            "continuous state; split labels when biologically incompatible states may coexist."
        ),
    }
    return rna_model, spatial_model, proportions, diagnostics


def validate_output(proportions: pd.DataFrame, spatial: ad.AnnData) -> None:
    values = proportions.to_numpy(dtype=float)
    if proportions.shape[0] != spatial.n_obs or proportions.shape[1] < 2:
        raise RuntimeError("scientific validation failed: invalid proportion dimensions")
    if not proportions.index.equals(pd.Index(spatial.obs_names)):
        raise RuntimeError("scientific validation failed: spatial identifiers changed")
    if not np.isfinite(values).all() or np.any(values < 0):
        raise RuntimeError("scientific validation failed: proportions are nonfinite or negative")
    row_sums = values.sum(axis=1)
    if np.any(row_sums <= 0) or not np.allclose(row_sums, 1, atol=5e-3):
        raise RuntimeError("scientific validation failed: proportions do not sum to one")


def main() -> int:
    args = parse_args()
    outputs = (
        args.proportions_output,
        args.reference_model_output,
        args.spatial_model_output,
        args.spatial_output,
        args.report,
    )
    if any(path.exists() for path in outputs):
        raise FileExistsError("refusing to overwrite output")
    scvi.settings.seed = args.seed
    spatial, reference, shared = prepare_inputs(args)
    if args.backend == "stereoscope":
        rna_model, spatial_model, proportions, diagnostics = train_stereoscope(
            spatial, reference, args
        )
    else:
        rna_model, spatial_model, proportions, diagnostics = train_destvi(
            spatial, reference, args
        )
    proportions.index = spatial.obs_names
    validate_output(proportions, spatial)
    spatial.obsm[f"{args.backend}_proportions"] = proportions
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    rna_model.save(args.reference_model_output, save_anndata=True)
    spatial_model.save(args.spatial_model_output, save_anndata=True)
    spatial.write_h5ad(args.spatial_output)
    proportions.insert(0, "location_id", proportions.index)
    proportions.to_csv(args.proportions_output, sep="\t", index=False)
    report = {
        "schema_version": 1,
        "passed": True,
        "backend": args.backend,
        "scvi_tools_version": scvi.__version__,
        "spatial_sha256": sha256(args.spatial_h5ad),
        "reference_sha256": sha256(args.reference_h5ad),
        "shared_genes": len(shared),
        "locations": spatial.n_obs,
        "reference_cells": reference.n_obs,
        "cell_types": int(reference.obs[args.cell_type_key].nunique()),
        "parameters": {
            "reference_epochs": args.reference_epochs,
            "spatial_epochs": args.spatial_epochs,
            "accelerator": args.accelerator,
            "seed": args.seed,
        },
        "diagnostics": diagnostics,
        "claim_boundary": (
            "Outputs are reference-defined model estimates. Validate held-out genes, reference "
            "subsampling, residuals and biological-sample reproducibility before interpretation."
        ),
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    reloaded = pd.read_csv(args.proportions_output, sep="\t")
    if len(reloaded) != spatial.n_obs or reloaded.isna().any().any():
        raise RuntimeError("serialized proportion output failed reload validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
