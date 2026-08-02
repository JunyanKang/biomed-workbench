#!/usr/bin/env python3
"""Run a declared spatial reference-mapping backend and normalize its evidence.

Python backends (cell2location, Tangram) run here.  RCTD and SPOTlight are
delegated to the companion R template so their native models are preserved.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse


class TangramDensityPrior(np.ndarray):
    """Numeric ndarray compatible with Tangram 1.0.4's string dispatch.

    Tangram 1.0.4 documents ndarray priors but compares the supplied object to
    two string sentinels without first checking its type.  Modern NumPy returns
    an elementwise boolean array for that comparison.  This view changes only
    comparisons against those dispatch strings; its numeric buffer is intact.
    """

    def __eq__(self, other):
        if isinstance(other, str):
            return False
        return super().__eq__(other)

    def __str__(self) -> str:
        return "customized-rna-count-based"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()


def require_expression(adata: ad.AnnData, layer: str | None, *, integer_counts: bool):
    matrix = adata.layers[layer] if layer else adata.X
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix).ravel()
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("spatial reference mapping requires finite nonnegative expression")
    if integer_counts and not np.allclose(values, np.rint(values)):
        raise ValueError("cell2location requires finite nonnegative integer counts")
    return matrix


def shared_gene_subset(spatial: ad.AnnData, reference: ad.AnnData, minimum: int) -> list[str]:
    shared = spatial.var_names.intersection(reference.var_names)
    if len(shared) < minimum:
        raise ValueError(f"only {len(shared)} shared genes; require at least {minimum}")
    return list(shared)


def tangram_backend(spatial, reference, cell_type_key: str, genes: list[str], device: str, epochs: int, seed: int):
    import torch
    import tangram as tg
    torch.manual_seed(seed)
    reference = reference[:, genes].copy()
    spatial = spatial[:, genes].copy()
    tg.pp_adatas(reference, spatial, genes=genes)
    # Tangram documents ndarray density priors as a public API.  Passing the
    # equivalent explicit array avoids pandas-Series coercion differences in
    # newer PyTorch releases while retaining the official RNA-count prior.
    density_prior = np.asarray(spatial.obs["rna_count_based_density"], dtype=np.float32)
    if not np.isfinite(density_prior).all() or (density_prior < 0).any():
        raise ValueError("Tangram RNA-count density prior is invalid")
    density_prior = (density_prior / density_prior.sum()).view(TangramDensityPrior)
    mapping = tg.map_cells_to_space(
        reference, spatial, mode="clusters", cluster_label=cell_type_key,
        density_prior=density_prior, num_epochs=epochs, device=device,
        random_state=seed, verbose=False,
    )
    tg.project_cell_annotations(mapping, spatial, annotation=cell_type_key)
    proportions = pd.DataFrame(spatial.obsm["tangram_ct_pred"], index=spatial.obs_names)
    proportions = proportions.div(proportions.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    diagnostics = {
        "mapping_mode": "clusters",
        "density_prior": "rna_count_based_explicit_array",
        "mapping_source_units": int(mapping.n_obs),
        "mapping_locations": int(mapping.n_vars),
        "training_history": mapping.uns.get("training_history", {}),
    }
    return proportions, mapping, diagnostics


def cell2location_backend(spatial, reference, cell_type_key: str, batch_key: str | None, genes: list[str], epochs: int, posterior_samples: int, device: str, seed: int):
    import torch
    import cell2location
    from cell2location.models import Cell2location, RegressionModel
    torch.manual_seed(seed)
    reference = reference[:, genes].copy()
    spatial = spatial[:, genes].copy()
    RegressionModel.setup_anndata(reference, batch_key=batch_key, labels_key=cell_type_key)
    reg = RegressionModel(reference)
    reg.train(max_epochs=epochs, batch_size=2500, train_size=1, lr=0.002, use_gpu=device != "cpu")
    reference = reg.export_posterior(reference, sample_kwargs={"num_samples": posterior_samples, "batch_size": 2500, "use_gpu": device != "cpu"})
    prefix = "means_per_cluster_mu_fg_"
    signatures = reference.var[[c for c in reference.var.columns if c.startswith(prefix)]].copy()
    signatures.columns = [c[len(prefix):] for c in signatures.columns]
    Cell2location.setup_anndata(spatial)
    model = Cell2location(spatial, cell_state_df=signatures, N_cells_per_location=30, detection_alpha=20)
    model.train(max_epochs=epochs, batch_size=None, train_size=1, use_gpu=device != "cpu")
    spatial = model.export_posterior(spatial, sample_kwargs={"num_samples": posterior_samples, "batch_size": spatial.n_obs, "use_gpu": device != "cpu"})
    key = "q05_cell_abundance_w_sf"
    abundance = pd.DataFrame(spatial.obsm[key], index=spatial.obs_names, columns=signatures.columns)
    diagnostics = {"reference_signatures": signatures, "posterior_key": key, "cell2location_version": cell2location.__version__}
    return abundance, spatial, diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("cell2location", "tangram"), required=True)
    parser.add_argument("--spatial-h5ad", type=Path, required=True)
    parser.add_argument("--reference-h5ad", type=Path, required=True)
    parser.add_argument("--cell-type-key", required=True)
    parser.add_argument("--reference-batch-key")
    parser.add_argument("--counts-layer")
    parser.add_argument("--minimum-shared-genes", type=int, default=500)
    parser.add_argument("--epochs", type=int, default=30000)
    parser.add_argument("--posterior-samples", type=int, default=1000)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--abundance-output", type=Path, required=True)
    parser.add_argument("--model-output", type=Path, required=True)
    parser.add_argument("--diagnostics-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    outputs = (args.abundance_output, args.model_output, args.diagnostics_output, args.report)
    if any(p.exists() for p in outputs):
        raise FileExistsError("refusing to overwrite output")
    spatial = ad.read_h5ad(args.spatial_h5ad)
    reference = ad.read_h5ad(args.reference_h5ad)
    # Tangram's official example data contain normalized nonnegative expression.
    # Count-model backends retain the stricter integer-count requirement.
    integer_counts = args.backend == "cell2location"
    require_expression(spatial, args.counts_layer, integer_counts=integer_counts)
    require_expression(reference, args.counts_layer, integer_counts=integer_counts)
    if args.cell_type_key not in reference.obs or reference.obs[args.cell_type_key].isna().any():
        raise ValueError("complete reference cell-type labels are required")
    if reference.obs[args.cell_type_key].nunique() < 2:
        raise ValueError("reference requires at least two cell types")
    genes = shared_gene_subset(spatial, reference, args.minimum_shared_genes)
    if args.backend == "tangram":
        abundance, model, diagnostics = tangram_backend(spatial, reference, args.cell_type_key, genes, args.device, args.epochs, args.seed)
    else:
        abundance, model, diagnostics = cell2location_backend(spatial, reference, args.cell_type_key, args.reference_batch_key, genes, args.epochs, args.posterior_samples, args.device, args.seed)
    abundance.index.name = "location_id"
    abundance.insert(0, "location_id", abundance.index)
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    abundance.to_csv(args.abundance_output, sep="\t", index=False)
    model.write_h5ad(args.model_output)
    serializable = {k: v for k, v in diagnostics.items() if not isinstance(v, pd.DataFrame)}
    args.diagnostics_output.write_text(json.dumps(serializable, indent=2, default=str) + "\n")
    reloaded = pd.read_csv(args.abundance_output, sep="\t")
    reloaded_model = ad.read_h5ad(args.model_output)
    if len(reloaded) != spatial.n_obs or reloaded.isna().any().any():
        raise RuntimeError("abundance output reload failed")
    if args.backend == "tangram" and reloaded_model.n_vars != spatial.n_obs:
        raise RuntimeError("Tangram mapping model does not retain every spatial location")
    abundance_values = reloaded.drop(columns=["location_id"]).to_numpy(dtype=float)
    if (abundance_values < 0).any() or not np.allclose(abundance_values.sum(axis=1), 1.0):
        raise RuntimeError("normalized mapping output failed nonnegative row-sum validation")
    report = {
        "schema_version": 1, "backend": args.backend, "spatial_sha256": digest(args.spatial_h5ad),
        "reference_sha256": digest(args.reference_h5ad), "shared_genes": len(genes),
        "cell_types": int(reference.obs[args.cell_type_key].nunique()), "seed": args.seed,
        "inputs": {
            "spatial_locations": int(spatial.n_obs),
            "reference_cells": int(reference.n_obs),
            "matrix_requirement": "finite_nonnegative_integer_counts" if integer_counts else "finite_nonnegative_expression",
        },
        "parameters": {
            "mode": "clusters" if args.backend == "tangram" else None,
            "cell_type_key": args.cell_type_key,
            "minimum_shared_genes": args.minimum_shared_genes,
            "epochs": args.epochs,
            "posterior_samples": args.posterior_samples if args.backend == "cell2location" else None,
            "device": args.device,
        },
        "versions": {
            args.backend: importlib.metadata.version(
                "tangram-sc" if args.backend == "tangram" else "cell2location"
            ),
            "anndata": importlib.metadata.version("anndata"),
            "numpy": importlib.metadata.version("numpy"),
            "pandas": importlib.metadata.version("pandas"),
            "torch": importlib.metadata.version("torch"),
        },
        "implementation": {
            "path": "biomed_workbench/modules/builtin/spatial-multimethod-inference/templates/run_deconvolution.py",
            "sha256": digest(Path(__file__).resolve()),
        },
        "outputs": {
            "abundance": {"sha256": digest(args.abundance_output), "rows": len(reloaded), "columns": len(reloaded.columns) - 1},
            "model": {"sha256": digest(args.model_output), "shape": [int(reloaded_model.n_obs), int(reloaded_model.n_vars)]},
            "diagnostics": {"sha256": digest(args.diagnostics_output)},
            "reloaded": True,
            "finite_nonnegative_row_normalized": True,
        },
        "claim_boundary": "Abundance or mapping estimates require reference, held-out-gene, posterior/residual and cross-method sensitivity review; they are not direct cell counts unless the selected model defines and validates that quantity.",
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
