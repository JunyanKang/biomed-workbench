#!/usr/bin/env python3
"""Run SAMap from versioned species AnnData inputs and precomputed homology maps."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from samap import SAMAP
from scipy import sparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--species-config", type=Path, required=True)
    parser.add_argument("--homology-map-directory", type=Path, required=True)
    parser.add_argument("--label-key", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output-h5ad", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_adata(path: Path, label_key: str) -> dict[str, object]:
    adata = ad.read_h5ad(path)
    values = adata.X.data if sparse.issparse(adata.X) else np.asarray(adata.X).ravel()
    if values.size == 0 or not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError(f"{path.name}: expression values are invalid")
    if label_key not in adata.obs or adata.obs[label_key].isna().any():
        raise ValueError(f"{path.name}: complete labels are required")
    if not adata.obs_names.is_unique or not adata.var_names.is_unique:
        raise ValueError(f"{path.name}: cell and gene identifiers must be unique")
    return {"cells": adata.n_obs, "genes": adata.n_vars, "sha256": digest(path)}


def main() -> int:
    args = parse_args()
    if args.output_h5ad.exists() or args.report.exists():
        raise FileExistsError("refusing to overwrite output")
    config = json.loads(args.species_config.read_text())
    if not isinstance(config, dict) or len(config) < 2:
        raise ValueError("species config must map at least two short species IDs to H5AD paths")
    species_paths = {str(species): Path(path).resolve(strict=True) for species, path in config.items()}
    if any(not 2 <= len(species) <= 4 for species in species_paths):
        raise ValueError("SAMap species identifiers must be unique short IDs of two to four characters")
    inventory = {
        species: validate_adata(path, args.label_key)
        for species, path in species_paths.items()
    }
    if not args.homology_map_directory.is_dir():
        raise ValueError("SAMap homology map directory is absent")
    map_files = sorted(path for path in args.homology_map_directory.rglob("*") if path.is_file())
    if not map_files:
        raise ValueError("SAMap requires precomputed BLAST homology map files")
    np.random.seed(args.seed)
    model = SAMAP(
        sams={species: str(path) for species, path in species_paths.items()},
        # SAMap 3.0.1 concatenates the pair identifier directly onto f_maps.
        # Preserve the official directory contract by supplying one separator.
        f_maps=str(args.homology_map_directory.resolve()) + os.sep,
    )
    model.run()
    # SAMap 3.0.1 returns its integrated data through the SAM container.
    # The AnnData object is intentionally extracted here so that downstream
    # workbench outputs keep their stable H5AD contract.
    result = model.samap.adata
    if result.n_obs != sum(item["cells"] for item in inventory.values()):
        raise RuntimeError("scientific validation failed: SAMap output changed cell count")
    if not np.isfinite(np.asarray(result.obsm["X_umap"])).all():
        raise RuntimeError("scientific validation failed: SAMap embedding is nonfinite")
    args.output_h5ad.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    result.write_h5ad(args.output_h5ad)
    output_sha256 = digest(args.output_h5ad)
    payload = {
        "schema_version": 1,
        "passed": True,
        "backend": "SAMap",
        "backend_version": importlib.metadata.version("sc-samap"),
        "species": inventory,
        "homology_map_files": len(map_files),
        "homology_map_digest": hashlib.sha256(
            "".join(digest(path) for path in map_files).encode()
        ).hexdigest(),
        "label_key": args.label_key,
        "seed": args.seed,
        "result": {
            "cells": int(result.n_obs),
            "genes": int(result.n_vars),
            "embedding": "X_umap",
            "output_h5ad_sha256": output_sha256,
        },
        "interpretation_scope": [
            "SAMap uses sequence-derived gene maps and expression neighborhoods; aligned cells are hypotheses of homology.",
            "Species-specific states must remain explicit and must not be forced into a shared label.",
            "Cross-condition differential inference returns to species-specific raw counts and biological samples.",
        ],
    }
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if ad.read_h5ad(args.output_h5ad).n_obs != result.n_obs:
        raise RuntimeError("SAMap output failed reload validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
