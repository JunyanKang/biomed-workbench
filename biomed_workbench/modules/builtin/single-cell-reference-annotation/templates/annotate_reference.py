#!/usr/bin/env python3
"""Run SingleR reference mapping and conservative marker/ontology adjudication."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import tempfile

import anndata
import numpy as np
import pandas as pd
import scanpy as sc
import scipy
from scipy import sparse
from scipy.io import mmwrite
import sklearn
from sklearn.metrics import f1_score


R_TEMPLATE = Path(__file__).with_name("run_singler.R")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-h5ad", required=True)
    parser.add_argument("--reference-h5ad", required=True)
    parser.add_argument("--output-h5ad", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--rscript", required=True)
    parser.add_argument("--query-raw-count-location", required=True)
    parser.add_argument("--reference-raw-count-location", required=True)
    parser.add_argument("--reference-label-key", required=True)
    parser.add_argument("--query-group-key", required=True)
    parser.add_argument("--existing-label-key", required=True)
    parser.add_argument("--evaluation-label-key", default="none")
    parser.add_argument("--unknown-label", required=True)
    parser.add_argument("--marker-panel", required=True)
    parser.add_argument("--ontology-contract", required=True)
    parser.add_argument("--minimum-common-genes", type=int, required=True)
    parser.add_argument("--minimum-query-gene-fraction", type=float, required=True)
    parser.add_argument("--minimum-delta-next", type=float, required=True)
    parser.add_argument("--minimum-group-consensus", type=float, required=True)
    parser.add_argument("--minimum-positive-marker-support", type=float, required=True)
    parser.add_argument("--maximum-negative-marker-conflict", type=float, required=True)
    parser.add_argument("--minimum-marker-log-expression-difference", type=float, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_counts(adata: anndata.AnnData, location: str):
    if location == "X":
        return adata.X
    if location.startswith("layers.") and location[7:] in adata.layers:
        return adata.layers[location[7:]]
    raise ValueError("raw count location must be X or an existing layers.NAME entry")


def validate_counts(matrix, name: str) -> sparse.csr_matrix:
    result = sparse.csr_matrix(matrix)
    values = result.data
    if values.size and (not np.isfinite(values).all() or float(values.min()) < 0):
        raise ValueError(f"{name} raw counts contain negative or nonfinite values")
    if values.size and not np.allclose(values, np.rint(values), rtol=0, atol=1e-8):
        raise ValueError(f"{name} raw counts are not integer-like")
    return result.astype(np.int64)


def log_normalize(counts: sparse.csr_matrix) -> sparse.csr_matrix:
    library = np.asarray(counts.sum(axis=1)).reshape(-1)
    if np.any(library <= 0):
        raise ValueError("zero-library cells cannot be reference-mapped")
    normalized = counts.multiply((10000.0 / library)[:, None]).tocsr()
    normalized.data = np.log1p(normalized.data)
    return normalized


def clean_obs_field(adata: anndata.AnnData, key: str) -> np.ndarray:
    if key not in adata.obs:
        raise ValueError(f"required observation field is missing: {key}")
    values = adata.obs[key]
    if values.isna().any():
        raise ValueError(f"observation field contains missing values: {key}")
    result = values.astype(str).str.strip().to_numpy()
    if np.any(result == ""):
        raise ValueError(f"observation field contains empty values: {key}")
    return result


def load_json_object(path: Path, name: str) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be a JSON object")
    return payload


def ancestors(identifier: str, parents: dict[str, list[str]]) -> set[str]:
    result = {identifier}
    active = [identifier]
    while active:
        child = active.pop()
        for parent in parents.get(child, []):
            if parent not in result:
                result.add(parent)
                active.append(parent)
    return result


def majority(values: np.ndarray) -> tuple[str, float]:
    levels, counts = np.unique(values, return_counts=True)
    order = np.argsort(-counts, kind="stable")
    return str(levels[order[0]]), float(counts[order[0]] / counts.sum())


def marker_decision(
    label: str,
    members: np.ndarray,
    expression: sparse.csr_matrix,
    global_mean: np.ndarray,
    gene_index: dict[str, int],
    marker_panel: dict[str, object],
    minimum_difference: float,
) -> dict[str, object]:
    contract = marker_panel[label]
    positive = [str(gene) for gene in contract["positive"]]
    negative = [str(gene) for gene in contract["negative"]]
    positive_present = [gene for gene in positive if gene in gene_index]
    negative_present = [gene for gene in negative if gene in gene_index]
    if not positive_present:
        raise ValueError(f"no positive marker is present for reference label: {label}")
    group_mean = np.asarray(expression[members].mean(axis=0)).reshape(-1)
    positive_pass = [gene for gene in positive_present if group_mean[gene_index[gene]] - global_mean[gene_index[gene]] >= minimum_difference]
    negative_fail = [gene for gene in negative_present if group_mean[gene_index[gene]] - global_mean[gene_index[gene]] >= minimum_difference]
    return {
        "positive_markers_declared": positive,
        "positive_markers_present": positive_present,
        "positive_markers_supported": positive_pass,
        "positive_support_fraction": len(positive_pass) / len(positive_present),
        "negative_markers_declared": negative,
        "negative_markers_present": negative_present,
        "negative_markers_conflicting": negative_fail,
        "negative_conflict_fraction": 0.0 if not negative_present else len(negative_fail) / len(negative_present),
    }


def main() -> int:
    args = parse_args()
    query_path = Path(args.query_h5ad).resolve(strict=True)
    reference_path = Path(args.reference_h5ad).resolve(strict=True)
    output_path = Path(args.output_h5ad)
    report_path = Path(args.report)
    marker_path = Path(args.marker_panel).resolve(strict=True)
    ontology_path = Path(args.ontology_contract).resolve(strict=True)
    rscript = Path(args.rscript).resolve(strict=True)
    source_digests = {
        "query_h5ad": sha256(query_path),
        "reference_h5ad": sha256(reference_path),
        "marker_panel": sha256(marker_path),
        "ontology_contract": sha256(ontology_path),
    }
    for path in (output_path, report_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite output: {path.name}")
        path.parent.mkdir(parents=True, exist_ok=True)
    if not R_TEMPLATE.is_file() or not rscript.is_file():
        raise ValueError("SingleR template or Rscript executable is unavailable")
    thresholds = (
        args.minimum_query_gene_fraction,
        args.minimum_group_consensus,
        args.minimum_positive_marker_support,
        args.maximum_negative_marker_conflict,
    )
    if args.minimum_common_genes < 10 or any(value < 0 or value > 1 for value in thresholds):
        raise ValueError("annotation thresholds are outside conservative bounds")

    query = sc.read_h5ad(query_path)
    reference = sc.read_h5ad(reference_path)
    if not query.obs_names.is_unique or not query.var_names.is_unique or not reference.obs_names.is_unique or not reference.var_names.is_unique:
        raise ValueError("query and reference cell and gene identifiers must be unique")
    query_groups = clean_obs_field(query, args.query_group_key)
    existing_labels = clean_obs_field(query, args.existing_label_key)
    reference_labels = clean_obs_field(reference, args.reference_label_key)
    query_counts = validate_counts(get_counts(query, args.query_raw_count_location), "query")
    reference_counts = validate_counts(get_counts(reference, args.reference_raw_count_location), "reference")
    original_query_counts = query_counts.copy()

    reference_gene_index = {str(gene): index for index, gene in enumerate(reference.var_names)}
    common_genes = [str(gene) for gene in query.var_names if str(gene) in reference_gene_index]
    overlap_fraction = len(common_genes) / query.n_vars
    if len(common_genes) < args.minimum_common_genes or overlap_fraction < args.minimum_query_gene_fraction:
        raise ValueError("query-reference gene overlap does not meet the declared contract")
    query_gene_index = {str(gene): index for index, gene in enumerate(query.var_names)}
    query_indices = np.asarray([query_gene_index[gene] for gene in common_genes])
    reference_indices = np.asarray([reference_gene_index[gene] for gene in common_genes])
    query_expression = log_normalize(query_counts[:, query_indices])
    reference_expression = log_normalize(reference_counts[:, reference_indices])

    marker_payload = load_json_object(marker_path, "marker panel")
    marker_labels = set(marker_payload)
    reference_label_set = set(reference_labels.tolist())
    if marker_labels != reference_label_set:
        raise ValueError("marker panel labels must exactly match reference labels")
    for label, contract in marker_payload.items():
        if not isinstance(contract, dict) or set(contract) != {"positive", "negative"}:
            raise ValueError(f"marker contract is invalid for label: {label}")
        if not isinstance(contract["positive"], list) or not contract["positive"]:
            raise ValueError(f"positive marker list is empty for label: {label}")
        if not isinstance(contract["negative"], list):
            raise ValueError(f"negative marker list is invalid for label: {label}")

    ontology = load_json_object(ontology_path, "ontology contract")
    if set(ontology) != {"label_to_ontology", "parents", "allowed_by_group"}:
        raise ValueError("ontology contract must declare label_to_ontology, parents, and allowed_by_group")
    label_to_ontology = {str(key): str(value) for key, value in ontology["label_to_ontology"].items()}
    parents = {str(key): [str(item) for item in value] for key, value in ontology["parents"].items()}
    allowed_by_group = {str(key): {str(item) for item in value} for key, value in ontology["allowed_by_group"].items()}
    if set(label_to_ontology) != reference_label_set:
        raise ValueError("ontology label mapping must exactly match reference labels")
    if set(allowed_by_group) - set(query_groups.tolist()):
        raise ValueError("ontology constraints name query groups that are absent")

    with tempfile.TemporaryDirectory(prefix="biomed-singler-") as temporary:
        work = Path(temporary)
        query_matrix = work / "query.mtx"
        reference_matrix = work / "reference.mtx"
        genes_path = work / "genes.txt"
        query_cells_path = work / "query-cells.txt"
        reference_cells_path = work / "reference-cells.txt"
        labels_path = work / "labels.txt"
        predictions_path = work / "predictions.tsv"
        versions_path = work / "versions.json"
        mmwrite(query_matrix, query_expression.transpose().tocoo())
        mmwrite(reference_matrix, reference_expression.transpose().tocoo())
        genes_path.write_text("\n".join(common_genes) + "\n", encoding="utf-8")
        query_cells_path.write_text("\n".join(map(str, query.obs_names)) + "\n", encoding="utf-8")
        reference_cells_path.write_text("\n".join(map(str, reference.obs_names)) + "\n", encoding="utf-8")
        labels_path.write_text("\n".join(reference_labels) + "\n", encoding="utf-8")
        completed = subprocess.run(
            [str(rscript), str(R_TEMPLATE), str(query_matrix), str(reference_matrix), str(genes_path), str(query_cells_path), str(reference_cells_path), str(labels_path), str(predictions_path), str(versions_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"SingleR execution failed: {completed.stderr[-3000:]}")
        predictions = pd.read_csv(predictions_path, sep="\t", dtype={"cell_id": str})
        r_versions = json.loads(versions_path.read_text(encoding="utf-8"))

    expected_cells = list(map(str, query.obs_names))
    if predictions["cell_id"].tolist() != expected_cells or len(predictions) != query.n_obs:
        raise RuntimeError("SingleR predictions do not reconcile to query cells")
    forced = predictions["singler_label"].astype(str).to_numpy()
    pruned = predictions["singler_pruned_label"].fillna("").astype(str).to_numpy()
    delta = predictions["singler_delta_next"].to_numpy(dtype=float)
    score_columns = [f"score::{label}" for label in sorted(reference_label_set)]
    if (
        set(score_columns) - set(predictions)
        or not np.isfinite(delta).all()
        or not np.isfinite(
            predictions[["singler_max_score", *score_columns]].to_numpy(dtype=float)
        ).all()
        or set(forced) - reference_label_set
        or set(pruned) - (reference_label_set | {""})
    ):
        raise RuntimeError("SingleR returned invalid labels or scores")

    global_mean = np.asarray(query_expression.mean(axis=0)).reshape(-1)
    common_gene_index = {gene: index for index, gene in enumerate(common_genes)}
    group_reports = {}
    group_candidate = {}
    group_passed = {}
    for group in sorted(set(query_groups.tolist())):
        members = np.flatnonzero(query_groups == group)
        candidate, forced_consensus = majority(forced[members])
        pruned_matches = float(np.mean(pruned[members] == candidate))
        marker = marker_decision(candidate, members, query_expression, global_mean, common_gene_index, marker_payload, args.minimum_marker_log_expression_difference)
        ontology_id = label_to_ontology[candidate]
        allowed = allowed_by_group.get(group)
        ontology_allowed = allowed is None or bool(ancestors(ontology_id, parents) & allowed)
        checks = {
            "forced_consensus": forced_consensus >= args.minimum_group_consensus,
            "pruned_consensus": pruned_matches >= args.minimum_group_consensus,
            "positive_marker_support": marker["positive_support_fraction"] >= args.minimum_positive_marker_support,
            "negative_marker_conflict": marker["negative_conflict_fraction"] <= args.maximum_negative_marker_conflict,
            "ontology_allowed": ontology_allowed,
        }
        group_candidate[group] = candidate
        group_passed[group] = all(checks.values())
        group_reports[group] = {
            "cells": len(members), "candidate_label": candidate, "candidate_ontology_id": ontology_id,
            "forced_consensus_fraction": forced_consensus, "pruned_consensus_fraction": pruned_matches,
            "allowed_ontology_ids": None if allowed is None else sorted(allowed),
            "marker_evidence": marker, "quality_checks": checks, "accepted": all(checks.values()),
        }

    conservative = np.full(query.n_obs, args.unknown_label, dtype=object)
    statuses = np.full(query.n_obs, "unknown", dtype=object)
    reasons = []
    for index, group in enumerate(query_groups):
        candidate = group_candidate[group]
        failures = []
        if not group_passed[group]:
            failures.extend(key for key, passed in group_reports[group]["quality_checks"].items() if not passed)
        if pruned[index] != candidate:
            failures.append("cell_pruned_or_discordant")
        if delta[index] < args.minimum_delta_next:
            failures.append("cell_delta_below_threshold")
        if failures:
            reasons.append(sorted(set(failures)))
        else:
            conservative[index] = candidate
            statuses[index] = "accepted"
            reasons.append([])

    output = query.copy()
    output.obs["reference_suggested_label"] = forced
    output.obs["reference_pruned_label"] = np.where(pruned == "", args.unknown_label, pruned)
    output.obs["reference_delta_next"] = delta
    output.obs["reference_candidate_ontology_id"] = [label_to_ontology[label] for label in forced]
    output.obs["reference_conservative_label"] = conservative
    output.obs["reference_annotation_status"] = statuses
    output.obs["reference_annotation_reasons"] = [";".join(value) for value in reasons]
    output.uns["biomed_reference_annotation"] = {
        "engine": "SingleR", "reference_label_key": args.reference_label_key,
        "query_group_key": args.query_group_key, "existing_label_key": args.existing_label_key,
        "unknown_label": args.unknown_label, "existing_labels_overwritten": False,
        "evaluation_labels_used_for_decision": False,
    }
    raw_preserved = (sparse.csr_matrix(get_counts(output, args.query_raw_count_location)) != original_query_counts).nnz == 0
    output.write_h5ad(output_path)
    reloaded = sc.read_h5ad(output_path)
    reload_valid = (
        reloaded.shape == query.shape
        and np.array_equal(reloaded.obs_names.to_numpy(), query.obs_names.to_numpy())
        and np.array_equal(reloaded.var_names.to_numpy(), query.var_names.to_numpy())
        and np.array_equal(reloaded.obs[args.existing_label_key].astype(str).to_numpy(), existing_labels)
        and np.array_equal(reloaded.obs["reference_conservative_label"].astype(str).to_numpy(), conservative.astype(str))
        and (sparse.csr_matrix(get_counts(reloaded, args.query_raw_count_location)) != original_query_counts).nnz == 0
    )
    if not reload_valid or not raw_preserved:
        raise RuntimeError("annotated h5ad failed identity, label, or raw-count reload validation")
    current_source_digests = {
        "query_h5ad": sha256(query_path),
        "reference_h5ad": sha256(reference_path),
        "marker_panel": sha256(marker_path),
        "ontology_contract": sha256(ontology_path),
    }
    if current_source_digests != source_digests:
        raise RuntimeError("query, reference, marker, or ontology source changed during annotation")

    evaluation = None
    if args.evaluation_label_key != "none":
        truth = clean_obs_field(query, args.evaluation_label_key)
        evaluation = {
            "labels_used_for_decision": False,
            "macro_f1": float(f1_score(truth, conservative.astype(str), average="macro")),
            "known_cell_accuracy": float(np.mean(conservative[truth != args.unknown_label] == truth[truth != args.unknown_label])),
            "unknown_retention_fraction": float(np.mean(conservative[truth == args.unknown_label] == args.unknown_label)),
        }

    report = {
        "schema_version": 2,
        "quality_status": "passed",
        "input": {
            "query_filename": query_path.name, "query_sha256": source_digests["query_h5ad"],
            "reference_filename": reference_path.name, "reference_sha256": source_digests["reference_h5ad"],
            "query_cells": query.n_obs, "reference_cells": reference.n_obs,
            "query_genes": query.n_vars, "reference_genes": reference.n_vars,
            "common_genes": len(common_genes), "query_gene_overlap_fraction": overlap_fraction,
        },
        "reference": {"label_key": args.reference_label_key, "labels": sorted(reference_label_set), "label_counts": {label: int(np.sum(reference_labels == label)) for label in sorted(reference_label_set)}},
        "annotation": {
            "accepted_cells": int(np.sum(conservative != args.unknown_label)),
            "unknown_cells": int(np.sum(conservative == args.unknown_label)),
            "output_label_counts": {str(label): int(count) for label, count in zip(*np.unique(conservative.astype(str), return_counts=True))},
            "group_results": group_reports,
        },
        "evaluation": evaluation,
        "quality_gates": {
            "query_reference_gene_overlap": True, "reference_labels_have_marker_contracts": True,
            "ontology_contract_complete": True, "singler_cell_reconciliation": True,
            "complete_finite_score_matrix": True, "source_artifacts_immutable": True,
            "existing_labels_preserved": bool(np.array_equal(output.obs[args.existing_label_key].astype(str).to_numpy(), existing_labels)),
            "raw_counts_preserved": bool(raw_preserved), "output_reload_valid": bool(reload_valid),
        },
        "thresholds": {
            "minimum_common_genes": args.minimum_common_genes, "minimum_query_gene_fraction": args.minimum_query_gene_fraction,
            "minimum_delta_next": args.minimum_delta_next, "minimum_group_consensus": args.minimum_group_consensus,
            "minimum_positive_marker_support": args.minimum_positive_marker_support,
            "maximum_negative_marker_conflict": args.maximum_negative_marker_conflict,
            "minimum_marker_log_expression_difference": args.minimum_marker_log_expression_difference,
        },
        "contracts": {"marker_panel_sha256": source_digests["marker_panel"], "ontology_contract_sha256": source_digests["ontology_contract"]},
        "output": {"filename": output_path.name, "sha256": sha256(output_path)},
        "versions": {
            "python": platform.python_version(), "scanpy": sc.__version__, "anndata": anndata.__version__,
            "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__,
            "scikit-learn": sklearn.__version__, **r_versions,
        },
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"quality_status": "passed", "accepted_cells": report["annotation"]["accepted_cells"], "unknown_cells": report["annotation"]["unknown_cells"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
