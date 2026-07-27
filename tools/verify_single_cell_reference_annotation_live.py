#!/usr/bin/env python3
"""Run SingleR plus marker and ontology adjudication on a known-truth fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


MODULE_ID = "single-cell-reference-annotation"
MODULE_VERSION = "1.1.0"
ROW_ID = "agent-protocol-1-singler-241-scanpy-1115-r-432"
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / MODULE_ID
PYTHON_TEMPLATE = MODULE_ROOT / "templates" / "annotate_reference.py"
R_TEMPLATE = MODULE_ROOT / "templates" / "run_singler.R"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], environment: dict[str, str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, check=False, timeout=timeout)
    if completed.returncode != 0:
        raise RuntimeError(f"reference annotation failed: {completed.stderr[-5000:]}\n{completed.stdout[-2000:]}")
    return completed


def verify(scientific_python: Path, rscript: Path) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    if not python.is_file():
        raise FileNotFoundError(f"scientific Python is absent: {python}")
    r_executable = rscript.expanduser().resolve(strict=True)
    if not os.access(python, os.X_OK) or not os.access(r_executable, os.X_OK):
        raise RuntimeError("scientific Python or Rscript is not executable")
    with tempfile.TemporaryDirectory(prefix="biomed-reference-annotation-") as temporary:
        work = Path(temporary)
        for name in ("matplotlib", "cache", "home"):
            (work / name).mkdir()
        environment = {
            "PATH": str(python.parent) + os.pathsep + str(r_executable.parent) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(work / "home"), "MPLCONFIGDIR": str(work / "matplotlib"),
            "XDG_CACHE_HOME": str(work / "cache"), "PYTHONHASHSEED": "0", "LANG": "C", "LC_ALL": "C",
        }
        query = work / "query.h5ad"
        reference = work / "reference.h5ad"
        marker_panel = work / "markers.json"
        ontology = work / "ontology.json"
        fixture_code = f"""
import anndata as ad
import json
import numpy as np
import pandas as pd
from scipy import sparse

rng = np.random.default_rng(1801)
genes = [f'GENE{{index:03d}}' for index in range(120)]
labels = ['T_cell', 'B_cell', 'Myeloid']
marker_ranges = {{'T_cell': range(0, 12), 'B_cell': range(12, 24), 'Myeloid': range(24, 36)}}

reference_rows, reference_labels, reference_cells = [], [], []
for label in labels:
    for index in range(60):
        rate = np.full(120, 1.2)
        rate[list(marker_ranges[label])] += 9.0
        reference_rows.append(rng.poisson(rate))
        reference_labels.append(label)
        reference_cells.append(f'ref-{{label}}-{{index:03d}}')
reference_counts = np.asarray(reference_rows, dtype=np.int32)
reference_adata = ad.AnnData(
    X=sparse.csr_matrix(np.log1p(reference_counts)),
    obs=pd.DataFrame({{'reference_label': reference_labels}}, index=reference_cells),
    var=pd.DataFrame(index=genes),
)
reference_adata.layers['counts'] = sparse.csr_matrix(reference_counts)
reference_adata.write_h5ad({str(reference)!r})

query_rows, records, query_cells = [], [], []
design = [('T_cell', 'cluster_T', 20), ('B_cell', 'cluster_B', 20), ('Myeloid', 'cluster_M', 20), ('unknown', 'cluster_unknown', 10)]
for sample_index, sample in enumerate(['S1', 'S2', 'S3', 'S4']):
    batch = 'batch-A' if sample_index < 2 else 'batch-B'
    for truth, cluster, count in design:
        for index in range(count):
            rate = np.full(120, 1.2 + sample_index * 0.03)
            if truth in marker_ranges:
                rate[list(marker_ranges[truth])] += 8.5
            else:
                rate[36:48] += 8.5
            rate[60:70] += 1.5 if batch == 'batch-A' else 0.0
            rate[70:80] += 1.5 if batch == 'batch-B' else 0.0
            query_rows.append(rng.poisson(rate))
            records.append({{'sample_id': sample, 'batch': batch, 'cluster': cluster, 'existing_label': 'unknown', 'evaluation_truth': truth}})
            query_cells.append(f'{{sample}}-{{truth}}-{{index:03d}}')
query_counts = np.asarray(query_rows, dtype=np.int32)
query_adata = ad.AnnData(
    X=sparse.csr_matrix(np.log1p(query_counts)),
    obs=pd.DataFrame(records, index=query_cells),
    var=pd.DataFrame(index=genes),
)
query_adata.layers['counts'] = sparse.csr_matrix(query_counts)
query_adata.write_h5ad({str(query)!r})

markers = {{
    'T_cell': {{'positive': ['GENE000', 'GENE001', 'GENE002', 'GENE003'], 'negative': ['GENE012', 'GENE024']}},
    'B_cell': {{'positive': ['GENE012', 'GENE013', 'GENE014', 'GENE015'], 'negative': ['GENE000', 'GENE024']}},
    'Myeloid': {{'positive': ['GENE024', 'GENE025', 'GENE026', 'GENE027'], 'negative': ['GENE000', 'GENE012']}},
}}
with open({str(marker_panel)!r}, 'w', encoding='utf-8') as handle: json.dump(markers, handle, sort_keys=True)
ontology = {{
    'label_to_ontology': {{'T_cell': 'CL:0000084', 'B_cell': 'CL:0000236', 'Myeloid': 'CL:0000763'}},
    'parents': {{'CL:0000084': ['CL:0000542'], 'CL:0000236': ['CL:0000542'], 'CL:0000542': ['CL:0000000'], 'CL:0000763': ['CL:0000000']}},
    'allowed_by_group': {{'cluster_T': ['CL:0000542'], 'cluster_B': ['CL:0000542'], 'cluster_M': ['CL:0000763'], 'cluster_unknown': ['CL:9999999']}},
}}
with open({str(ontology)!r}, 'w', encoding='utf-8') as handle: json.dump(ontology, handle, sort_keys=True)
"""
        run([str(python), "-c", fixture_code], environment)
        output = work / "annotated.h5ad"
        analysis_report_path = work / "analysis.json"
        run([
            str(python), str(PYTHON_TEMPLATE),
            "--query-h5ad", str(query), "--reference-h5ad", str(reference),
            "--output-h5ad", str(output), "--report", str(analysis_report_path),
            "--rscript", str(r_executable), "--query-raw-count-location", "layers.counts",
            "--reference-raw-count-location", "layers.counts", "--reference-label-key", "reference_label",
            "--query-group-key", "cluster", "--existing-label-key", "existing_label",
            "--evaluation-label-key", "evaluation_truth", "--unknown-label", "unknown",
            "--marker-panel", str(marker_panel), "--ontology-contract", str(ontology),
            "--minimum-common-genes", "100", "--minimum-query-gene-fraction", "0.8",
            "--minimum-delta-next", "0.05", "--minimum-group-consensus", "0.8",
            "--minimum-positive-marker-support", "0.75", "--maximum-negative-marker-conflict", "0.25",
            "--minimum-marker-log-expression-difference", "0.4",
        ], environment)
        analysis = json.loads(analysis_report_path.read_text(encoding="utf-8"))
        groups = analysis["annotation"]["group_results"]
        if not (
            analysis["schema_version"] == 2
            and analysis["quality_status"] == "passed"
            and analysis["input"]["query_cells"] == 280
            and analysis["input"]["reference_cells"] == 180
            and analysis["input"]["common_genes"] == 120
            and analysis["annotation"]["accepted_cells"] == 240
            and analysis["annotation"]["unknown_cells"] == 40
            and analysis["evaluation"]["macro_f1"] == 1.0
            and analysis["evaluation"]["known_cell_accuracy"] == 1.0
            and analysis["evaluation"]["unknown_retention_fraction"] == 1.0
            and all(analysis["quality_gates"].values())
            and analysis["quality_gates"]["complete_finite_score_matrix"] is True
            and analysis["quality_gates"]["source_artifacts_immutable"] is True
            and all(groups[group]["accepted"] for group in ("cluster_T", "cluster_B", "cluster_M"))
            and groups["cluster_unknown"]["accepted"] is False
            and groups["cluster_unknown"]["quality_checks"]["ontology_allowed"] is False
        ):
            raise RuntimeError(f"reference annotation failed expected scientific behavior: {json.dumps(analysis, sort_keys=True)[:5000]}")
        versions = analysis["versions"]
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        return {
            "schema_version": 1, "passed": True, "module_id": MODULE_ID, "module_version": MODULE_VERSION,
            "compatibility_row_id": ROW_ID,
            "registry_digest": registry.digest,
            "templates": {
                "annotate_reference": {"name": PYTHON_TEMPLATE.name, "sha256": sha256(PYTHON_TEMPLATE)},
                "run_singler": {"name": R_TEMPLATE.name, "sha256": sha256(R_TEMPLATE)},
            },
            "tool_versions": {"SingleR": versions["SingleR"], "scanpy": versions["scanpy"]},
            "dependency_versions": {key: versions[key] for key in ("python", "anndata", "numpy", "pandas", "scipy", "scikit-learn", "r", "Matrix", "BiocParallel", "jsonlite")},
            "fixture": {"query_sha256": sha256(query), "reference_sha256": sha256(reference), "query_cells": 280, "reference_cells": 180, "genes": 120, "known_query_cells": 240, "unknown_query_cells": 40},
            "execution": {"singler_completed": True, "output_sha256": sha256(output), "analysis_report_sha256": sha256(analysis_report_path)},
            "results": {
                "accepted_cells": analysis["annotation"]["accepted_cells"], "unknown_cells": analysis["annotation"]["unknown_cells"],
                "macro_f1": analysis["evaluation"]["macro_f1"], "known_cell_accuracy": analysis["evaluation"]["known_cell_accuracy"],
                "unknown_retention_fraction": analysis["evaluation"]["unknown_retention_fraction"],
                "unknown_group_blocking_gates": [key for key, passed in groups["cluster_unknown"]["quality_checks"].items() if not passed],
            },
            "scientific_summary": {
                "singler_reference_mapping_executed": True, "marker_contracts_applied": True,
                "ontology_ancestor_constraints_applied": True, "unknown_population_retained": True,
                "existing_labels_and_raw_counts_preserved": True, "evaluation_labels_posthoc_only": True,
                "annotated_h5ad_reloaded": True, "complete_finite_score_matrix_retained": True,
                "all_source_artifacts_immutable": True,
                "no_environment_or_compute_infrastructure_managed": True,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--rscript", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.scientific_python, args.rscript)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": MODULE_ID, "passed": True, "accepted_cells": report["results"]["accepted_cells"], "unknown_cells": report["results"]["unknown_cells"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
