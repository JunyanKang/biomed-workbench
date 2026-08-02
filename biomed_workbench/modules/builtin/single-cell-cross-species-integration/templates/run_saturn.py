#!/usr/bin/env python3
"""Validate inputs and invoke the official SATURN train-saturn.py entrypoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", type=Path, required=True)
    parser.add_argument("--saturn-script", type=Path, required=True)
    parser.add_argument("--label-key", required=True)
    parser.add_argument("--reference-label-key", required=True)
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--device-num", type=int, default=0)
    parser.add_argument("--embedding-model", choices=["ESM1b", "MSA1b", "protXL", "ESM1b_protref", "ESM2"], default="ESM1b")
    parser.add_argument("--hv-genes", type=int, default=8000)
    parser.add_argument("--num-macrogenes", type=int, default=2000)
    parser.add_argument("--pretrain-epochs", type=int, default=200)
    parser.add_argument("--metric-epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--work-directory", type=Path, required=True)
    parser.add_argument("--integrated-output-h5ad", type=Path, required=True)
    parser.add_argument("--stdout-log", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_input_table(path: Path, label_key: str, reference_label_key: str) -> list[dict[str, object]]:
    frame = pd.read_csv(path)
    required = {"species", "path", "embedding_path"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"SATURN input CSV is missing columns: {', '.join(missing)}")
    if len(frame) < 2 or frame["species"].astype(str).duplicated().any():
        raise ValueError("SATURN requires at least two unique species rows")
    inventory = []
    for row in frame.itertuples(index=False):
        species = str(row.species)
        h5ad_path = Path(str(row.path)).resolve(strict=True)
        embedding_path = Path(str(row.embedding_path)).resolve(strict=True)
        adata = ad.read_h5ad(h5ad_path)
        values = adata.X.data if sparse.issparse(adata.X) else np.asarray(adata.X).ravel()
        if values.size == 0 or np.any(values < 0) or not np.isfinite(values).all():
            raise ValueError(f"{species}: SATURN expression must be finite and nonnegative")
        if not np.allclose(values, np.rint(values)):
            raise ValueError(f"{species}: SATURN seurat_v3 HVG selection requires integer counts")
        for key in (label_key, reference_label_key):
            if key not in adata.obs or adata.obs[key].isna().any():
                raise ValueError(f"{species}: complete {key} values are required")
        if not adata.obs_names.is_unique or not adata.var_names.is_unique:
            raise ValueError(f"{species}: cell and gene identifiers must be unique")
        inventory.append(
            {
                "species": species,
                "cells": adata.n_obs,
                "genes": adata.n_vars,
                "h5ad_sha256": sha256(h5ad_path),
                "embedding_sha256": sha256(embedding_path),
            }
        )
    return inventory


def main() -> int:
    args = parse_args()
    declared = [args.integrated_output_h5ad, args.stdout_log, args.report]
    if any(path.exists() for path in declared):
        raise FileExistsError("refusing to overwrite declared outputs")
    if args.work_directory.exists() and any(args.work_directory.iterdir()):
        raise FileExistsError("SATURN work directory must be absent or empty")
    if any(value < 1 for value in (args.hv_genes, args.num_macrogenes, args.pretrain_epochs, args.metric_epochs, args.batch_size)):
        raise ValueError("SATURN dimensions, epochs and batch size must be positive")
    script = args.saturn_script.resolve(strict=True)
    inventory = validate_input_table(args.input_csv, args.label_key, args.reference_label_key)
    args.work_directory.mkdir(parents=True, exist_ok=True)
    args.stdout_log.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "python",
        str(script),
        "--in_data",
        str(args.input_csv.resolve(strict=True)),
        "--device",
        args.device,
        "--device_num",
        str(args.device_num),
        "--in_label_col",
        args.label_key,
        "--ref_label_col",
        args.reference_label_key,
        "--embedding_model",
        args.embedding_model,
        "--hv_genes",
        str(args.hv_genes),
        "--num_macrogenes",
        str(args.num_macrogenes),
        "--pretrain_epochs",
        str(args.pretrain_epochs),
        "--epochs",
        str(args.metric_epochs),
        "--batch_size",
        str(args.batch_size),
        "--seed",
        str(args.seed),
        "--work_dir",
        str(args.work_directory),
        "--log_dir",
        str(args.work_directory / "tensorboard"),
    ]
    completed = subprocess.run(
        command,
        cwd=script.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    args.stdout_log.write_text(completed.stdout + "\n[stderr]\n" + completed.stderr)
    if completed.returncode != 0:
        raise RuntimeError(f"SATURN failed with exit code {completed.returncode}; inspect {args.stdout_log}")
    candidates = sorted(
        path
        for path in args.work_directory.rglob("*.h5ad")
        if "pretrain" not in path.name.lower()
    )
    valid_candidates = []
    expected_cells = sum(int(item["cells"]) for item in inventory)
    for path in candidates:
        try:
            candidate = ad.read_h5ad(path)
        except Exception:
            continue
        if candidate.n_obs == expected_cells and "species" in candidate.obs:
            valid_candidates.append(path)
    if len(valid_candidates) != 1:
        raise RuntimeError(
            "SATURN output discovery requires exactly one final H5AD with all input cells; "
            f"found {len(valid_candidates)}"
        )
    args.integrated_output_h5ad.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(valid_candidates[0], args.integrated_output_h5ad)
    reloaded = ad.read_h5ad(args.integrated_output_h5ad)
    if reloaded.n_obs != expected_cells or reloaded.obs["species"].nunique() != len(inventory):
        raise RuntimeError("SATURN output failed cell/species reload validation")
    payload = {
        "schema_version": 1,
        "passed": True,
        "backend": "SATURN",
        "species": inventory,
        "parameters": {
            "device": args.device,
            "device_num": args.device_num,
            "embedding_model": args.embedding_model,
            "hv_genes": args.hv_genes,
            "num_macrogenes": args.num_macrogenes,
            "pretrain_epochs": args.pretrain_epochs,
            "metric_epochs": args.metric_epochs,
            "batch_size": args.batch_size,
            "seed": args.seed,
        },
        "official_entrypoint_sha256": sha256(script),
        "input_csv_sha256": sha256(args.input_csv),
        "native_output": str(valid_candidates[0]),
        "scientific_boundary": [
            "SATURN uses protein-language-model gene embeddings and learned macrogenes; it does not require one-to-one ortholog collapse.",
            "Protein embedding release and input gene identifiers are part of the scientific provenance.",
            "Species-specific states and unsupported labels must remain visible in held-out-species validation.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
