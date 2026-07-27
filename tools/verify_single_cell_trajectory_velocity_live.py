#!/usr/bin/env python3
"""Run scVelo dynamics on a known-time splicing simulation and validate direction."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
MODULE_ID = "single-cell-trajectory-velocity"
MODULE_VERSION = "1.1.0"
ROW_ID = "agent-protocol-1-scvelo-034-scanpy-1115"
TEMPLATE = ROOT / "biomed_workbench" / "modules" / "builtin" / MODULE_ID / "templates" / "run_velocity.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], environment: dict[str, str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, check=False, timeout=timeout)
    if completed.returncode != 0:
        raise RuntimeError(f"trajectory velocity template failed: {completed.stderr[-5000:]}\n{completed.stdout[-2000:]}")
    return completed


def verify(scientific_python: Path) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    if not os.access(python, os.X_OK):
        raise RuntimeError("scientific Python is not executable")
    with tempfile.TemporaryDirectory(prefix="biomed-velocity-") as temporary:
        work = Path(temporary)
        for name in ("numba", "matplotlib", "cache", "home"):
            (work / name).mkdir()
        environment = {
            "PATH": str(python.parent) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(work / "home"), "NUMBA_CACHE_DIR": str(work / "numba"),
            "MPLCONFIGDIR": str(work / "matplotlib"), "XDG_CACHE_HOME": str(work / "cache"),
            "PYTHONHASHSEED": "0", "LANG": "C", "LC_ALL": "C",
        }
        fixture = work / "known-time-splicing.h5ad"
        fixture_code = f"""
import numpy as np
import scvelo as scv

adata = scv.datasets.simulation(n_obs=160, n_vars=35, noise_model='gillespie', random_seed=4)
adata.obs_names = [f'cell-{{index:03d}}' for index in range(adata.n_obs)]
adata.var_names = [f'GENE{{index:03d}}' for index in range(adata.n_vars)]
adata.obs['sample_id'] = [f'S{{index % 4 + 1}}' for index in range(adata.n_obs)]
low = float(adata.obs['true_t'].quantile(0.1))
high = float(adata.obs['true_t'].quantile(0.9))
adata.obs['root_score'] = (adata.obs['true_t'] <= low).astype(float)
adata.obs['terminal_score'] = (adata.obs['true_t'] >= high).astype(float)
adata.X = adata.layers['spliced'].copy()
adata.write_h5ad({str(fixture)!r})
"""
        run([str(python), "-c", fixture_code], environment)
        output = work / "velocity.h5ad"
        analysis_path = work / "analysis.json"
        run([
            str(python), str(TEMPLATE), "--input-h5ad", str(fixture), "--output-h5ad", str(output), "--report", str(analysis_path),
            "--spliced-layer", "spliced", "--unspliced-layer", "unspliced", "--sample-key", "sample_id",
            "--experimental-time-key", "true_t", "--root-score-key", "root_score", "--terminal-score-key", "terminal_score",
            "--n-top-genes", "30", "--n-pcs", "15", "--n-neighbors", "20", "--max-dynamics-iterations", "10",
            "--minimum-modeled-genes", "20", "--minimum-latent-time-correlation", "0.65",
            "--minimum-velocity-pseudotime-correlation", "0.25", "--minimum-root-terminal-separation", "0.05",
            "--minimum-median-velocity-confidence", "0.7", "--seed", "41",
        ], environment)
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        if not (
            analysis["schema_version"] == 2
            and analysis["quality_status"] == "passed"
            and analysis["input"]["cells"] == 160
            and analysis["input"]["genes"] == 35
            and analysis["input"]["samples"] == 4
            and analysis["model"]["modeled_genes"] >= 20
            and analysis["direction_validation"]["latent_time_spearman"] >= 0.65
            and analysis["direction_validation"]["velocity_pseudotime_spearman"] >= 0.25
            and analysis["direction_validation"]["experimental_time_used_for_fitting"] is False
            and analysis["direction_validation"]["experimental_time_removed_before_backend_execution"] is True
            and analysis["source_immutable"] is True
            and analysis["cell_feature_and_source_metadata_identity_preserved"] is True
            and all(analysis["quality_gates"].values())
        ):
            raise RuntimeError(f"trajectory direction or preservation validation failed: {json.dumps(analysis, sort_keys=True)[:5000]}")
        versions = analysis["versions"]
        return {
            "schema_version": 1, "passed": True, "module_id": MODULE_ID, "module_version": MODULE_VERSION,
            "compatibility_row_id": ROW_ID,
            "templates": {"run_velocity": {"name": TEMPLATE.name, "sha256": sha256(TEMPLATE)}},
            "tool_versions": {"scvelo": versions["scvelo"], "scanpy": versions["scanpy"]},
            "dependency_versions": {key: versions[key] for key in ("anndata", "numpy", "pandas", "scipy", "scikit-learn", "numba", "umap-learn")},
            "fixture": {"sha256": sha256(fixture), "cells": 160, "genes": 35, "biological_samples": 4, "known_time": True, "spliced_and_unspliced_integer_counts": True},
            "execution": {"dynamical_model_completed": True, "velocity_graph_completed": True, "output_sha256": sha256(output), "analysis_report_sha256": sha256(analysis_path)},
            "results": {
                "modeled_genes": analysis["model"]["modeled_genes"],
                "latent_time_spearman": analysis["direction_validation"]["latent_time_spearman"],
                "velocity_pseudotime_spearman": analysis["direction_validation"]["velocity_pseudotime_spearman"],
                "root_terminal_separation": analysis["direction_validation"]["root_terminal_separation"],
                "median_velocity_confidence": analysis["confidence"]["median_velocity_confidence"],
            },
            "scientific_summary": {
                "spliced_unspliced_layers_validated": True, "dynamical_rna_velocity_executed": True,
                "velocity_graph_and_pseudotime_executed": True, "latent_time_direction_validated_against_known_time": True,
                "root_and_terminal_direction_validated": True, "experimental_time_withheld_from_model_fitting": True,
                "experimental_time_removed_before_backend_execution": True,
                "source_counts_and_identifiers_preserved": True, "velocity_h5ad_reloaded": True,
                "source_immutable": True, "source_metadata_preserved": True,
                "no_environment_or_compute_infrastructure_managed": True,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.scientific_python)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": MODULE_ID, "passed": True, "modeled_genes": report["results"]["modeled_genes"], "latent_time_spearman": report["results"]["latent_time_spearman"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
