#!/usr/bin/env python3
"""Train and reload scVI and scANVI on a replicated single-cell fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
MODULE_ID = "single-cell-generative-modeling"
MODULE_VERSION = "1.2.0"
ROW_ID = "agent-protocol-1-scvi-120-scanpy-1115-torch-241"
TEMPLATE = ROOT / "biomed_workbench" / "modules" / "builtin" / MODULE_ID / "templates" / "train_scvi_scanvi.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], environment: dict[str, str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=timeout, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"generative modeling template failed: {completed.stderr[-5000:]}\n{completed.stdout[-2000:]}")
    return completed


def verify(scientific_python: Path) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    if not python.is_file() or not os.access(python, os.X_OK):
        raise RuntimeError("scientific Python is not executable")
    with tempfile.TemporaryDirectory(prefix="biomed-generative-") as temporary:
        work = Path(temporary)
        for name in ("matplotlib", "cache", "home"):
            (work / name).mkdir()
        environment = {
            "PATH": str(python.parent) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(work / "home"),
            "MPLCONFIGDIR": str(work / "matplotlib"),
            "XDG_CACHE_HOME": str(work / "cache"),
            "PYTHONHASHSEED": "0",
            "LANG": "C",
            "LC_ALL": "C",
        }
        fixture = work / "replicated-counts.h5ad"
        fixture_code = f"""
import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse

rng = np.random.default_rng(912)
samples = ['S1', 'S2', 'S3', 'S4']
batches = {{'S1': 'batch-A', 'S2': 'batch-A', 'S3': 'batch-B', 'S4': 'batch-B'}}
labels = [('T_cell', 28), ('B_cell', 28), ('Myeloid', 28), ('unknown', 12)]
genes = [f'GENE{{index:03d}}' for index in range(120)]
rows, records, cells = [], [], []
for sample_index, sample in enumerate(samples):
    for label, count in labels:
        for cell_index in range(count):
            rate = np.full(120, 1.2 + 0.05 * sample_index)
            if label == 'T_cell': rate[0:18] += 8.0
            elif label == 'B_cell': rate[18:36] += 8.0
            elif label == 'Myeloid': rate[36:54] += 8.0
            else: rate[54:72] += 6.0
            if batches[sample] == 'batch-A': rate[72:92] += 3.0
            else: rate[92:112] += 3.0
            rows.append(rng.poisson(rate))
            records.append({{'sample_id': sample, 'chemistry_batch': batches[sample], 'reviewed_cell_type': label}})
            cells.append(f'{{sample}}-{{label}}-{{cell_index:03d}}')
raw = np.asarray(rows, dtype=np.int32)
adata = ad.AnnData(
    X=sparse.csr_matrix(np.log1p(raw)),
    obs=pd.DataFrame(records, index=cells),
    var=pd.DataFrame(index=genes),
)
adata.layers['counts'] = sparse.csr_matrix(raw)
adata.uns['label_provenance'] = {{'reviewed': True, 'unknown_is_explicit': True}}
adata.write_h5ad({str(fixture)!r})
"""
        run([str(python), "-c", fixture_code], environment)

        reports = {}
        execution = {}
        for mode in ("scvi", "scanvi"):
            output = work / f"{mode}.h5ad"
            model = work / f"{mode}-model"
            report_path = work / f"{mode}.json"
            run([
                str(python), str(TEMPLATE),
                "--input-h5ad", str(fixture), "--output-h5ad", str(output),
                "--model-dir", str(model), "--report", str(report_path), "--mode", mode,
                "--raw-count-location", "layers.counts", "--batch-key", "chemistry_batch",
                "--sample-key", "sample_id", "--reviewed-label-key", "reviewed_cell_type",
                "--unknown-label", "unknown", "--n-hidden", "48", "--n-latent", "8",
                "--n-layers", "1", "--dropout-rate", "0.05", "--gene-likelihood", "nb",
                "--scvi-epochs", "60", "--scanvi-epochs", "40", "--batch-size", "96",
                "--train-size", "0.85", "--holdout-fraction", "0.2", "--n-neighbors", "15",
                "--minimum-batch-entropy-gain", "0.0", "--maximum-label-purity-loss", "0.15",
                "--minimum-label-connectivity", "0.9", "--minimum-heldout-macro-f1", "0.8",
                "--suggestion-confidence", "0.8", "--seed", "37",
            ], environment)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            structural_gates = (
                "latent_finite", "reviewed_and_unknown_labels_preserved", "raw_counts_preserved",
                "model_reload_valid", "h5ad_reload_valid",
            )
            expected = (
                report["schema_version"] == 2
                and report["mode"] == mode
                and report["input"]["cells"] == 384
                and report["input"]["features"] == 120
                and report["design"]["sample_count"] == 4
                and report["design"]["batch_count"] == 2
                and report["design"]["known_label_count"] == 3
                and report["design"]["unknown_cells"] == 48
                and report["design"]["reviewed_labels_overwritten"] is False
                and report["design"]["reviewed_labels_removed_before_base_scvi_training"] is True
                and report["source_immutable"] is True
                and report["cell_feature_and_source_metadata_identity_preserved"] is True
                and all(report["quality_gates"][gate] for gate in structural_gates)
                and report["model"]["reload_valid"] is True
            )
            if not expected:
                diagnostic = {
                    "quality_status": report.get("quality_status"),
                    "metric_deltas": report.get("metric_deltas"),
                    "baseline_metrics": report.get("baseline_metrics"),
                    "modeled_metrics": report.get("modeled_metrics"),
                    "quality_gates": report.get("quality_gates"),
                    "heldout_annotation_metrics": report.get("heldout_annotation_metrics"),
                }
                raise RuntimeError(f"{mode} failed structural, conservation, or reload validation: {json.dumps(diagnostic, sort_keys=True)}")
            if mode == "scanvi":
                heldout = report["heldout_annotation_metrics"]
                prediction = report["prediction_summary"]
                if report["quality_status"] != "passed" or heldout["macro_f1"] < 0.8 or heldout["balanced_accuracy"] < 0.8:
                    raise RuntimeError("scANVI failed independent held-out label validation")
                if prediction["unknown_cells_retained_for_review"] != 48:
                    raise RuntimeError("scANVI did not preserve original unknown identities")
            reports[mode] = report
            execution[f"{mode}_completed"] = True
            execution[f"{mode}_output_sha256"] = sha256(output)
            execution[f"{mode}_model_sha256"] = report["model"]["sha256"]
            execution[f"{mode}_report_sha256"] = sha256(report_path)

        versions = reports["scanvi"]["versions"]
        eligible = sorted(mode for mode, report in reports.items() if report["quality_status"] == "passed")
        blocked = {
            mode: [gate for gate, passed in report["quality_gates"].items() if not passed]
            for mode, report in reports.items() if report["quality_status"] != "passed"
        }
        if "scanvi" not in eligible:
            raise RuntimeError("no independently validated semi-supervised model remained eligible")
        return {
            "schema_version": 1,
            "passed": True,
            "module_id": MODULE_ID,
            "module_version": MODULE_VERSION,
            "compatibility_row_id": ROW_ID,
            "templates": {"train_scvi_scanvi": {"name": TEMPLATE.name, "sha256": sha256(TEMPLATE)}},
            "tool_versions": {key: versions[key] for key in ("scvi-tools", "scanpy")},
            "dependency_versions": {key: versions[key] for key in ("anndata", "numpy", "pandas", "scipy", "scikit-learn", "torch", "lightning")},
            "fixture": {"sha256": sha256(fixture), "cells": 384, "features": 120, "biological_samples": 4, "batches": 2, "known_labels": 3, "unknown_cells": 48},
            "execution": execution,
            "results": {
                mode: {
                    "quality_status": report["quality_status"],
                    "batch_neighbor_entropy_gain": report["metric_deltas"]["batch_neighbor_entropy_gain"],
                    "known_label_neighbor_purity_loss": report["metric_deltas"]["known_label_neighbor_purity_loss"],
                    "heldout_macro_f1": None if report["heldout_annotation_metrics"] is None else report["heldout_annotation_metrics"]["macro_f1"],
                    "quality_gates": report["quality_gates"],
                }
                for mode, report in reports.items()
            },
            "decision": {"eligible_modes": eligible, "blocked_modes": blocked, "selected_mode": "scanvi"},
            "scientific_summary": {
                "scvi_and_scanvi_trained": True,
                "models_and_h5ad_reloaded": True,
                "raw_counts_preserved": True,
                "reviewed_and_unknown_labels_preserved": True,
                "scanvi_evaluated_on_hidden_labels": True,
                "scanvi_predictions_are_reviewable_suggestions": True,
                "reviewed_labels_removed_before_base_scvi_training": True,
                "source_immutable": True,
                "source_metadata_preserved": True,
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
    print(json.dumps({"module_id": MODULE_ID, "passed": True, "modes": sorted(report["results"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
