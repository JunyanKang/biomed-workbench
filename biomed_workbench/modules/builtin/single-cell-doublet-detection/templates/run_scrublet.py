#!/usr/bin/env python3
"""Run sample-aware Scrublet doublet detection on immutable single-cell counts.

Adapt this project template only after inspecting the actual H5AD, sample design,
chemistry, expected recovery, and raw-count layer. A doublet score is evidence for
review, not an automatic instruction to discard a cell.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

import anndata
import numpy as np
import pandas as pd
import scrublet as scr
from scipy import sparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-h5ad", required=True)
    parser.add_argument("--output-h5ad", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--raw-count-location", required=True)
    parser.add_argument("--sample-key", required=True)
    parser.add_argument("--expected-doublet-rate", type=float, required=True)
    parser.add_argument("--min-cells-per-sample", type=int, default=50)
    parser.add_argument("--n-prin-comps", type=int, default=30)
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


def count_matrix(adata: anndata.AnnData, location: str):
    if location == "X":
        matrix = adata.X
    elif location.startswith("layers.") and location[7:] in adata.layers:
        matrix = adata.layers[location[7:]]
    else:
        raise ValueError("raw-count-location must be X or an existing layers.NAME entry")
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix).reshape(-1)
    if values.size == 0 or not np.isfinite(values).all() or float(values.min(initial=0)) < 0:
        raise ValueError("raw counts must be finite and nonnegative")
    if not np.allclose(values, np.rint(values), rtol=0, atol=1e-8):
        raise ValueError("raw-count-location is not integer-like")
    return matrix.copy()


def matrices_equal(left, right) -> bool:
    if left.shape != right.shape:
        return False
    if sparse.issparse(left) or sparse.issparse(right):
        left_csr = sparse.csr_matrix(left)
        right_csr = sparse.csr_matrix(right)
        difference = left_csr - right_csr
        difference.eliminate_zeros()
        return difference.nnz == 0
    return np.array_equal(np.asarray(left), np.asarray(right))


def run_sample(matrix, expected_rate: float, n_prin_comps: int, seed: int) -> tuple[np.ndarray, np.ndarray, float, int]:
    # Scrublet filters features internally. Retry only the PCA dimension after its
    # own admissibility check and retain the actual value in the evidence record.
    last_error: Exception | None = None
    for candidate_components in range(n_prin_comps, 1, -1):
        detector = scr.Scrublet(matrix, expected_doublet_rate=expected_rate, random_state=seed)
        try:
            scores, predicted = detector.scrub_doublets(n_prin_comps=candidate_components)
            break
        except ValueError as error:
            if "n_components=" not in str(error):
                raise
            last_error = error
    else:
        raise RuntimeError("Scrublet could not identify an admissible PCA dimension") from last_error
    threshold = float(detector.threshold_)
    if not np.isfinite(scores).all() or not np.isfinite(threshold):
        raise RuntimeError("Scrublet produced non-finite score or threshold")
    return np.asarray(scores, dtype=float), np.asarray(predicted, dtype=bool), threshold, candidate_components


def main() -> int:
    args = parse_args()
    source = Path(args.input_h5ad).resolve(strict=True)
    target = Path(args.output_h5ad)
    report_path = Path(args.report)
    if target.exists() or report_path.exists():
        raise FileExistsError("refusing to overwrite declared outputs")
    if target.absolute() == source or report_path.absolute() == source:
        raise ValueError("output artifacts must not replace the source H5AD")
    if not 0 < args.expected_doublet_rate < 1:
        raise ValueError("expected-doublet-rate must be strictly between zero and one")
    if args.min_cells_per_sample < 20 or args.n_prin_comps < 2:
        raise ValueError("minimum sample size and principal components are invalid")

    source_digest = sha256(source)
    adata = anndata.read_h5ad(source)
    if args.sample_key not in adata.obs or adata.obs[args.sample_key].isna().any():
        raise ValueError("sample-key is absent or incomplete")
    if not adata.obs_names.is_unique or not adata.var_names.is_unique:
        raise ValueError("cell and feature identifiers must be unique")
    counts = count_matrix(adata, args.raw_count_location)
    if (
        "counts" in adata.layers
        and args.raw_count_location != "layers.counts"
        and not matrices_equal(adata.layers["counts"], counts)
    ):
        raise ValueError(
            "an existing layers.counts differs from the declared raw-count location"
        )
    adata.layers["counts"] = counts

    scores = np.full(adata.n_obs, np.nan, dtype=float)
    calls = np.zeros(adata.n_obs, dtype=bool)
    statuses = np.full(adata.n_obs, "not-run", dtype=object)
    sample_reports: list[dict[str, object]] = []
    sample_values = adata.obs[args.sample_key].astype(str).to_numpy()
    for offset, sample in enumerate(sorted(pd.unique(sample_values))):
        indices = np.flatnonzero(sample_values == sample)
        if indices.size < args.min_cells_per_sample:
            statuses[indices] = "insufficient-cells"
            sample_reports.append({"sample": sample, "cells": int(indices.size), "status": "insufficient-cells"})
            continue
        sample_counts = counts[indices, :]
        sample_scores, sample_calls, threshold, used_components = run_sample(
            sample_counts,
            args.expected_doublet_rate,
            min(args.n_prin_comps, max(2, min(sample_counts.shape) - 1)),
            args.seed + offset,
        )
        scores[indices] = sample_scores
        calls[indices] = sample_calls
        statuses[indices] = "completed"
        sample_reports.append(
            {
                "sample": sample,
                "cells": int(indices.size),
                "status": "completed",
                "threshold": threshold,
                "n_prin_comps": used_components,
                "seed": args.seed + offset,
                "called_doublets": int(sample_calls.sum()),
                "called_fraction": float(sample_calls.mean()),
            }
        )

    completed = statuses == "completed"
    if not completed.any():
        raise RuntimeError("Scrublet did not run for any sample")
    adata.obs["scrublet_score"] = scores
    adata.obs["scrublet_call"] = pd.Categorical(calls, categories=[False, True])
    adata.obs["scrublet_status"] = pd.Categorical(statuses)
    adata.uns["biomed_workbench_doublets"] = {
        "template": "run_scrublet.py",
        "input_sha256": sha256(source),
        "raw_count_location": args.raw_count_location,
        "sample_key": args.sample_key,
        "expected_doublet_rate": args.expected_doublet_rate,
        "seed": args.seed,
        "versions": {"python": platform.python_version(), "anndata": package_version("anndata"), "scrublet": package_version("scrublet")},
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(target, compression="gzip")
    reloaded = anndata.read_h5ad(target)
    if (
        reloaded.shape != adata.shape
        or "counts" not in reloaded.layers
        or "scrublet_score" not in reloaded.obs
    ):
        raise RuntimeError("reloaded H5AD does not retain counts and Scrublet fields")
    if (
        not np.array_equal(reloaded.obs_names, adata.obs_names)
        or not np.array_equal(reloaded.var_names, adata.var_names)
        or not np.array_equal(
            reloaded.obs[args.sample_key].astype(str).to_numpy(),
            sample_values,
        )
        or not matrices_equal(reloaded.layers["counts"], counts)
    ):
        raise RuntimeError("raw counts or cell identities changed after serialization")
    if sha256(source) != source_digest:
        raise RuntimeError("source H5AD changed during Scrublet execution")
    report = {
        "schema_version": 2,
        "input": {
            "filename": source.name,
            "sha256": source_digest,
            "cells": int(adata.n_obs),
            "features": int(adata.n_vars),
            "raw_count_location": args.raw_count_location,
            "sample_key": args.sample_key,
            "samples": sorted(pd.unique(sample_values).tolist()),
            "total_counts": int(counts.sum()),
        },
        "input_cells": int(adata.n_obs),
        "completed_cells": int(completed.sum()),
        "not_run_cells": int((~completed).sum()),
        "called_doublets": int(calls[completed].sum()),
        "called_fraction": float(calls[completed].mean()),
        "sample_results": sample_reports,
        "raw_count_preserved": True,
        "source_immutable": True,
        "cell_and_feature_identity_preserved": True,
        "automatic_cell_removal_performed": False,
        "versions": {
            "python": platform.python_version(),
            "scrublet": package_version("scrublet"),
            "anndata": package_version("anndata"),
            "numpy": package_version("numpy"),
            "pandas": package_version("pandas"),
            "scipy": package_version("scipy"),
        },
        "output_h5ad_sha256": sha256(target),
        "output_reloaded": True,
        "quality_status": "review-required",
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
