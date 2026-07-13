#!/usr/bin/env python3
"""Execute Harmony, Scanorama, and BBKNN integration on a crossed-batch fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
MODULE_ID = "single-cell-batch-integration"
MODULE_VERSION = "1.0.0"
ROW_ID = "agent-protocol-1-scanpy-1104-harmony-020-scanorama-174-bbknn-160"
TEMPLATE = ROOT / "biomed_workbench" / "modules" / "builtin" / MODULE_ID / "templates" / "benchmark_integration.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], *, environment: dict[str, str], timeout: int = 300) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=timeout, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"integration template failed: {completed.stderr[-3000:]}")
    return completed


def verify(scientific_python: Path) -> dict[str, object]:
    python = scientific_python.expanduser().resolve(strict=True)
    if not python.is_file() or not os.access(python, os.X_OK):
        raise RuntimeError("scientific Python is not executable")
    with tempfile.TemporaryDirectory(prefix="biomed-integration-") as temporary:
        work = Path(temporary)
        for name in ("numba", "matplotlib", "cache", "home"):
            (work / name).mkdir()
        environment = {
            "PATH": str(python.parent) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(work / "home"),
            "NUMBA_CACHE_DIR": str(work / "numba"),
            "MPLCONFIGDIR": str(work / "matplotlib"),
            "XDG_CACHE_HOME": str(work / "cache"),
            "PYTHONHASHSEED": "0",
            "LANG": "C",
            "LC_ALL": "C",
        }
        fixture = work / "crossed-batch.h5ad"
        fixture_code = f"""
import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse

rng = np.random.default_rng(781)
samples = ['S1', 'S2', 'S3', 'S4']
batches = {{'S1': 'batch-A', 'S2': 'batch-A', 'S3': 'batch-B', 'S4': 'batch-B'}}
labels = [('T_cell', 30), ('B_cell', 30), ('unknown', 10)]
genes = [f'GENE{{i:03d}}' for i in range(80)]
matrix, records, cells = [], [], []
for sample_index, sample in enumerate(samples):
    for label, count in labels:
        for cell_index in range(count):
            rate = np.full(80, 1.5 + sample_index * 0.04)
            if label == 'T_cell': rate[0:10] += 6.5
            if label == 'B_cell': rate[10:20] += 6.5
            if label == 'unknown': rate[20:30] += 5.0
            if batches[sample] == 'batch-A': rate[30:45] += 5.5
            else: rate[45:60] += 5.5
            matrix.append(rng.poisson(rate))
            records.append({{'sample_id': sample, 'chemistry_batch': batches[sample], 'reviewed_cell_type': label}})
            cells.append(f'{{sample}}-{{label}}-{{cell_index:03d}}')
raw = np.asarray(matrix, dtype=np.int32)
obs = pd.DataFrame(records, index=cells)
var = pd.DataFrame(index=genes)
adata = ad.AnnData(X=sparse.csr_matrix(np.log1p(raw)), obs=obs, var=var)
adata.layers['counts'] = sparse.csr_matrix(raw)
adata.uns['label_provenance'] = {{'reviewed': True, 'used_for_integration': False}}
adata.write_h5ad({str(fixture)!r})
"""
        run([str(python), "-c", fixture_code], environment=environment)

        reports = {}
        execution = {}
        baseline_reference = None
        for method in ("harmony", "scanorama", "bbknn"):
            output = work / f"{method}.h5ad"
            report_path = work / f"{method}.json"
            run([
                str(python), str(TEMPLATE),
                "--input-h5ad", str(fixture), "--output-h5ad", str(output), "--report", str(report_path),
                "--method", method, "--raw-count-location", "layers.counts", "--batch-key", "chemistry_batch",
                "--sample-key", "sample_id", "--evaluation-label-key", "reviewed_cell_type", "--unknown-label", "unknown",
                "--n-top-genes", "65", "--n-pcs", "15", "--n-neighbors", "15",
                "--maximum-label-purity-loss", "0.15", "--minimum-batch-entropy-gain", "0.02",
                "--minimum-label-connectivity", "0.85", "--seed", "29",
            ], environment=environment)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if baseline_reference is None:
                baseline_reference = report["baseline_metrics"]
            if not (
                report["method"] == method
                and report["input"]["cells"] == 280
                and report["input"]["features"] == 80
                and report["design"]["batch_count"] == 2
                and report["design"]["sample_count"] == 4
                and report["design"]["known_label_count"] == 2
                and report["design"]["unknown_cells"] == 40
                and report["design"]["labels_used_for_training"] is False
                and report["design"]["labels_spanning_batches"] == {"B_cell": 2, "T_cell": 2}
                and report["quality_gates"]["raw_counts_preserved"] is True
                and report["quality_gates"]["unknown_labels_retained"] is True
                and report["quality_gates"]["label_purity_preserved"] is True
                and report["quality_gates"]["label_graph_connected"] is True
                and report["reload_validation_passed"] is True
            ):
                raise RuntimeError(f"{method} failed structural or biological-conservation validation")
            if any(abs(float(report["baseline_metrics"][key]) - float(baseline_reference[key])) > 1e-10 for key in ("batch_neighbor_entropy", "label_neighbor_purity", "mean_label_graph_connectivity")):
                raise RuntimeError("integration candidates did not use one frozen baseline")
            reports[method] = report
            execution[f"{method}_completed"] = True
            execution[f"{method}_output_sha256"] = sha256(output)
            execution[f"{method}_report_sha256"] = sha256(report_path)

        eligible = sorted(method for method, report in reports.items() if report["quality_status"] == "passed")
        blocked = {method: [gate for gate, passed in report["quality_gates"].items() if not passed] for method, report in reports.items() if report["quality_status"] != "passed"}
        if not eligible:
            raise RuntimeError("no integration candidate passed all declared gates")
        selected = max(eligible, key=lambda method: reports[method]["metric_deltas"]["batch_neighbor_entropy_gain"])
        versions = reports["harmony"]["versions"]
        return {
            "schema_version": 1,
            "passed": True,
            "module_id": MODULE_ID,
            "module_version": MODULE_VERSION,
            "compatibility_row_id": ROW_ID,
            "templates": {"benchmark_integration": {"name": TEMPLATE.name, "sha256": sha256(TEMPLATE)}},
            "tool_versions": {key: versions[key] for key in ("scanpy", "harmonypy", "scanorama", "bbknn")},
            "dependency_versions": {
                "anndata": versions["anndata"], "numpy": versions["numpy"], "pandas": versions["pandas"],
                "scipy": versions["scipy"], "scikit-learn": versions["scikit-learn"],
                "umap-learn": "0.5.12",
            },
            "fixture": {"sha256": sha256(fixture), "cells": 280, "features": 80, "biological_samples": 4, "batches": 2, "known_labels": 2, "unknown_cells": 40},
            "execution": execution,
            "candidate_results": {
                method: {
                    "quality_status": report["quality_status"],
                    "batch_neighbor_entropy_gain": report["metric_deltas"]["batch_neighbor_entropy_gain"],
                    "label_neighbor_purity_loss": report["metric_deltas"]["label_neighbor_purity_loss"],
                    "mean_label_graph_connectivity": report["integrated_metrics"]["mean_label_graph_connectivity"],
                    "quality_gates": report["quality_gates"],
                }
                for method, report in reports.items()
            },
            "decision": {"eligible_methods": eligible, "blocked_methods": blocked, "selected_method": selected, "selection_rule": "maximum batch entropy gain among candidates passing every conservation and provenance gate"},
            "scientific_summary": {
                "harmony_scanorama_bbknn_executed": True,
                "one_frozen_baseline_used": True,
                "labels_used_only_for_posthoc_evaluation": True,
                "unknown_cells_retained": True,
                "raw_counts_preserved": True,
                "biological_conservation_gates_passed": True,
                "eligible_method_selected_without_umap_scoring": True,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.scientific_python)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": MODULE_ID, "passed": True, "eligible": report["decision"]["eligible_methods"], "selected": report["decision"]["selected_method"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
