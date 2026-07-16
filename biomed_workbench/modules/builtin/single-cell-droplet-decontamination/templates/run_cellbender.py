#!/usr/bin/env python3
"""Run CellBender remove-background and validate the serialized scientific output."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np
from cellbender.remove_background import consts
from cellbender.remove_background.downstream import anndata_from_h5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-h5", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--expected-cells", type=int, required=True)
    parser.add_argument("--total-droplets-included", type=int, required=True)
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--fpr", type=float, default=0.01)
    parser.add_argument("--model", choices=("naive", "simple", "ambient", "swapping", "full"), default="full")
    parser.add_argument("--cpu-threads", type=int, default=1)
    parser.add_argument("--use-cuda", choices=("false", "true"), default="false")
    parser.add_argument("--checkpoint", default="")
    return parser.parse_args()


def artifact_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
    else:
        for child in sorted(item for item in path.rglob("*") if item.is_file()):
            digest.update(child.relative_to(path).as_posix().encode())
            digest.update(child.read_bytes())
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    source = Path(args.input).resolve(strict=True)
    output = Path(args.output_h5)
    report_path = Path(args.report)
    if output.suffix != ".h5":
        raise ValueError("CellBender output must use the .h5 suffix")
    if output.exists() or report_path.exists():
        raise FileExistsError("refusing to overwrite declared outputs")
    if args.expected_cells < 10 or args.total_droplets_included <= args.expected_cells:
        raise ValueError("expected cells and total included droplets are inconsistent")
    if args.epochs < 1 or not 0 < args.fpr < 1 or args.cpu_threads < 1:
        raise ValueError("epochs, FPR, or CPU thread count is invalid")
    source_digest = artifact_sha256(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, "-m", "cellbender.base_cli", "remove-background",
        "--input", str(source), "--output", str(output),
        "--expected-cells", str(args.expected_cells),
        "--total-droplets-included", str(args.total_droplets_included),
        "--epochs", str(args.epochs), "--fpr", str(args.fpr),
        "--model", args.model, "--cpu-threads", str(args.cpu_threads),
    ]
    if args.use_cuda == "true":
        command.append("--cuda")
    if args.checkpoint:
        command.extend(["--checkpoint", str(Path(args.checkpoint))])
    environment = dict(os.environ)
    environment["PYTHONHASHSEED"] = str(consts.RANDOM_SEED)
    completed = subprocess.run(command, cwd=output.parent, env=environment, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"CellBender failed: {completed.stderr[-2500:]}")
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("CellBender did not create a nonempty HDF5 output")

    corrected = anndata_from_h5(str(output), analyzed_barcodes_only=False)
    values = corrected.X.data if hasattr(corrected.X, "data") else np.asarray(corrected.X).reshape(-1)
    if corrected.n_obs == 0 or corrected.n_vars == 0 or not corrected.obs_names.is_unique or not corrected.var_names.is_unique:
        raise RuntimeError("CellBender output has invalid shape or identifiers")
    if values.size == 0 or not np.isfinite(values).all() or np.any(values < 0):
        raise RuntimeError("CellBender output counts are empty, non-finite, or negative")
    if not np.allclose(values, np.rint(values), rtol=0, atol=1e-8):
        raise RuntimeError("CellBender output counts are not integer-like")
    if artifact_sha256(source) != source_digest:
        raise RuntimeError("source input changed during CellBender execution")
    expected_latents = {"cell_probability", "cell_size", "droplet_efficiency", "background_fraction"}
    latent_fields = sorted(expected_latents & (set(corrected.obs.columns) | set(corrected.uns)))
    if "cell_probability" not in latent_fields:
        raise RuntimeError("CellBender output does not retain cell-probability evidence")
    if "cell_probability" in corrected.uns:
        indices = np.asarray(corrected.uns.get("barcode_indices_for_latents", []))
        probabilities = np.asarray(corrected.uns["cell_probability"])
        if indices.size == 0 or probabilities.size != indices.size or np.any(indices >= corrected.n_obs):
            raise RuntimeError("CellBender latent probabilities do not reconcile to analyzed barcodes")
    output_digest = artifact_sha256(output)
    reloaded = anndata_from_h5(str(output), analyzed_barcodes_only=False)
    if reloaded.shape != corrected.shape or not np.array_equal(reloaded.obs_names, corrected.obs_names):
        raise RuntimeError("CellBender HDF5 did not reload with stable shape and barcodes")

    report = {
        "input_sha256": source_digest, "output_h5_sha256": output_digest,
        "output_droplets": int(corrected.n_obs), "output_features": int(corrected.n_vars),
        "output_nonzero_counts": int(values.size), "latent_fields": latent_fields,
        "expected_cells": args.expected_cells, "total_droplets_included": args.total_droplets_included,
        "epochs": args.epochs, "fpr": args.fpr, "model": args.model,
        "internal_random_seed": int(consts.RANDOM_SEED),
        "backend_requested": "cuda" if args.use_cuda == "true" else "cpu",
        "source_artifact_mutated": False, "serialized_output_reloaded": True,
        "versions": {"python": platform.python_version(), "cellbender": importlib.metadata.version("cellbender")},
        "quality_status": "review-required",
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
