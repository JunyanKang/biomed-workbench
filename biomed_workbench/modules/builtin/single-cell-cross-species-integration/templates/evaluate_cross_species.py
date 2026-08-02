#!/usr/bin/env python3
"""Evaluate cross-species integration without requiring species signal to vanish."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

PROJECT_ROOT = Path(__file__).resolve().parents[5]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from biomed_workbench.capabilities.single_cell_integration import (
    integration_diagnostics,
    leave_one_species_out_validation,
    species_predictability,
    validate_inference_input,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integrated-h5ad", type=Path, required=True)
    parser.add_argument("--embedding-key", required=True)
    parser.add_argument("--species-key", required=True)
    parser.add_argument("--label-key", required=True)
    parser.add_argument("--sample-key", required=True)
    parser.add_argument("--cluster-key")
    parser.add_argument("--module-scores-tsv", type=Path)
    parser.add_argument("--n-neighbors", type=int, default=30)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def conserved_module_consistency(path: Path) -> dict[str, object]:
    frame = pd.read_csv(path, sep="\t")
    required = {"species", "cell_type", "module", "score"}
    if not required.issubset(frame):
        raise ValueError("module score table requires species, cell_type, module and score")
    means = (
        frame.groupby(["species", "cell_type", "module"], observed=True)["score"]
        .mean()
        .unstack("module")
    )
    pairs = []
    species_values = sorted(frame["species"].astype(str).unique())
    for index, left in enumerate(species_values):
        for right in species_values[index + 1 :]:
            shared = sorted(
                set(means.loc[left].index if left in means.index.levels[0] else [])
                & set(means.loc[right].index if right in means.index.levels[0] else [])
            )
            for cell_type in shared:
                left_values = means.loc[(left, cell_type)].to_numpy(dtype=float)
                right_values = means.loc[(right, cell_type)].to_numpy(dtype=float)
                finite = np.isfinite(left_values) & np.isfinite(right_values)
                if finite.sum() < 3:
                    continue
                correlation = spearmanr(left_values[finite], right_values[finite]).statistic
                pairs.append(
                    {
                        "species_a": left,
                        "species_b": right,
                        "cell_type": str(cell_type),
                        "modules": int(finite.sum()),
                        "spearman": None if not np.isfinite(correlation) else float(correlation),
                    }
                )
    return {"comparisons": pairs, "comparison_count": len(pairs)}


def main() -> int:
    args = parse_args()
    if args.report.exists():
        raise FileExistsError("refusing to overwrite report")
    adata = ad.read_h5ad(args.integrated_h5ad)
    required_obs = {args.species_key, args.label_key, args.sample_key}
    missing = sorted(required_obs - set(adata.obs))
    if missing:
        raise ValueError(f"integrated object is missing metadata: {', '.join(missing)}")
    if args.embedding_key not in adata.obsm:
        raise ValueError("declared cross-species embedding is missing")
    if args.cluster_key and args.cluster_key not in adata.obs:
        raise ValueError("declared cluster key is missing")
    matrix = np.asarray(adata.obsm[args.embedding_key], dtype=float)
    if not np.isfinite(matrix).all() or args.n_neighbors < 2 or adata.n_obs <= args.n_neighbors:
        raise ValueError("embedding or neighbor setting is invalid")
    species = adata.obs[args.species_key].astype(str).to_numpy()
    labels = adata.obs[args.label_key].astype(str).to_numpy()
    diagnostics = integration_diagnostics(
        matrix,
        batch=species,
        labels=labels,
        clusters=None if args.cluster_key is None else adata.obs[args.cluster_key].astype(str),
        n_neighbors=args.n_neighbors,
    )
    loso = leave_one_species_out_validation(
        matrix,
        species=species,
        labels=labels,
        n_neighbors=min(15, args.n_neighbors),
    )
    unsupported = {
        fold["held_out_species"]: fold["unsupported_truth_labels"]
        for fold in loso["folds"]
    }
    validate_inference_input(
        expression_semantics="raw_counts",
        sample_key=args.sample_key,
        donor_key=None,
        species_key=args.species_key,
    )
    payload = {
        "schema_version": 1,
        "passed": True,
        "cells": adata.n_obs,
        "species": sorted(set(species)),
        "embedding_key": args.embedding_key,
        "diagnostics": diagnostics,
        "species_predictability": species_predictability(matrix, species, seed=args.seed),
        "leave_one_species_out": loso,
        "unsupported_labels_by_held_out_species": unsupported,
        "conserved_module_consistency": (
            None
            if args.module_scores_tsv is None
            else conserved_module_consistency(args.module_scores_tsv)
        ),
        "interpretation": [
            "Species mixing and cell-state preservation are reported separately; complete species erasure is not a goal.",
            "Unsupported held-out-species labels are retained as unsupported rather than counted as successful transfer.",
            "Species-specific populations require review in the unintegrated space and independent marker evidence.",
            "Cross-condition inference uses species-specific raw counts with sample/donor/species as biological units.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
