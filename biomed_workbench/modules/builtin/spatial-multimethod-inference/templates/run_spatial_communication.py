#!/usr/bin/env python3
"""Run sample-separated COMMOT with a mandatory physical-distance cutoff."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd


def validate_spatial_contract(adata: ad.AnnData, sample_key: str, spatial_key: str) -> None:
    """Validate sample separation and finite physical coordinates."""
    if sample_key not in adata.obs or spatial_key not in adata.obsm:
        raise ValueError("sample identity or spatial coordinates are absent")
    if adata.obs[sample_key].isna().any():
        raise ValueError("sample identity must be complete")
    coordinates = np.asarray(adata.obsm[spatial_key], dtype=float)
    if coordinates.shape != (adata.n_obs, 2) or not np.isfinite(coordinates).all():
        raise ValueError("spatial coordinates must be finite observations by two")


def validate_database(database: pd.DataFrame) -> None:
    """Validate a ligand-receptor database without silently discarding pairs."""
    required = {"ligand", "receptor"}
    if not required <= set(database.columns):
        raise ValueError("database requires ligand and receptor columns")
    if database.empty or database[list(required)].isna().any().any():
        raise ValueError("ligand-receptor database is empty or incomplete")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-h5ad", type=Path, required=True)
    parser.add_argument("--sample-key", required=True)
    parser.add_argument("--spatial-key", default="spatial")
    parser.add_argument("--coordinate-unit", required=True)
    parser.add_argument("--database-csv", type=Path, required=True)
    parser.add_argument("--database-name", required=True)
    parser.add_argument("--distance-threshold", type=float, required=True)
    parser.add_argument("--heteromeric", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--pathway-sum", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.distance_threshold <= 0 or not args.coordinate_unit.strip():
        raise ValueError("positive distance threshold and physical coordinate unit are required")
    if args.output_directory.exists() or args.summary_output.exists() or args.report.exists():
        raise FileExistsError("refusing to overwrite output")
    import commot as ct
    adata = ad.read_h5ad(args.input_h5ad)
    validate_spatial_contract(adata, args.sample_key, args.spatial_key)
    database = pd.read_csv(args.database_csv)
    validate_database(database)
    args.output_directory.mkdir(parents=True)
    rows = []
    for sample in sorted(adata.obs[args.sample_key].astype(str).unique()):
        subset = adata[adata.obs[args.sample_key].astype(str) == sample].copy()
        subset.obsm["spatial"] = np.asarray(subset.obsm[args.spatial_key], dtype=float)
        if subset.n_obs < 10:
            raise ValueError(f"sample {sample} has fewer than ten observations")
        ct.tl.spatial_communication(
            subset, database=database, database_name=args.database_name,
            dis_thr=args.distance_threshold, heteromeric=args.heteromeric,
            pathway_sum=args.pathway_sum,
        )
        output = args.output_directory / f"{sample}.h5ad"
        subset.write_h5ad(output)
        keys = sorted(k for k in subset.obsm if k.startswith("commot-"))
        rows.append({"sample_id": sample, "observations": subset.n_obs, "distance_threshold": args.distance_threshold, "coordinate_unit": args.coordinate_unit, "communication_outputs": ";".join(keys)})
    pd.DataFrame(rows).to_csv(args.summary_output, sep="\t", index=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"schema_version": 1, "backend": "COMMOT", "database_name": args.database_name, "database_rows": len(database), "distance_threshold": args.distance_threshold, "coordinate_unit": args.coordinate_unit, "heteromeric": args.heteromeric, "pathway_sum": args.pathway_sum, "seed": args.seed, "samples_separated": True, "claim_boundary": "Distance-constrained scores are model-based communication hypotheses; condition inference requires biological-sample-level support and multiplicity control."}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
