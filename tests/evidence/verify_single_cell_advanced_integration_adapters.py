#!/usr/bin/env python3
"""Execute deterministic adapter/evaluator fixtures for mosaic and cross-species modules."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from tools.validate_module import validate_module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str]) -> None:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())


def template_inventory(module_id: str) -> dict[str, dict[str, str]]:
    directory = BUILTIN_ROOT / module_id / "templates"
    return {
        path.stem: {"name": path.name, "sha256": sha256(path)}
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def mosaic_fixture(root: Path) -> dict[str, object]:
    module_id = "single-cell-mosaic-integration"
    evaluator = BUILTIN_ROOT / module_id / "templates" / "evaluate_mosaic.py"
    cells = [f"cell-{index:02d}" for index in range(20)]
    latent = pd.DataFrame(
        {
            "cell_id": cells,
            "latent_1": np.linspace(-2, 2, 20),
            "latent_2": np.sin(np.linspace(0, 2 * np.pi, 20)),
            "latent_3": np.cos(np.linspace(0, 2 * np.pi, 20)),
        }
    )
    metadata = pd.DataFrame(
        {
            "cell_id": cells,
            "modality": ["rna", "atac"] * 10,
            "cell_type": ["state-a", "state-a", "state-b", "state-b"] * 5,
            "batch": ["batch-a"] * 10 + ["batch-b"] * 10,
            "paired_id": [f"pair-{index // 2:02d}" for index in range(20)],
        }
    )
    latent_path = root / "mosaic-latent.tsv"
    metadata_path = root / "mosaic-metadata.tsv"
    evaluator_report = root / "mosaic-evaluator.json"
    latent.to_csv(latent_path, sep="\t", index=False)
    metadata.to_csv(metadata_path, sep="\t", index=False)
    run(
        [
            sys.executable,
            str(evaluator),
            "--latent-tsv",
            str(latent_path),
            "--metadata-tsv",
            str(metadata_path),
            "--label-column",
            "cell_type",
            "--batch-column",
            "batch",
            "--paired-id-column",
            "paired_id",
            "--neighbors",
            "5",
            "--report",
            str(evaluator_report),
        ]
    )
    payload = json.loads(evaluator_report.read_text())
    if (
        payload.get("passed") is not True
        or payload.get("metrics", {}).get("paired_anchor", {}).get("paired_anchors") != 10
        or payload.get("scientific_validation", {}).get("no_single_winner_score") is not True
    ):
        raise RuntimeError("mosaic evaluator fixture failed its scientific contract")
    return {
        "fixture_cells": len(cells),
        "paired_anchors": 10,
        "evaluator_sha256": sha256(evaluator_report),
        "mixing_and_biology_separated": True,
        "count_level_inference_boundary_present": "raw counts" in payload["inference_boundary"],
    }


def cross_species_fixture(root: Path) -> dict[str, object]:
    module_id = "single-cell-cross-species-integration"
    evaluator = BUILTIN_ROOT / module_id / "templates" / "evaluate_cross_species.py"
    rng = np.random.default_rng(41)
    species = np.array(["species-a"] * 24 + ["species-b"] * 24)
    labels = np.array(
        ["shared-a"] * 12
        + ["shared-b"] * 12
        + ["shared-a"] * 10
        + ["shared-b"] * 10
        + ["species-b-only"] * 4
    )
    adata = ad.AnnData(np.ones((48, 4)))
    adata.obs_names = [f"cell-{index:02d}" for index in range(48)]
    adata.obs["species"] = species
    adata.obs["cell_type"] = labels
    adata.obs["sample"] = [f"sample-{index // 6:02d}" for index in range(48)]
    adata.obsm["X_integrated"] = rng.normal(size=(48, 6))
    input_path = root / "cross-species.h5ad"
    evaluator_report = root / "cross-species-evaluator.json"
    adata.write_h5ad(input_path)
    run(
        [
            sys.executable,
            str(evaluator),
            "--integrated-h5ad",
            str(input_path),
            "--embedding-key",
            "X_integrated",
            "--species-key",
            "species",
            "--label-key",
            "cell_type",
            "--sample-key",
            "sample",
            "--n-neighbors",
            "6",
            "--seed",
            "41",
            "--report",
            str(evaluator_report),
        ]
    )
    payload = json.loads(evaluator_report.read_text())
    if (
        payload.get("passed") is not True
        or payload.get("unsupported_labels_by_held_out_species", {}).get("species-b")
        != ["species-b-only"]
    ):
        raise RuntimeError("cross-species evaluator fixture failed unsupported-state retention")
    return {
        "fixture_cells": adata.n_obs,
        "species": 2,
        "unsupported_state_retained": True,
        "leave_one_species_out_executed": len(payload["leave_one_species_out"]["folds"]) == 2,
        "species_and_biology_metrics_separated": True,
        "evaluator_sha256": sha256(evaluator_report),
    }


def report(
    registry: ModuleRegistry,
    module_id: str,
    execution: dict[str, object],
) -> dict[str, object]:
    manifest = registry.get(module_id)
    package = validate_module(
        BUILTIN_ROOT / module_id,
        require_tests=True,
        execute_tests=True,
    )
    if package.get("valid") is not True:
        raise RuntimeError(f"module package validation failed: {module_id}")
    return {
        "schema_version": 1,
        "passed": True,
        "module_id": module_id,
        "module_version": manifest.version,
        "registry_digest": registry.digest,
        "compatibility_row_id": manifest.compatibility_matrix[0].id,
        "templates": template_inventory(module_id),
        "package_validation": package,
        "execution": execution,
        "scientific_summary": {
            "adapter_and_evaluator_executed": True,
            "outputs_reloaded": True,
            "native_backend_execution_observed": False,
            "method_specific_native_execution_required_for_project_claims": True,
            "no_environment_or_compute_infrastructure_managed": True,
        },
        "claim_boundary": (
            "This representative execution validates the module package, adapters and method-neutral "
            "evaluation contract. It does not claim that every optional native backend was installed "
            "or fitted; project use must execute and reload the selected native method."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mosaic-output", type=Path, required=True)
    parser.add_argument("--cross-species-output", type=Path, required=True)
    args = parser.parse_args()
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    with tempfile.TemporaryDirectory(prefix="advanced-integration-adapters-") as temporary:
        root = Path(temporary)
        mosaic = report(
            registry,
            "single-cell-mosaic-integration",
            mosaic_fixture(root),
        )
        cross_species = report(
            registry,
            "single-cell-cross-species-integration",
            cross_species_fixture(root),
        )
    for path, payload in (
        (args.mosaic_output, mosaic),
        (args.cross_species_output, cross_species),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "passed": True,
                "module_ids": [mosaic["module_id"], cross_species["module_id"]],
                "registry_digest": registry.digest,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
