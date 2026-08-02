#!/usr/bin/env python3
"""Run totalVI or MultiVI with explicit paired, unpaired and missing-modality contracts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import anndata as ad
import mudata
import numpy as np
import pandas as pd
import scvi
from scipy import sparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("totalvi", "multivi"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--batch-key", required=True)
    parser.add_argument("--counts-layer")
    parser.add_argument("--protein-obsm-key", default="protein_expression")
    parser.add_argument("--rna-modality", default="rna")
    parser.add_argument("--atac-modality", default="atac")
    parser.add_argument("--latent-dimensions", type=int, default=20)
    parser.add_argument("--max-epochs", type=int, default=400)
    parser.add_argument("--accelerator", choices=("cpu", "gpu"), default="cpu")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--model-output", type=Path, required=True)
    parser.add_argument("--integrated-output", type=Path, required=True)
    parser.add_argument("--latent-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def digest_directory(path: Path) -> str:
    value = hashlib.sha256()
    for item in sorted(entry for entry in path.rglob("*") if entry.is_file()):
        value.update(item.relative_to(path).as_posix().encode())
        value.update(b"\0")
        value.update(bytes.fromhex(digest(item)))
    return value.hexdigest()


def count_values(matrix) -> np.ndarray:
    return matrix.data if sparse.issparse(matrix) else np.asarray(matrix).ravel()


def validate_counts(matrix, label: str) -> None:
    values = count_values(matrix)
    if (
        values.size == 0
        or not np.isfinite(values).all()
        or np.any(values < 0)
        or not np.allclose(values, np.rint(values), rtol=0, atol=1e-8)
    ):
        raise ValueError(f"{label} requires finite nonnegative integer counts")


def selected_matrix(adata: ad.AnnData, layer: str | None, label: str):
    if layer is not None:
        if layer not in adata.layers:
            raise ValueError(f"{label} count layer is absent: {layer}")
        matrix = adata.layers[layer]
    else:
        matrix = adata.X
    validate_counts(matrix, label)
    return matrix


def prepare_outputs(args: argparse.Namespace) -> None:
    outputs = (
        args.model_output,
        args.integrated_output,
        args.latent_output,
        args.report,
    )
    if any(path.exists() for path in outputs):
        raise FileExistsError("refusing to overwrite output")
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)


def run_totalvi(args: argparse.Namespace):
    adata = ad.read_h5ad(args.input)
    selected_matrix(adata, args.counts_layer, "RNA")
    if args.batch_key not in adata.obs or adata.obs[args.batch_key].isna().any():
        raise ValueError("complete batch metadata is required")
    if args.protein_obsm_key not in adata.obsm:
        raise ValueError("declared protein expression matrix is absent")
    protein = adata.obsm[args.protein_obsm_key]
    protein_values = protein.to_numpy() if isinstance(protein, pd.DataFrame) else np.asarray(protein)
    if protein_values.ndim != 2 or protein_values.shape[0] != adata.n_obs:
        raise ValueError("protein matrix must be cell by protein and match RNA cells")
    validate_counts(protein_values, "protein")
    if protein_values.shape[1] < 2:
        raise ValueError("totalVI requires at least two protein features")
    source_cells = adata.obs_names.copy()
    scvi.model.TOTALVI.setup_anndata(
        adata,
        layer=args.counts_layer,
        batch_key=args.batch_key,
        protein_expression_obsm_key=args.protein_obsm_key,
    )
    model = scvi.model.TOTALVI(adata, n_latent=args.latent_dimensions)
    model.train(
        max_epochs=args.max_epochs,
        accelerator=args.accelerator,
        devices=1,
    )
    latent = np.asarray(model.get_latent_representation())
    if latent.shape != (adata.n_obs, args.latent_dimensions):
        raise RuntimeError("scientific validation failed: unexpected totalVI latent dimensions")
    if not np.isfinite(latent).all():
        raise RuntimeError("scientific validation failed: nonfinite totalVI latent values")
    adata.obsm["X_totalvi"] = latent
    model.save(args.model_output, save_anndata=True)
    adata.write_h5ad(args.integrated_output)
    return (
        model,
        adata,
        latent,
        source_cells,
        {
            "modalities": ["rna", "protein"],
            "paired_cells": int(adata.n_obs),
            "rna_only_cells": 0,
            "secondary_only_cells": 0,
            "output_semantics": "joint RNA-protein latent representation",
        },
    )


def run_multivi(args: argparse.Namespace):
    mdata = mudata.read_h5mu(args.input)
    if args.rna_modality not in mdata.mod or args.atac_modality not in mdata.mod:
        raise ValueError("MultiVI input requires declared RNA and ATAC modalities")
    rna = mdata.mod[args.rna_modality]
    atac = mdata.mod[args.atac_modality]
    rna_counts = selected_matrix(rna, args.counts_layer, "RNA")
    atac_counts = selected_matrix(atac, args.counts_layer, "ATAC")
    if args.counts_layer is not None:
        rna.X = rna_counts.copy()
        atac.X = atac_counts.copy()
    if (
        args.batch_key not in rna.obs
        or rna.obs[args.batch_key].isna().any()
        or args.batch_key not in mdata.obs
        or mdata.obs[args.batch_key].isna().any()
    ):
        raise ValueError("complete batch metadata must exist on the union cell axis and RNA modality")
    if not rna.obs_names.equals(mdata.obs_names) or not atac.obs_names.equals(mdata.obs_names):
        raise ValueError(
            "MultiVI MuData must retain the union cell axis in both modalities; "
            "encode absent measurements as all-zero modality rows"
        )
    if rna.n_vars < 100 or atac.n_vars < 100:
        raise ValueError("MultiVI requires substantive shared RNA features and a shared ATAC peak set")
    rna_present = np.asarray(rna_counts.sum(axis=1)).ravel() > 0
    atac_present = np.asarray(atac_counts.sum(axis=1)).ravel() > 0
    if np.any(~rna_present & ~atac_present):
        raise ValueError("cells with neither RNA nor ATAC measurements are invalid")
    rna_cells = set(map(str, rna.obs_names[rna_present]))
    atac_cells = set(map(str, atac.obs_names[atac_present]))
    paired = rna_cells & atac_cells
    if not paired:
        raise ValueError("mosaic MultiVI requires paired anchor cells")
    source_cells = mdata.obs_names.copy()
    scvi.model.MULTIVI.setup_mudata(
        mdata,
        batch_key=args.batch_key,
        modalities={
            "rna_layer": args.rna_modality,
            "atac_layer": args.atac_modality,
            "batch_key": args.rna_modality,
        },
    )
    model = scvi.model.MULTIVI(
        mdata,
        n_latent=args.latent_dimensions,
        fully_paired=(rna_cells == atac_cells),
    )
    model.train(
        max_epochs=args.max_epochs,
        accelerator=args.accelerator,
        devices=1,
    )
    latent = np.asarray(model.get_latent_representation())
    if latent.shape != (mdata.n_obs, args.latent_dimensions):
        raise RuntimeError("scientific validation failed: unexpected MultiVI latent dimensions")
    if not np.isfinite(latent).all():
        raise RuntimeError("scientific validation failed: nonfinite MultiVI latent values")
    mdata.obsm["X_multivi"] = latent
    model.save(args.model_output, save_anndata=True)
    mdata.write_h5mu(args.integrated_output)
    return (
        model,
        mdata,
        latent,
        source_cells,
        {
            "modalities": ["rna", "atac"],
            "paired_cells": len(paired),
            "rna_only_cells": len(rna_cells - atac_cells),
            "secondary_only_cells": len(atac_cells - rna_cells),
            "shared_peak_contract": "All ATAC datasets must use one declared peak universe.",
            "output_semantics": "joint RNA-ATAC latent representation with mosaic missingness retained",
        },
    )


def main() -> int:
    args = parse_args()
    if args.latent_dimensions < 2 or args.max_epochs < 20:
        raise ValueError("latent dimensions or training epochs are too small")
    prepare_outputs(args)
    scvi.settings.seed = args.seed
    if args.backend == "totalvi":
        model, integrated, latent, source_cells, design = run_totalvi(args)
    else:
        model, integrated, latent, source_cells, design = run_multivi(args)
    current_cells = integrated.obs_names
    if not pd.Index(current_cells).equals(pd.Index(source_cells)):
        raise RuntimeError("scientific validation failed: integration changed or reordered cells")
    latent_frame = pd.DataFrame(
        latent,
        index=current_cells,
        columns=[f"latent_{index + 1}" for index in range(latent.shape[1])],
    )
    latent_frame.insert(0, "cell_id", latent_frame.index)
    latent_frame.to_csv(args.latent_output, sep="\t", index=False)
    report = {
        "schema_version": 1,
        "passed": True,
        "backend": args.backend,
        "scvi_tools_version": scvi.__version__,
        "input_sha256": digest(args.input),
        "cells": len(current_cells),
        "latent_dimensions": latent.shape[1],
        "batch_key": args.batch_key,
        "batches": int(integrated.obs[args.batch_key].nunique()),
        "design": design,
        "parameters": {
            "max_epochs": args.max_epochs,
            "accelerator": args.accelerator,
            "seed": args.seed,
        },
        "runtime": {
            "anndata": importlib.metadata.version("anndata"),
            "mudata": importlib.metadata.version("mudata"),
        },
        "outputs": {
            "model_sha256": digest_directory(args.model_output),
            "integrated_sha256": digest(args.integrated_output),
            "latent_sha256": digest(args.latent_output),
        },
        "interpretation_scope": [
            "The latent representation is for integration, visualization and mapping, not confirmatory differential expression.",
            "Missing modalities are modelled as missing and are never silently converted into observed measurements.",
            "Differential inference returns to immutable raw counts with sample or donor as the statistical unit.",
        ],
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    reloaded = pd.read_csv(args.latent_output, sep="\t")
    if len(reloaded) != len(current_cells) or reloaded.isna().any().any():
        raise RuntimeError("serialized latent output failed reload validation")
    if args.backend == "totalvi":
        integrated_reload = ad.read_h5ad(args.integrated_output)
        model_reload = scvi.model.TOTALVI.load(args.model_output)
    else:
        integrated_reload = mudata.read_h5mu(args.integrated_output)
        model_reload = scvi.model.MULTIVI.load(args.model_output)
    if not pd.Index(integrated_reload.obs_names).equals(pd.Index(current_cells)):
        raise RuntimeError("integrated output failed cell-order reload validation")
    latent_reload = np.asarray(model_reload.get_latent_representation())
    if latent_reload.shape != latent.shape or not np.isfinite(latent_reload).all():
        raise RuntimeError("saved model failed latent-representation reload validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
