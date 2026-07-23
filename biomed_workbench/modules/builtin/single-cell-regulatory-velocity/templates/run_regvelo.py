#!/usr/bin/env python3
"""Fit GRN-informed regulatory velocity with explicit compatibility and quality gates."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import random
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import regvelo
from regvelo import REGVELOVI
import scvi
from scipy import sparse
import torch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-h5ad", required=True)
    parser.add_argument("--prior-grn-tsv", required=True)
    parser.add_argument("--output-h5ad", required=True)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--spliced-layer", default="spliced")
    parser.add_argument("--unspliced-layer", default="unspliced")
    parser.add_argument(
        "--layer-semantics",
        choices=("integer-counts", "nonnegative-continuous"),
        default="integer-counts",
    )
    parser.add_argument("--model-modes", default="soft")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--max-epochs", type=int, required=True)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--n-latent", type=int, default=10)
    parser.add_argument("--n-hidden", type=int, default=128)
    parser.add_argument("--lambda-grn", type=float, default=1.0)
    parser.add_argument("--lambda-l1", type=float, default=0.0)
    parser.add_argument("--minimum-regulators", type=int, default=5)
    parser.add_argument("--minimum-edges", type=int, default=10)
    parser.add_argument("--maximum-dense-bytes", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_version(name: str) -> str:
    return importlib.metadata.version(name)


def validated_layer(data: ad.AnnData, key: str, semantics: str) -> np.ndarray:
    if key not in data.layers:
        raise ValueError(f"required splicing layer is missing: {key}")
    matrix = data.layers[key]
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix)
    if values.size and (not np.isfinite(values).all() or np.min(values) < 0):
        raise ValueError(f"{key} contains negative or nonfinite values")
    if (
        semantics == "integer-counts"
        and values.size
        and not np.allclose(values, np.rint(values), rtol=0, atol=1e-8)
    ):
        raise ValueError(f"{key} is not integer-like")
    return np.asarray(matrix.toarray() if sparse.issparse(matrix) else matrix, dtype=np.float32)


def load_grn(path: Path, genes: pd.Index) -> tuple[pd.DataFrame, list[str]]:
    frame = pd.read_csv(path, sep="\t", index_col=0)
    if frame.empty or not frame.index.is_unique or not frame.columns.is_unique:
        raise ValueError("prior GRN must be a nonempty target-by-regulator matrix with unique identifiers")
    frame.index = frame.index.astype(str)
    frame.columns = frame.columns.astype(str)
    if frame.index.has_duplicates or frame.columns.has_duplicates:
        raise ValueError("prior GRN identifiers become duplicated after string normalization")
    numeric = frame.apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any() or not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("prior GRN contains nonnumeric or nonfinite values")
    missing_targets = numeric.index.difference(genes)
    missing_regulators = numeric.columns.difference(genes)
    if len(missing_targets) or len(missing_regulators):
        raise ValueError("prior GRN target or regulator identifiers are absent from the expression object")
    regulators = list(numeric.columns)
    square = pd.DataFrame(0.0, index=genes, columns=genes)
    square.loc[numeric.index, numeric.columns] = numeric
    np.fill_diagonal(square.values, 0)
    return square, regulators


def history_summary(history: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, values in history.items():
        array = pd.to_numeric(pd.Series(np.asarray(values).reshape(-1)), errors="coerce").to_numpy(dtype=float)
        finite = array[np.isfinite(array)]
        result[str(key)] = {
            "observations": int(array.size),
            "finite_observations": int(finite.size),
            "last_finite": float(finite[-1]) if finite.size else None,
        }
    return result


def main() -> int:
    args = parse_args()
    source_path = Path(args.input_h5ad).resolve(strict=True)
    grn_path = Path(args.prior_grn_tsv).resolve(strict=True)
    output_path = Path(args.output_h5ad)
    model_root = Path(args.model_dir)
    report_path = Path(args.report)
    for path in (output_path, model_root, report_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite output: {path.name}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    model_root.parent.mkdir(parents=True, exist_ok=True)
    model_root.mkdir()
    report_path.parent.mkdir(parents=True, exist_ok=True)

    modes = [value.strip() for value in args.model_modes.split(",") if value.strip()]
    if not modes or len(set(modes)) != len(modes) or not set(modes) <= {"hard", "soft"}:
        raise ValueError("model modes must be a unique comma-separated subset of hard,soft")
    if args.repeats < 1 or args.max_epochs < 2 or args.batch_size < 2:
        raise ValueError("repeats, epochs, or batch size are too small")
    if args.n_latent != 10 or args.n_hidden != 256:
        raise ValueError("RegVelo 0.4.2 supports only the validated default n_latent=10 and n_hidden=256 through this template")
    if args.lambda_grn < 0 or args.lambda_l1 < 0:
        raise ValueError("regularization strengths must be nonnegative")

    source_digest = sha256(source_path)
    grn_digest = sha256(grn_path)
    source = ad.read_h5ad(source_path)
    if source.n_obs < 20 or source.n_vars < 10:
        raise ValueError("input is too small for regulatory velocity")
    if not source.obs_names.is_unique or not source.var_names.is_unique:
        raise ValueError("cell and feature identifiers must be unique")
    estimated_dense_bytes = int(source.n_obs * source.n_vars * np.dtype("float32").itemsize * 2)
    if estimated_dense_bytes > args.maximum_dense_bytes:
        raise MemoryError(
            f"dense spliced/unspliced working layers require {estimated_dense_bytes} bytes, "
            f"above the declared maximum of {args.maximum_dense_bytes}"
        )
    spliced = validated_layer(source, args.spliced_layer, args.layer_semantics)
    unspliced = validated_layer(source, args.unspliced_layer, args.layer_semantics)
    if spliced.shape != unspliced.shape or not np.any(spliced) or not np.any(unspliced):
        raise ValueError("spliced and unspliced layers are empty or misaligned")

    square_grn, regulators = load_grn(grn_path, source.var_names)
    edge_count = int(np.count_nonzero(square_grn.to_numpy()))
    if len(regulators) < args.minimum_regulators or edge_count < args.minimum_edges:
        raise ValueError("prior GRN has too few regulators or edges for the declared analysis")

    work = ad.AnnData(
        X=spliced.copy(),
        obs=source.obs.copy(),
        var=source.var.copy(),
        layers={"spliced": spliced.copy(), "unspliced": unspliced.copy()},
    )
    work.uns["regvelo_prior_grn"] = {
        "filename": grn_path.name,
        "sha256": grn_digest,
        "orientation": "targets-by-regulators",
        "regulators": regulators,
        "edge_count": edge_count,
        "layer_semantics": args.layer_semantics,
    }
    REGVELOVI.setup_anndata(work, spliced_layer="spliced", unspliced_layer="unspliced")

    runs: list[dict[str, object]] = []
    outputs: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for mode in modes:
        for repeat in range(args.repeats):
            run_seed = args.seed + repeat
            random.seed(run_seed)
            np.random.seed(run_seed)
            torch.manual_seed(run_seed)
            scvi.settings.seed = run_seed
            torch.use_deterministic_algorithms(True, warn_only=True)
            model = REGVELOVI(
                work,
                W=torch.tensor(square_grn.to_numpy().T, dtype=torch.float32),
                regulators=regulators,
                soft_constraint=mode == "soft",
                lam=args.lambda_grn,
                lam2=args.lambda_l1,
            )
            model.train(
                max_epochs=args.max_epochs,
                batch_size=min(args.batch_size, work.n_obs),
                train_size=0.8,
                validation_size=0.2,
                early_stopping=False,
                enable_progress_bar=False,
                deterministic=True,
                check_val_every_n_epoch=1,
                plan_kwargs={"lr": 1e-3},
            )
            velocity = np.asarray(model.get_velocity(return_numpy=True), dtype=np.float32)
            latent_time = np.asarray(model.get_latent_time(return_numpy=True), dtype=np.float32)
            latent = np.asarray(model.get_latent_representation(), dtype=np.float32)
            if (
                velocity.shape != work.shape
                or latent_time.shape != work.shape
                or latent.shape != (work.n_obs, args.n_latent)
                or not all(np.isfinite(value).all() for value in (velocity, latent_time, latent))
            ):
                raise RuntimeError("RegVelo returned invalid velocity, latent-time, or latent-state arrays")
            run_id = f"{mode}-seed-{run_seed}"
            model_path = model_root / run_id
            model.save(model_path, overwrite=False, save_anndata=False)
            reloaded_model = REGVELOVI.load(model_path, adata=work)
            reloaded_latent = np.asarray(reloaded_model.get_latent_representation(), dtype=np.float32)
            if reloaded_latent.shape != latent.shape or not np.isfinite(reloaded_latent).all():
                raise RuntimeError("saved RegVelo model failed reload inference")
            outputs[run_id] = (velocity, latent_time, latent)
            runs.append({
                "run_id": run_id,
                "mode": mode,
                "seed": run_seed,
                "model_directory": model_path.name,
                "model_files": sorted(path.name for path in model_path.iterdir()),
                "history": history_summary(model.history),
                "velocity_finite": True,
                "latent_time_finite": True,
                "latent_representation_finite": True,
                "model_reloaded": True,
            })

    primary_id = runs[0]["run_id"]
    velocity, latent_time, latent = outputs[str(primary_id)]
    output = source.copy()
    output.layers["regvelo_velocity"] = sparse.csr_matrix(velocity)
    output.layers["regvelo_latent_time"] = sparse.csr_matrix(latent_time)
    output.obsm["X_regvelo"] = latent
    output.uns["biomed_regulatory_velocity"] = {
        "engine": "RegVelo",
        "engine_version": package_version("regvelo"),
        "primary_run": primary_id,
        "model_modes": modes,
        "repeats": args.repeats,
        "deterministic_training": True,
        "prior_grn_sha256": grn_digest,
        "prior_grn_orientation": "targets-by-regulators",
        "regulator_count": len(regulators),
        "edge_count": edge_count,
        "source_data_used_for_fitting": ["spliced", "unspliced", "prior-grn"],
        "layer_semantics": args.layer_semantics,
        "experimental_labels_used_for_fitting": False,
        "perturbation_predictions_are_causal_evidence": False,
    }
    output.write_h5ad(output_path, compression="gzip")
    reloaded = ad.read_h5ad(output_path)
    reloaded_spliced = validated_layer(reloaded, args.spliced_layer, args.layer_semantics)
    reloaded_unspliced = validated_layer(reloaded, args.unspliced_layer, args.layer_semantics)
    if (
        reloaded.shape != source.shape
        or not np.array_equal(reloaded.obs_names, source.obs_names)
        or not np.array_equal(reloaded.var_names, source.var_names)
        or not np.array_equal(reloaded_spliced, spliced)
        or not np.array_equal(reloaded_unspliced, unspliced)
        or "regvelo_velocity" not in reloaded.layers
        or "regvelo_latent_time" not in reloaded.layers
        or "X_regvelo" not in reloaded.obsm
        or reloaded.uns["biomed_regulatory_velocity"]["primary_run"] != primary_id
    ):
        raise RuntimeError("RegVelo output failed identity, field, or provenance reload validation")
    if sha256(source_path) != source_digest or sha256(grn_path) != grn_digest:
        raise RuntimeError("source h5ad or prior GRN changed during analysis")

    pairwise = []
    run_ids = list(outputs)
    for left_index, left_id in enumerate(run_ids):
        for right_id in run_ids[left_index + 1:]:
            left = outputs[left_id][0].reshape(-1)
            right = outputs[right_id][0].reshape(-1)
            correlation = float(np.corrcoef(left, right)[0, 1])
            pairwise.append({"left": left_id, "right": right_id, "velocity_pearson": correlation})
    report = {
        "schema_version": 1,
        "quality_status": "review-required",
        "input": {
            "filename": source_path.name,
            "sha256": source_digest,
            "cells": int(source.n_obs),
            "genes": int(source.n_vars),
            "spliced_layer": args.spliced_layer,
            "unspliced_layer": args.unspliced_layer,
            "layer_semantics": args.layer_semantics,
            "estimated_dense_bytes": estimated_dense_bytes,
            "maximum_dense_bytes": args.maximum_dense_bytes,
        },
        "prior_grn": {
            "filename": grn_path.name,
            "sha256": grn_digest,
            "orientation": "targets-by-regulators",
            "regulators": len(regulators),
            "edges": edge_count,
            "square_model_matrix_shape": list(square_grn.shape),
        },
        "parameters": {
            "model_modes": modes,
            "repeats": args.repeats,
            "max_epochs": args.max_epochs,
            "batch_size": min(args.batch_size, work.n_obs),
            "n_latent": args.n_latent,
            "n_hidden": args.n_hidden,
            "lambda_grn": args.lambda_grn,
            "lambda_l1": args.lambda_l1,
            "seed": args.seed,
            "deterministic_training": True,
        },
        "runs": runs,
        "stability": {"pairwise_velocity_correlations": pairwise},
        "quality": {
            "splicing_layers_validated_under_declared_semantics": True,
            "dense_memory_budget_enforced": True,
            "grn_namespace_and_orientation_validated": True,
            "multiple_modes_or_seeds_retained": len(runs) > 1,
            "deterministic_training_requested": True,
            "all_outputs_finite": True,
            "models_saved_and_reloaded": True,
            "source_artifacts_immutable": True,
            "source_count_layers_preserved_in_output": True,
            "experimental_labels_withheld_from_fitting": True,
            "perturbation_predictions_not_causal_claims": True,
            "output_reloaded": True,
        },
        "output": {"filename": output_path.name, "sha256": sha256(output_path)},
        "versions": {
            "python": platform.python_version(),
            "regvelo": package_version("regvelo"),
            "anndata": package_version("anndata"),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": package_version("scipy"),
            "scvelo": package_version("scvelo"),
            "scvi-tools": package_version("scvi-tools"),
            "cellrank": package_version("cellrank"),
            "torch": torch.__version__,
            "torchode": package_version("torchode"),
            "jax": package_version("jax"),
            "jaxlib": package_version("jaxlib"),
        },
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"quality_status": report["quality_status"], "runs": len(runs), "output": output_path.name}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
