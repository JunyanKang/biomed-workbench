#!/usr/bin/env python3
"""Execute donor-aware pseudobulk templates on a deterministic h5ad fixture."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
MODULE_ID = "single-cell-donor-inference"
MODULE_VERSION = "1.0.0"
ROW_ID = "agent-protocol-1-scanpy-110-edger-40-deseq2-142-limma-358"
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / MODULE_ID
AGGREGATE_TEMPLATE = MODULE_ROOT / "templates" / "pseudobulk_aggregate.py"
DIFFERENTIAL_TEMPLATE = MODULE_ROOT / "templates" / "donor_differential.R"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], *, environment: dict[str, str], timeout: int = 300) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=timeout, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"scientific template failed: {completed.stderr[-3000:]}")
    return completed


def read_results(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def numeric(value: str) -> float | None:
    if value in {"", "NA", "NaN"}:
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def bh_adjust(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    adjusted = [1.0] * len(values)
    running = 1.0
    total = len(values)
    for reverse_index in range(total - 1, -1, -1):
        original_index = order[reverse_index]
        rank = reverse_index + 1
        running = min(running, values[original_index] * total / rank)
        adjusted[original_index] = min(1.0, running)
    return adjusted


def validate_result(path: Path, engine: str) -> dict[str, object]:
    rows = read_results(path)
    expected_columns = {
        "gene_id", "cell_type", "engine", "log2_fold_change", "standard_error",
        "mean_expression", "statistic", "p_value", "fdr", "significant", "global_fdr",
    }
    if not rows or set(rows[0]) != expected_columns or any(row["engine"] != engine for row in rows):
        raise RuntimeError(f"{engine} result schema failed")
    if len({(row["gene_id"], row["cell_type"]) for row in rows}) != len(rows):
        raise RuntimeError(f"{engine} result identities are duplicated")
    finite = [(index, numeric(row["p_value"])) for index, row in enumerate(rows)]
    finite = [(index, value) for index, value in finite if value is not None]
    if not finite or any(value < 0 or value > 1 for _, value in finite):
        raise RuntimeError(f"{engine} p-values are invalid")
    expected_bh = bh_adjust([value for _, value in finite])
    for (index, _), expected in zip(finite, expected_bh):
        observed = numeric(rows[index]["global_fdr"])
        if observed is None or not math.isclose(observed, expected, rel_tol=1e-6, abs_tol=1e-6):
            raise RuntimeError(f"{engine} global BH values failed independent recomputation")

    effect_sets = {
        "T_cell": {f"GENE{i:03d}" for i in range(0, 8)},
        "B_cell": {f"GENE{i:03d}" for i in range(8, 16)},
    }
    summaries = {}
    for cell_type, genes in effect_sets.items():
        selected = [row for row in rows if row["cell_type"] == cell_type and row["gene_id"] in genes]
        effects = [numeric(row["log2_fold_change"]) for row in selected]
        effects = [value for value in effects if value is not None]
        significant = sum(str(row["significant"]).upper() == "TRUE" for row in selected)
        if len(effects) != len(genes) or statistics.median(effects) <= 1.0 or significant < 6:
            raise RuntimeError(f"{engine} did not recover the planted {cell_type} effect")
        summaries[cell_type] = {
            "median_planted_log2_fold_change": round(statistics.median(effects), 6),
            "significant_planted_genes": significant,
        }
    return {"rows": len(rows), "bh_recomputed": True, "planted_effects": summaries}


def verify(scientific_python: Path, rscript: Path) -> dict[str, object]:
    python = scientific_python.expanduser().resolve(strict=True)
    r_executable = rscript.expanduser().resolve(strict=True)
    if not python.is_file() or not os.access(python, os.X_OK):
        raise RuntimeError("scientific Python is not executable")
    if not r_executable.is_file() or not os.access(r_executable, os.X_OK):
        raise RuntimeError("Rscript is not executable")

    with tempfile.TemporaryDirectory(prefix="biomed-donor-inference-") as temporary:
        work = Path(temporary)
        for name in ("numba", "matplotlib", "cache", "home"):
            (work / name).mkdir()
        environment = {
            "PATH": str(python.parent) + os.pathsep + str(r_executable.parent) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(work / "home"),
            "NUMBA_CACHE_DIR": str(work / "numba"),
            "MPLCONFIGDIR": str(work / "matplotlib"),
            "XDG_CACHE_HOME": str(work / "cache"),
            "PYTHONHASHSEED": "0",
            "LANG": "C",
            "LC_ALL": "C",
        }
        fixture = work / "annotated-fixture.h5ad"
        fixture_code = f"""
import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse

rng = np.random.default_rng(2307)
samples = [f'S{{i:02d}}' for i in range(1, 9)]
conditions = {{sample: ('control' if index < 4 else 'treated') for index, sample in enumerate(samples)}}
sexes = {{sample: ('F' if index % 2 == 0 else 'M') for index, sample in enumerate(samples)}}
ages = {{sample: [30, 40, 35, 45][index % 4] for index, sample in enumerate(samples)}}
cell_types = ['T_cell', 'B_cell']
cells_per_group = 30
genes = [f'GENE{{i:03d}}' for i in range(80)]
counts = []
records = []
cell_ids = []
for sample_index, sample in enumerate(samples):
    donor_factor = 0.9 + sample_index * 0.025
    for cell_type in cell_types:
        for cell_index in range(cells_per_group):
            rate = np.full(len(genes), 2.2 * donor_factor)
            if conditions[sample] == 'treated' and cell_type == 'T_cell':
                rate[0:8] += 8.0
            if conditions[sample] == 'treated' and cell_type == 'B_cell':
                rate[8:16] += 8.0
            counts.append(rng.poisson(rate))
            records.append({{'sample_id': sample, 'cell_type': cell_type, 'condition': conditions[sample], 'sex': sexes[sample], 'age': ages[sample]}})
            cell_ids.append(f'{{sample}}-{{cell_type}}-{{cell_index:03d}}')
raw = np.asarray(counts, dtype=np.int32)
obs = pd.DataFrame(records, index=cell_ids)
var = pd.DataFrame(index=genes)
adata = ad.AnnData(X=sparse.csr_matrix(np.log1p(raw)), obs=obs, var=var)
adata.layers['counts'] = sparse.csr_matrix(raw)
adata.uns['annotation_provenance'] = {{'method': 'deterministic-validation-fixture', 'reviewed': True}}
adata.write_h5ad({str(fixture)!r})
"""
        run([str(python), "-c", fixture_code], environment=environment)

        counts = work / "pseudobulk-counts.tsv"
        metadata = work / "pseudobulk-metadata.tsv"
        accounting = work / "aggregation-accounting.json"
        run([
            str(python), str(AGGREGATE_TEMPLATE),
            "--input-h5ad", str(fixture), "--raw-count-location", "layers.counts",
            "--sample-key", "sample_id", "--cell-type-key", "cell_type", "--condition-key", "condition",
            "--covariates", "sex,age", "--subject-key", "none",
            "--min-cells-per-pseudobulk", "20", "--min-library-size", "1000",
            "--output-counts", str(counts), "--output-metadata", str(metadata), "--accounting-report", str(accounting),
        ], environment=environment)
        aggregation = json.loads(accounting.read_text(encoding="utf-8"))
        if not (
            aggregation["input"]["cells"] == 480
            and aggregation["input"]["features"] == 80
            and aggregation["accounting"]["pseudobulks"] == 16
            and aggregation["accounting"]["eligible_pseudobulks"] == 16
            and aggregation["accounting"]["all_cells_accounted"] is True
            and aggregation["accounting"]["raw_counts_conserved"] is True
            and all(item["eligible_pseudobulks"] == 8 for item in aggregation["cell_types"])
        ):
            raise RuntimeError("pseudobulk aggregation scientific validation failed")

        engine_files = {}
        engine_reports = {}
        result_summaries = {}
        for engine in ("edger", "deseq2", "limma-voom"):
            result_path = work / f"{engine}-results.tsv"
            report_path = work / f"{engine}-diagnostics.json"
            run([
                str(r_executable), str(DIFFERENTIAL_TEMPLATE),
                "--counts", str(counts), "--metadata", str(metadata),
                "--results", str(result_path), "--diagnostics", str(report_path),
                "--engine", engine, "--condition-column", "condition", "--reference-level", "control", "--contrast-level", "treated",
                "--cell-type-column", "cell_type", "--sample-column", "biological_sample", "--subject-column", "none",
                "--categorical-covariates", "sex", "--continuous-covariates", "age",
                "--min-replicates-per-group", "3", "--min-count", "10", "--min-samples-expressed", "3", "--fdr-threshold", "0.05",
            ], environment=environment)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            completed = [item for item in report["analyses"] if item["status"] == "completed"]
            if not (
                report["engine"] == engine
                and len(completed) == 2
                and all(item["samples"] == 8 and item["design_rank"] == len(item["design_columns"]) for item in completed)
                and all("age" in item["design_columns"] for item in completed)
                and all(item["group_counts"] == {"control": 4, "treated": 4} for item in completed)
                and report["design"]["categorical_covariates"] == "sex"
                and report["design"]["continuous_covariates"] == "age"
                and report["quality"]["cells_used_as_replicates"] is False
                and report["quality"]["all_completed_designs_full_rank"] is True
                and report["quality"]["result_reload_validated"] is True
            ):
                raise RuntimeError(f"{engine} design or reload validation failed")
            result_summaries[engine] = validate_result(result_path, engine)
            engine_reports[engine] = report
            engine_files[engine] = {
                "results_sha256": sha256(result_path),
                "diagnostics_sha256": sha256(report_path),
            }

        versions = engine_reports["edger"]["versions"]
        tool_versions = {
            "scanpy": aggregation["versions"]["scanpy"],
            "edgeR": versions["edgeR"],
            "DESeq2": versions["DESeq2"],
            "limma": versions["limma"],
        }
        dependency_versions = {
            "anndata": aggregation["versions"]["anndata"],
            "numpy": aggregation["versions"]["numpy"],
            "pandas": aggregation["versions"]["pandas"],
            "scipy": aggregation["versions"]["scipy"],
            "r": versions["R"],
            "jsonlite": versions["jsonlite"],
            "digest": versions["digest"],
        }
        return {
            "schema_version": 1,
            "passed": True,
            "module_id": MODULE_ID,
            "module_version": MODULE_VERSION,
            "compatibility_row_id": ROW_ID,
            "templates": {
                "pseudobulk_aggregate": {"name": AGGREGATE_TEMPLATE.name, "sha256": sha256(AGGREGATE_TEMPLATE)},
                "donor_differential": {"name": DIFFERENTIAL_TEMPLATE.name, "sha256": sha256(DIFFERENTIAL_TEMPLATE)},
            },
            "tool_versions": tool_versions,
            "dependency_versions": dependency_versions,
            "scientific_runtime": {
                "aggregation": aggregation["versions"],
                "inference": versions,
            },
            "fixture": {
                "sha256": sha256(fixture),
                "cells": 480,
                "features": 80,
                "biological_samples": 8,
                "cell_types": 2,
                "groups_per_condition": 4,
            },
            "execution": {
                "aggregation_completed": True,
                "edger_completed": True,
                "deseq2_completed": True,
                "limma_voom_completed": True,
                "pseudobulk_counts_sha256": sha256(counts),
                "pseudobulk_metadata_sha256": sha256(metadata),
                "aggregation_report_sha256": sha256(accounting),
                "engine_outputs": engine_files,
            },
            "result_summaries": result_summaries,
            "scientific_summary": {
                "all_cells_accounted": True,
                "raw_counts_conserved": True,
                "biological_replicates_per_condition": 4,
                "cells_used_as_replicates": False,
                "all_designs_full_rank": True,
                "categorical_and_continuous_covariates_validated": True,
                "all_result_files_reloaded": True,
                "global_bh_independently_recomputed": True,
                "planted_effect_direction_recovered_by_all_engines": True,
                "edger_deseq2_limma_voom_passed": True,
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
    print(json.dumps({"module_id": report["module_id"], "passed": True, "tool_versions": report["tool_versions"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
