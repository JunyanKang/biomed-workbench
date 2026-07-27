#!/usr/bin/env python3
"""Train and validate scVI or scANVI without overwriting scientific source data."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import random
from importlib.metadata import version
from pathlib import Path

import anndata
import numpy as np
import pandas as pd
import scanpy as sc
import scipy
from scipy import sparse
from scipy.sparse.csgraph import connected_components
import scvi
from scvi.model import SCANVI, SCVI
import sklearn
from sklearn.metrics import balanced_accuracy_score, f1_score
from sklearn.neighbors import NearestNeighbors
import torch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-h5ad", required=True)
    parser.add_argument("--output-h5ad", required=True)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--mode", choices=("scvi", "scanvi"), required=True)
    parser.add_argument("--raw-count-location", required=True)
    parser.add_argument("--batch-key", required=True)
    parser.add_argument("--sample-key", required=True)
    parser.add_argument("--reviewed-label-key", required=True)
    parser.add_argument("--unknown-label", required=True)
    parser.add_argument("--n-hidden", type=int, required=True)
    parser.add_argument("--n-latent", type=int, required=True)
    parser.add_argument("--n-layers", type=int, required=True)
    parser.add_argument("--dropout-rate", type=float, required=True)
    parser.add_argument("--gene-likelihood", choices=("nb", "zinb", "poisson"), required=True)
    parser.add_argument("--scvi-epochs", type=int, required=True)
    parser.add_argument("--scanvi-epochs", type=int, required=True)
    parser.add_argument("--batch-size", type=int, required=True)
    parser.add_argument("--train-size", type=float, required=True)
    parser.add_argument("--holdout-fraction", type=float, required=True)
    parser.add_argument("--n-neighbors", type=int, required=True)
    parser.add_argument("--minimum-batch-entropy-gain", type=float, required=True)
    parser.add_argument("--maximum-label-purity-loss", type=float, required=True)
    parser.add_argument("--minimum-label-connectivity", type=float, required=True)
    parser.add_argument("--minimum-heldout-macro-f1", type=float, required=True)
    parser.add_argument("--suggestion-confidence", type=float, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--de-group-key", default="none")
    parser.add_argument("--de-group1", default="")
    parser.add_argument("--de-group2", default="")
    parser.add_argument("--de-delta", type=float, default=0.25)
    parser.add_argument("--de-top-genes", type=int, default=50)
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(file_sha256(item).encode("ascii"))
    return digest.hexdigest()


def matrix_values(matrix) -> np.ndarray:
    return np.asarray(matrix.data) if sparse.issparse(matrix) else np.asarray(matrix).reshape(-1)


def get_counts(adata: anndata.AnnData, location: str):
    if location == "X":
        return adata.X
    if location.startswith("layers.") and location[7:] in adata.layers:
        return adata.layers[location[7:]]
    raise ValueError("raw-count-location must be X or an existing layers.NAME entry")


def validate_counts(matrix) -> None:
    values = matrix_values(matrix)
    if values.size and (not np.isfinite(values).all() or float(values.min()) < 0):
        raise ValueError("raw counts must contain finite nonnegative values")
    if values.size and not np.allclose(values, np.rint(values), rtol=0, atol=1e-8):
        raise ValueError("raw count location is not integer-like")


def metadata_frame(adata: anndata.AnnData, fields: list[str]) -> pd.DataFrame:
    missing = [field for field in fields if field not in adata.obs]
    if missing:
        raise ValueError(f"required observation metadata is missing: {', '.join(missing)}")
    frame = adata.obs.loc[:, fields].copy()
    for field in fields:
        if frame[field].isna().any():
            raise ValueError(f"metadata field contains missing values: {field}")
        frame[field] = frame[field].astype(str).str.strip()
        if frame[field].eq("").any():
            raise ValueError(f"metadata field contains empty values: {field}")
    return frame


def h5ad_safe_frame(frame: pd.DataFrame, *, preserve_missing: bool = True) -> pd.DataFrame:
    """Normalize string-like metadata before AnnData HDF5 serialization."""
    sanitized = frame.copy()
    sanitized.index = pd.Index(np.asarray(sanitized.index, dtype=object).astype(str), name=sanitized.index.name)
    for column in sanitized.columns:
        dtype = str(sanitized[column].dtype).lower()
        if dtype != "object" and "string" not in dtype:
            continue
        missing = sanitized[column].isna()
        values = np.array(sanitized[column].astype(object).where(~missing, None), dtype=object, copy=True)
        values[~missing.to_numpy()] = np.asarray(sanitized.loc[~missing, column].astype(str), dtype=object)
        if not preserve_missing:
            values[missing.to_numpy()] = "nan"
        sanitized[column] = pd.Categorical(values)
    return sanitized


def sanitize_h5ad_metadata(adata: anndata.AnnData) -> dict[str, int]:
    """Preserve metadata values while removing unsupported Arrow string arrays."""
    counts = {"obs_columns": int(adata.obs.shape[1]), "var_columns": int(adata.var.shape[1])}
    adata.obs = h5ad_safe_frame(adata.obs, preserve_missing=False)
    adata.var = h5ad_safe_frame(adata.var, preserve_missing=False)
    return counts


def bayesian_de_summary(model, model_adata: anndata.AnnData, args: argparse.Namespace) -> dict[str, object]:
    """Run a bounded cell-level scVI DE contrast after model admission only."""
    if args.de_group_key == "none":
        if args.de_group1 or args.de_group2:
            raise ValueError("DE group values require --de-group-key")
        return {"status": "not_requested", "evidence_level": "not_applicable"}
    if not args.de_group_key.strip() or not args.de_group1.strip():
        raise ValueError("requested Bayesian DE requires --de-group-key and --de-group1")
    if args.de_group2 == "rest":
        raise ValueError("use an empty --de-group2 for one-versus-all; 'rest' is not an scvi-tools category")
    if not 0 < args.de_delta <= 5 or not 1 <= args.de_top_genes <= 500:
        raise ValueError("Bayesian DE delta or result bound is invalid")
    if args.de_group_key not in model_adata.obs:
        raise ValueError("Bayesian DE group key is absent from model metadata")
    groups = model_adata.obs[args.de_group_key].astype(str)
    if args.de_group1 not in set(groups):
        raise ValueError("Bayesian DE group1 is absent from model metadata")
    if args.de_group2 and args.de_group2 not in set(groups):
        raise ValueError("Bayesian DE group2 is absent from model metadata")
    table = model.differential_expression(
        groupby=args.de_group_key,
        group1=args.de_group1,
        group2=args.de_group2 or None,
        mode="change",
        delta=args.de_delta,
    )
    required_columns = {"proba_de", "lfc_mean", "bayes_factor", "group1", "group2"}
    missing = sorted(required_columns - set(table.columns))
    if missing:
        raise RuntimeError(f"scvi-tools change-mode DE lacks required fields: {', '.join(missing)}")
    ranked = table.sort_values("proba_de", ascending=False).head(args.de_top_genes).reset_index()
    index_column = ranked.columns[0]
    records = [
        {
            "feature": str(row[index_column]),
            "proba_de": float(row["proba_de"]),
            "lfc_mean": float(row["lfc_mean"]),
            "bayes_factor": float(row["bayes_factor"]),
            "group1": str(row["group1"]),
            "group2": str(row["group2"]),
        }
        for _, row in ranked.iterrows()
    ]
    return {
        "status": "completed",
        "evidence_level": "exploratory_cell_level",
        "group_key": args.de_group_key,
        "group1": args.de_group1,
        "group2": args.de_group2 or "all-other-cells",
        "mode": "change",
        "delta": args.de_delta,
        "tested_features": int(table.shape[0]),
        "top_features": records,
        "interpretation_boundary": "This is model-based cell-level evidence and cannot substitute for pseudobulk or donor-aware condition inference.",
    }


def neighbors(representation: np.ndarray, count: int) -> np.ndarray:
    if not np.isfinite(representation).all():
        raise ValueError("latent representation contains nonfinite values")
    model = NearestNeighbors(n_neighbors=count + 1, metric="euclidean")
    rows = model.fit(representation).kneighbors(representation, return_distance=False)
    return np.asarray([row[row != index][:count] for index, row in enumerate(rows)], dtype=int)


def batch_entropy(indices: np.ndarray, batches: np.ndarray) -> float:
    levels = sorted(set(batches.tolist()))
    denominator = math.log(len(levels))
    values = []
    for row in indices:
        counts = np.asarray([(batches[row] == level).sum() for level in levels], dtype=float)
        probabilities = counts[counts > 0] / counts.sum()
        values.append(float(-(probabilities * np.log(probabilities)).sum() / denominator))
    return float(np.mean(values))


def label_purity(indices: np.ndarray, labels: np.ndarray, known: np.ndarray) -> float:
    values = []
    for index in np.flatnonzero(known):
        selected = indices[index]
        selected = selected[known[selected]]
        if selected.size:
            values.append(float(np.mean(labels[selected] == labels[index])))
    if not values:
        raise ValueError("known labels do not support neighborhood-purity evaluation")
    return float(np.mean(values))


def label_connectivity(indices: np.ndarray, labels: np.ndarray, known: np.ndarray) -> tuple[float, dict[str, float]]:
    source = np.repeat(np.arange(len(labels)), indices.shape[1])
    target = indices.reshape(-1)
    graph = sparse.csr_matrix((np.ones(len(source)), (source, target)), shape=(len(labels), len(labels)))
    graph = graph.maximum(graph.transpose())
    scores = {}
    for label in sorted(set(labels[known].tolist())):
        members = np.flatnonzero(known & (labels == label))
        if len(members) < 2:
            continue
        _, components = connected_components(graph[members][:, members], directed=False)
        scores[str(label)] = int(np.bincount(components).max()) / len(members)
    if not scores:
        raise ValueError("known labels do not support graph-connectivity evaluation")
    return float(np.mean(list(scores.values()))), scores


def representation_metrics(representation: np.ndarray, batches: np.ndarray, labels: np.ndarray, known: np.ndarray, count: int) -> dict[str, object]:
    indices = neighbors(representation, count)
    connectivity, by_label = label_connectivity(indices, labels, known)
    return {
        "batch_neighbor_entropy": batch_entropy(indices, batches),
        "known_label_neighbor_purity": label_purity(indices, labels, known),
        "mean_known_label_connectivity": connectivity,
        "known_label_connectivity": by_label,
    }


def baseline_pca(counts: sparse.csr_matrix, obs: pd.DataFrame, var: pd.DataFrame, batch_key: str, dimensions: int, seed: int) -> np.ndarray:
    baseline = anndata.AnnData(X=counts.copy(), obs=obs.copy(), var=var.copy())
    sc.pp.normalize_total(baseline, target_sum=10000)
    sc.pp.log1p(baseline)
    top_genes = min(max(20, dimensions * 5), baseline.n_vars)
    sc.pp.highly_variable_genes(baseline, n_top_genes=top_genes, flavor="cell_ranger", batch_key=batch_key)
    hvg_count = int(baseline.var["highly_variable"].sum())
    components = min(dimensions, hvg_count - 1, baseline.n_obs - 1)
    if components < 2:
        raise ValueError("baseline PCA cannot be estimated from the declared data")
    baseline = baseline[:, baseline.var["highly_variable"]].copy()
    sc.pp.scale(baseline, zero_center=True, max_value=10)
    sc.tl.pca(baseline, n_comps=components, random_state=seed)
    return np.asarray(baseline.obsm["X_pca"])


def stratified_holdout(labels: np.ndarray, unknown_label: str, fraction: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    heldout = np.zeros(len(labels), dtype=bool)
    for label in sorted(set(labels.tolist()) - {unknown_label}):
        members = np.flatnonzero(labels == label)
        if len(members) < 5:
            raise ValueError(f"reviewed label has fewer than five cells: {label}")
        count = min(len(members) - 2, max(1, int(round(len(members) * fraction))))
        heldout[rng.choice(members, size=count, replace=False)] = True
    return heldout


def train_kwargs(args: argparse.Namespace, epochs: int) -> dict[str, object]:
    return {
        "max_epochs": epochs,
        "train_size": args.train_size,
        "batch_size": min(args.batch_size, 1024),
        "shuffle_set_split": True,
        "enable_progress_bar": False,
        "enable_checkpointing": False,
        "logger": False,
    }


def main() -> int:
    args = parse_args()
    source = Path(args.input_h5ad).resolve(strict=True)
    source_digest = file_sha256(source)
    output = Path(args.output_h5ad)
    model_dir = Path(args.model_dir)
    report_path = Path(args.report)
    for path in (output, report_path, model_dir):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite output: {path.name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    model_dir.parent.mkdir(parents=True, exist_ok=True)
    if not (4 <= args.n_hidden <= 4096 and 2 <= args.n_latent <= 256 and 1 <= args.n_layers <= 8):
        raise ValueError("model dimensions are outside conservative bounds")
    if not (0 <= args.dropout_rate < 1 and 0 < args.train_size < 1 and 0 < args.holdout_fraction < 0.5):
        raise ValueError("training fractions or dropout are invalid")
    if not (0 <= args.minimum_heldout_macro_f1 <= 1 and 0 <= args.suggestion_confidence <= 1):
        raise ValueError("classification thresholds are invalid")

    source_adata = sc.read_h5ad(source)
    if source_adata.n_obs <= args.n_neighbors + 1 or source_adata.n_vars < max(10, args.n_latent + 1):
        raise ValueError("input is too small for the declared model and evaluation neighborhood")
    if not source_adata.obs_names.is_unique or not source_adata.var_names.is_unique:
        raise ValueError("cell and feature identifiers must be unique")
    metadata = metadata_frame(source_adata, [args.batch_key, args.sample_key, args.reviewed_label_key])
    batches = metadata[args.batch_key].to_numpy()
    samples = metadata[args.sample_key].to_numpy()
    labels = metadata[args.reviewed_label_key].to_numpy()
    if len(set(batches.tolist())) < 2 or len(set(samples.tolist())) < 2:
        raise ValueError("model validation requires at least two batches and biological samples")
    if not bool((metadata.groupby(args.sample_key, observed=True)[args.batch_key].nunique() == 1).all()):
        raise ValueError("each biological sample must map to exactly one batch")
    known = labels != args.unknown_label
    if len(set(labels[known].tolist())) < 2 or int((~known).sum()) < 1:
        raise ValueError("reviewed labels must include at least two known classes and explicit unknown cells")
    label_batches = pd.crosstab(metadata.loc[known, args.reviewed_label_key], metadata.loc[known, args.batch_key])
    if bool(((label_batches > 0).sum(axis=1) < 2).any()):
        raise ValueError("a reviewed label is confined to one batch")

    counts = get_counts(source_adata, args.raw_count_location)
    validate_counts(counts)
    original_counts = sparse.csr_matrix(counts, dtype=np.int64)
    model_obs = source_adata.obs.drop(columns=[args.reviewed_label_key]).copy()
    if args.reviewed_label_key in model_obs:
        raise RuntimeError("reviewed labels remain visible to base scVI training")
    adata = anndata.AnnData(X=original_counts.copy(), obs=model_obs, var=source_adata.var.copy())
    adata.layers["counts"] = original_counts.copy()
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    scvi.settings.seed = args.seed
    SCVI.setup_anndata(adata, layer="counts", batch_key=args.batch_key)
    base_model = SCVI(
        adata,
        n_hidden=args.n_hidden,
        n_latent=args.n_latent,
        n_layers=args.n_layers,
        dropout_rate=args.dropout_rate,
        gene_likelihood=args.gene_likelihood,
    )
    base_model.train(**train_kwargs(args, args.scvi_epochs))
    base_latent = np.asarray(base_model.get_latent_representation())
    selected_model = base_model
    selected_adata = adata
    selected_latent = base_latent
    holdout_metrics = None
    prediction_summary = None

    if args.mode == "scanvi":
        heldout = stratified_holdout(labels, args.unknown_label, args.holdout_fraction, args.seed)
        evaluation_adata = adata.copy()
        evaluation_adata.obs["_scanvi_training_label"] = labels.copy()
        evaluation_adata.obs.loc[heldout, "_scanvi_training_label"] = args.unknown_label
        evaluation_model = SCANVI.from_scvi_model(
            base_model,
            adata=evaluation_adata,
            labels_key="_scanvi_training_label",
            unlabeled_category=args.unknown_label,
        )
        evaluation_model.train(**train_kwargs(args, args.scanvi_epochs))
        heldout_predictions = np.asarray(evaluation_model.predict())[heldout]
        heldout_truth = labels[heldout]
        holdout_metrics = {
            "cells": int(heldout.sum()),
            "macro_f1": float(f1_score(heldout_truth, heldout_predictions, average="macro")),
            "balanced_accuracy": float(balanced_accuracy_score(heldout_truth, heldout_predictions)),
            "truth_counts": {str(key): int(value) for key, value in zip(*np.unique(heldout_truth, return_counts=True))},
            "prediction_counts": {str(key): int(value) for key, value in zip(*np.unique(heldout_predictions, return_counts=True))},
        }

        final_adata = adata.copy()
        final_adata.obs["_scanvi_training_label"] = labels.copy()
        final_model = SCANVI.from_scvi_model(
            base_model,
            adata=final_adata,
            labels_key="_scanvi_training_label",
            unlabeled_category=args.unknown_label,
        )
        final_model.train(**train_kwargs(args, args.scanvi_epochs))
        probabilities = final_model.predict(soft=True)
        suggestions = probabilities.idxmax(axis=1).astype(str).to_numpy()
        confidence = probabilities.max(axis=1).to_numpy(dtype=float)
        output_labels = labels.copy()
        low_confidence = confidence < args.suggestion_confidence
        output_labels[~known] = args.unknown_label
        selected_model = final_model
        selected_adata = final_adata
        selected_latent = np.asarray(final_model.get_latent_representation())
        prediction_summary = {
            "suggested_known_classes": sorted(probabilities.columns.astype(str).tolist()),
            "minimum_suggestion_confidence": args.suggestion_confidence,
            "low_confidence_cells": int(low_confidence.sum()),
            "original_unknown_cells": int((~known).sum()),
            "unknown_cells_retained_for_review": int((output_labels == args.unknown_label).sum()),
        }

    baseline_representation = baseline_pca(original_counts, adata.obs, adata.var, args.batch_key, args.n_latent, args.seed)
    baseline = representation_metrics(baseline_representation, batches, labels, known, args.n_neighbors)
    modeled = representation_metrics(selected_latent, batches, labels, known, args.n_neighbors)
    entropy_gain = float(modeled["batch_neighbor_entropy"] - baseline["batch_neighbor_entropy"])
    purity_loss = float(baseline["known_label_neighbor_purity"] - modeled["known_label_neighbor_purity"])

    output_adata = source_adata.copy()
    latent_key = "X_scANVI" if args.mode == "scanvi" else "X_scVI"
    output_adata.obsm[latent_key] = selected_latent
    if args.mode == "scanvi":
        output_adata.obs["scanvi_suggested_label"] = suggestions
        output_adata.obs["scanvi_suggestion_confidence"] = confidence
        output_adata.obs["scanvi_conservative_label"] = output_labels
        output_adata.obs["scanvi_requires_review"] = (~known) | low_confidence
    sc.pp.neighbors(output_adata, n_neighbors=args.n_neighbors, use_rep=latent_key, random_state=args.seed)
    sc.tl.umap(output_adata, random_state=args.seed)
    raw_preserved = (sparse.csr_matrix(get_counts(output_adata, args.raw_count_location)) != original_counts).nnz == 0

    selected_model.save(str(model_dir), overwrite=False, save_anndata=False)
    metadata_serialization = sanitize_h5ad_metadata(output_adata)
    output_adata.uns["biomed_generative_model"] = {
        "mode": args.mode,
        "latent_key": latent_key,
        "reviewed_label_key": args.reviewed_label_key,
        "unknown_label": args.unknown_label,
        "reviewed_labels_overwritten": False,
        "quality_status": "pending_reload",
        "metadata_serialization": metadata_serialization,
    }
    output_adata.write_h5ad(output)
    reloaded_adata = sc.read_h5ad(output)
    model_class = SCANVI if args.mode == "scanvi" else SCVI
    reloaded_model = model_class.load(str(model_dir), adata=selected_adata)
    reloaded_latent = np.asarray(reloaded_model.get_latent_representation())
    model_reload_valid = reloaded_latent.shape == selected_latent.shape and np.isfinite(reloaded_latent).all()
    h5ad_reload_valid = (
        reloaded_adata.shape == source_adata.shape
        and latent_key in reloaded_adata.obsm
        and "X_umap" in reloaded_adata.obsm
        and "connectivities" in reloaded_adata.obsp
        and (sparse.csr_matrix(get_counts(reloaded_adata, args.raw_count_location)) != original_counts).nnz == 0
        and np.array_equal(reloaded_adata.obs[args.reviewed_label_key].astype(str).to_numpy(), labels)
        and all(
            np.array_equal(
                reloaded_adata.obs[column].astype(str).to_numpy(),
                source_adata.obs[column].astype(str).to_numpy(),
            )
            for column in source_adata.obs.columns
        )
    )
    gates = {
        "latent_finite": bool(np.isfinite(selected_latent).all()),
        "batch_mixing_gain": entropy_gain >= args.minimum_batch_entropy_gain,
        "label_purity_preserved": purity_loss <= args.maximum_label_purity_loss,
        "label_graph_connected": float(modeled["mean_known_label_connectivity"]) >= args.minimum_label_connectivity,
        "reviewed_and_unknown_labels_preserved": bool(np.array_equal(output_adata.obs[args.reviewed_label_key].astype(str).to_numpy(), labels)),
        "raw_counts_preserved": bool(raw_preserved),
        "model_reload_valid": bool(model_reload_valid),
        "h5ad_reload_valid": bool(h5ad_reload_valid),
        "heldout_annotation_valid": args.mode == "scvi" or float(holdout_metrics["macro_f1"]) >= args.minimum_heldout_macro_f1,
    }
    quality_status = "passed" if all(gates.values()) else "blocked"
    bayesian_de = (
        bayesian_de_summary(selected_model, selected_adata, args)
        if quality_status == "passed"
        else {
            "status": "blocked_by_model_quality_gates",
            "evidence_level": "not_admitted",
            "interpretation_boundary": "Bayesian DE was not run because the generative model failed one or more required quality gates.",
        }
    )
    output_adata.uns["biomed_generative_model"]["quality_status"] = quality_status
    output_adata.write_h5ad(output)
    final_reloaded_adata = sc.read_h5ad(output)
    final_h5ad_reload_valid = (
        final_reloaded_adata.uns["biomed_generative_model"]["quality_status"] == quality_status
        and latent_key in final_reloaded_adata.obsm
        and "connectivities" in final_reloaded_adata.obsp
        and (sparse.csr_matrix(get_counts(final_reloaded_adata, args.raw_count_location)) != original_counts).nnz == 0
        and np.array_equal(final_reloaded_adata.obs[args.reviewed_label_key].astype(str).to_numpy(), labels)
    )
    if not h5ad_reload_valid or not final_h5ad_reload_valid or not model_reload_valid:
        raise RuntimeError("model or h5ad reload validation failed")

    report = {
        "schema_version": 2,
        "mode": args.mode,
        "quality_status": quality_status,
        "input": {"filename": source.name, "sha256": file_sha256(source), "cells": output_adata.n_obs, "features": output_adata.n_vars, "raw_count_location": args.raw_count_location},
        "design": {
            "batch_key": args.batch_key,
            "sample_key": args.sample_key,
            "reviewed_label_key": args.reviewed_label_key,
            "unknown_label": args.unknown_label,
            "batch_count": len(set(batches.tolist())),
            "sample_count": len(set(samples.tolist())),
            "known_label_count": len(set(labels[known].tolist())),
            "unknown_cells": int((~known).sum()),
            "reviewed_labels_overwritten": False,
            "reviewed_labels_removed_before_base_scvi_training": True,
        },
        "parameters": {
            "n_hidden": args.n_hidden, "n_latent": args.n_latent, "n_layers": args.n_layers,
            "dropout_rate": args.dropout_rate, "gene_likelihood": args.gene_likelihood,
            "scvi_epochs": args.scvi_epochs, "scanvi_epochs": args.scanvi_epochs,
            "batch_size": args.batch_size, "train_size": args.train_size,
            "holdout_fraction": args.holdout_fraction, "n_neighbors": args.n_neighbors,
            "seed": args.seed, "de_group_key": args.de_group_key, "de_group1": args.de_group1,
            "de_group2": args.de_group2 or "all-other-cells", "de_delta": args.de_delta,
            "de_top_genes": args.de_top_genes,
        },
        "baseline_metrics": baseline,
        "modeled_metrics": modeled,
        "metric_deltas": {"batch_neighbor_entropy_gain": entropy_gain, "known_label_neighbor_purity_loss": purity_loss},
        "heldout_annotation_metrics": holdout_metrics,
        "prediction_summary": prediction_summary,
        "bayesian_differential_expression": bayesian_de,
        "quality_thresholds": {
            "minimum_batch_entropy_gain": args.minimum_batch_entropy_gain,
            "maximum_label_purity_loss": args.maximum_label_purity_loss,
            "minimum_label_connectivity": args.minimum_label_connectivity,
            "minimum_heldout_macro_f1": args.minimum_heldout_macro_f1,
            "suggestion_confidence": args.suggestion_confidence,
        },
        "quality_gates": gates,
        "source_immutable": file_sha256(source) == source_digest,
        "cell_feature_and_source_metadata_identity_preserved": True,
        "output": {"filename": output.name, "sha256": file_sha256(output), "latent_key": latent_key},
        "model": {"directory_name": model_dir.name, "sha256": tree_sha256(model_dir), "reload_valid": True},
        "versions": {
            "python": platform.python_version(), "scvi-tools": scvi.__version__, "scanpy": sc.__version__,
            "anndata": anndata.__version__, "numpy": np.__version__, "pandas": pd.__version__,
            "scipy": scipy.__version__, "scikit-learn": sklearn.__version__, "torch": torch.__version__,
            "lightning": version("lightning"),
        },
    }
    if not report["source_immutable"]:
        raise RuntimeError("source H5AD changed during generative modeling")
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"mode": args.mode, "quality_status": quality_status, "entropy_gain": entropy_gain, "purity_loss": purity_loss, "heldout_macro_f1": None if holdout_metrics is None else holdout_metrics["macro_f1"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
