#!/usr/bin/env python3
"""Prepare a count-preserving one-to-one ortholog matrix for classical baselines."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--species-config", type=Path, required=True)
    parser.add_argument("--orthology-ledger", type=Path, required=True)
    parser.add_argument("--count-layer", default="X")
    parser.add_argument("--sample-key", required=True)
    parser.add_argument("--label-key", required=True)
    parser.add_argument("--minimum-confidence", type=float, default=0.8)
    parser.add_argument("--output-h5ad", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    args = parse_args()
    if args.output_h5ad.exists() or args.report.exists():
        raise FileExistsError("refusing to overwrite output")
    if not 0 <= args.minimum_confidence <= 1:
        raise ValueError("minimum confidence must be between zero and one")
    config = json.loads(args.species_config.read_text())
    if not isinstance(config, dict) or len(config) < 2:
        raise ValueError("species config must map at least two species to H5AD files")
    ledger = pd.read_csv(args.orthology_ledger, sep="\t")
    required = {
        "source_species",
        "source_gene",
        "target_species",
        "target_gene",
        "orthogroup_id",
        "relation",
        "confidence",
    }
    if not required.issubset(ledger):
        raise ValueError("orthology ledger does not satisfy the required schema")
    ledger = ledger.loc[
        (ledger["relation"] == "one-to-one")
        & (pd.to_numeric(ledger["confidence"]) >= args.minimum_confidence)
    ].copy()
    if ledger.empty:
        raise ValueError("no high-confidence one-to-one orthologs remain")
    members = pd.concat(
        [
            ledger[["orthogroup_id", "source_species", "source_gene"]].rename(
                columns={"source_species": "species", "source_gene": "gene"}
            ),
            ledger[["orthogroup_id", "target_species", "target_gene"]].rename(
                columns={"target_species": "species", "target_gene": "gene"}
            ),
        ],
        ignore_index=True,
    ).drop_duplicates()
    counts = members.groupby(["orthogroup_id", "species"], observed=True).size()
    if (counts > 1).any():
        raise ValueError("one-to-one ledger contains multiple genes per species and orthogroup")
    complete_groups = sorted(
        group
        for group, frame in members.groupby("orthogroup_id", observed=True)
        if set(frame["species"]) == set(config)
    )
    if len(complete_groups) < 50:
        raise ValueError("fewer than 50 complete one-to-one orthogroups remain")
    pieces = []
    inventory = {}
    for species, raw_path in config.items():
        path = Path(raw_path).resolve(strict=True)
        adata = ad.read_h5ad(path)
        if args.sample_key not in adata.obs or args.label_key not in adata.obs:
            raise ValueError(f"{species}: sample or label metadata is missing")
        source = adata.X if args.count_layer == "X" else adata.layers[args.count_layer]
        values = source.data if sparse.issparse(source) else np.asarray(source).ravel()
        if values.size == 0 or np.any(values < 0) or not np.isfinite(values).all() or not np.allclose(values, np.rint(values)):
            raise ValueError(f"{species}: baseline requires immutable integer counts")
        mapping = (
            members.loc[
                (members["species"] == species)
                & members["orthogroup_id"].isin(complete_groups),
                ["orthogroup_id", "gene"],
            ]
            .set_index("orthogroup_id")["gene"]
        )
        genes = mapping.loc[complete_groups].tolist()
        missing = sorted(set(genes) - set(adata.var_names))
        if missing:
            raise ValueError(f"{species}: {len(missing)} ledger genes are absent from the count matrix")
        subset = adata[:, genes].copy()
        subset.X = source[:, adata.var_names.get_indexer(genes)].copy()
        subset.var_names = complete_groups
        subset.obs["species"] = str(species)
        subset.obs_names = [f"{species}:{cell}" for cell in subset.obs_names]
        pieces.append(subset)
        inventory[str(species)] = {
            "cells": subset.n_obs,
            "genes": subset.n_vars,
            "sha256": sha256(path),
        }
    combined = ad.concat(pieces, axis=0, join="inner", merge="same")
    if combined.n_vars != len(complete_groups) or not combined.obs_names.is_unique:
        raise RuntimeError("shared ortholog baseline failed axis validation")
    args.output_h5ad.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    combined.write_h5ad(args.output_h5ad)
    payload = {
        "schema_version": 1,
        "passed": True,
        "species": inventory,
        "orthogroups": len(complete_groups),
        "minimum_confidence": args.minimum_confidence,
        "count_layer": args.count_layer,
        "orthology_ledger_sha256": sha256(args.orthology_ledger),
        "permitted_backends": ["scVI", "scANVI", "Harmony", "Seurat-v5-CCA", "Seurat-v5-RPCA"],
        "scientific_boundary": [
            "The shared matrix is a deliberately conservative one-to-one baseline, not the only cross-species representation.",
            "SAMap, SATURN and CAME retain broader gene relationships and must be compared separately.",
            "Integrated representations are not confirmatory differential-expression inputs.",
        ],
    }
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if ad.read_h5ad(args.output_h5ad).shape != combined.shape:
        raise RuntimeError("shared ortholog baseline failed reload validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
