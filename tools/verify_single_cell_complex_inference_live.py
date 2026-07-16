#!/usr/bin/env python3
"""Execute longitudinal dream and composition templates on a planted fixture."""

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


MODULE_ID = "single-cell-complex-inference"
MODULE_VERSION = "1.0.0"
ROW_ID = "agent-protocol-1-dream-1325-speckle-120"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
PREPARE = MODULE_ROOT / "templates" / "prepare_inference_inputs.py"
DREAM = MODULE_ROOT / "templates" / "fit_dream_longitudinal.R"
COMPOSITION = MODULE_ROOT / "templates" / "fit_composition_models.R"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], environment: dict[str, str], *, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command, cwd=ROOT, env=environment, capture_output=True, text=True,
        check=False, timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"complex inference command failed ({completed.returncode}): {' '.join(command[:3])}\n"
            f"stderr:\n{completed.stderr[-6000:]}\nstdout:\n{completed.stdout[-3000:]}"
        )
    return completed


def fixture_code(output: Path) -> str:
    return f"""
import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse

rng = np.random.default_rng(811)
genes = [f'GENE{{index:03d}}' for index in range(60)]
subjects = [f'S{{index + 1}}' for index in range(8)]
conditions = {{subject: ('control' if index < 4 else 'treated') for index, subject in enumerate(subjects)}}
sexes = {{subject: ('M' if index % 2 == 0 else 'F') for index, subject in enumerate(subjects)}}
cell_types = ('TypeA', 'TypeB', 'TypeC')
rows, metadata = [], []
cell_index = 0
for subject_index, subject in enumerate(subjects):
    condition = conditions[subject]
    subject_effect = np.exp((subject_index - 3.5) * 0.025)
    for time in (0.0, 1.0, 2.0):
        sample = f'{{subject}}_T{{int(time)}}'
        if condition == 'treated':
            cell_counts = {{'TypeA': 40 + int(10 * time), 'TypeB': 40 - int(8 * time), 'TypeC': 40 - int(2 * time)}}
        else:
            cell_counts = {{'TypeA': 40, 'TypeB': 40, 'TypeC': 40}}
        for cell_type in cell_types:
            for _ in range(cell_counts[cell_type]):
                rate = np.full(60, 1.8)
                start = {{'TypeA': 5, 'TypeB': 15, 'TypeC': 25}}[cell_type]
                rate[start:start + 6] += 3.0
                if cell_type == 'TypeA' and condition == 'treated':
                    rate[0:5] += 4.5 * time
                rate *= subject_effect
                rows.append(rng.poisson(rate).astype(np.int32))
                metadata.append({{
                    'sample': sample, 'subject': subject, 'cell_type': cell_type,
                    'condition': condition, 'time': time, 'sex': sexes[subject],
                }})
                cell_index += 1
counts = np.asarray(rows, dtype=np.int32)
adata = ad.AnnData(
    sparse.csr_matrix(counts),
    obs=pd.DataFrame(metadata, index=[f'cell-{{index:05d}}' for index in range(cell_index)]),
    var=pd.DataFrame(index=genes),
)
adata.layers['counts'] = adata.X.copy()
adata.write_h5ad({str(output)!r})
"""


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def inspect_outputs(python: Path, work: Path, environment: dict[str, str]) -> dict[str, object]:
    code = f"""
import json
import pandas as pd

linear = pd.read_csv({str(work / 'linear-results.tsv')!r}, sep='\\t')
spline = pd.read_csv({str(work / 'spline-results.tsv')!r}, sep='\\t')
composition = pd.read_csv({str(work / 'composition-results.tsv')!r}, sep='\\t')
linear_a = linear[(linear.cell_type == 'TypeA') & (linear.test_type == 'coefficient')].sort_values('p_value')
spline_a = spline[(spline.cell_type == 'TypeA') & (spline.test_type == 'joint')].sort_values('p_value')
primary = composition[composition.model == 'dream-logit-proportion'].set_index('cell_type')
print(json.dumps({{
  'linear_type_a_top_five': linear_a.head(5).gene_id.tolist(),
  'linear_type_a_effects': {{row.gene_id: float(row.log2_effect) for row in linear_a.head(5).itertuples()}},
  'linear_type_a_top_five_significant': bool(linear_a.head(5).significant.all()),
  'spline_type_a_joint_top_five': spline_a.head(5).gene_id.tolist(),
  'spline_type_a_joint_top_five_significant': bool(spline_a.head(5).significant.all()),
  'spline_joint_rows_per_cell_type': spline[spline.test_type == 'joint'].groupby('cell_type').size().to_dict(),
  'composition_primary_effects': {{cell_type: float(primary.loc[cell_type, 'transformed_effect']) for cell_type in primary.index}},
  'all_tables_reloaded': True,
}}))
"""
    return json.loads(run([str(python), "-c", code], environment).stdout)


def verify(scientific_python: Path, rscript: Path, r_library: Path) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    r_executable = rscript.expanduser().absolute()
    r_lib = r_library.expanduser().resolve(strict=True)
    if not python.exists() or not r_executable.exists() or not os.access(python, os.X_OK) or not os.access(r_executable, os.X_OK):
        raise RuntimeError("scientific Python and Rscript must be executable")

    with tempfile.TemporaryDirectory(prefix="biomed-complex-inference-") as temporary:
        work = Path(temporary)
        for name in ("home", "cache"):
            (work / name).mkdir()
        environment = {
            "PATH": str(python.parent) + os.pathsep + str(r_executable.parent) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(work / "home"), "XDG_CACHE_HOME": str(work / "cache"),
            "PYTHONHASHSEED": "0", "R_LIBS_USER": str(r_lib), "LANG": "C", "LC_ALL": "C",
        }
        source = work / "input.h5ad"
        run([str(python), "-c", fixture_code(source)], environment)
        source_digest = sha256(source)

        counts = work / "counts.tsv"
        pseudobulk = work / "pseudobulk.tsv"
        composition_input = work / "composition.tsv"
        prepare_report = work / "prepare.json"
        run([
            str(python), str(PREPARE), "--input-h5ad", str(source), "--raw-count-location", "layers.counts",
            "--sample-key", "sample", "--subject-key", "subject", "--cell-type-key", "cell_type",
            "--condition-key", "condition", "--time-key", "time", "--categorical-covariates", "sex",
            "--continuous-covariates", "none", "--require-longitudinal", "true",
            "--min-cells-per-pseudobulk", "20", "--min-library-size", "100",
            "--output-counts", str(counts), "--output-pseudobulk-metadata", str(pseudobulk),
            "--output-composition", str(composition_input), "--report", str(prepare_report),
        ], environment)

        common = [
            str(r_executable), str(DREAM), "--counts", str(counts), "--metadata", str(pseudobulk),
            "--variance-formula", "~ time + (1 | condition) + (1 | sex) + (1 | subject)",
            "--ddf", "adaptive", "--min-count", "2", "--min-samples-expressed", "4",
            "--min-subjects", "6", "--min-repeated-subjects", "6", "--fdr-threshold", "0.05",
        ]
        run(common + [
            "--results", str(work / "linear-results.tsv"), "--variance-results", str(work / "linear-variance.tsv"),
            "--diagnostics", str(work / "linear.json"), "--formula", "~ condition * time + sex + (1 | subject)",
            "--coefficient-pattern", "^conditiontreated:time$",
        ], environment)
        run(common + [
            "--results", str(work / "spline-results.tsv"), "--variance-results", str(work / "spline-variance.tsv"),
            "--diagnostics", str(work / "spline.json"), "--formula", "~ condition * ns(time, df = 2) + sex + (1 | subject)",
            "--coefficient-pattern", "^conditiontreated:ns[(]time, df = 2[)]",
        ], environment)

        composition_report = work / "composition.json"
        run([
            str(r_executable), str(COMPOSITION), "--composition", str(composition_input),
            "--results", str(work / "composition-results.tsv"), "--alr-results", str(work / "alr.tsv"),
            "--diagnostics", str(composition_report), "--formula", "~ condition * time + sex + (1 | subject)",
            "--coefficient-pattern", "^conditiontreated:time$", "--ddf", "adaptive",
            "--reference-cell-types", "TypeA,TypeB,TypeC", "--min-total-cells", "50", "--min-samples", "12",
            "--min-subjects", "6", "--min-repeated-subjects", "6", "--min-reference-support", "2",
            "--fdr-threshold", "0.05",
        ], environment)

        prepared = read_json(prepare_report)
        linear = read_json(work / "linear.json")
        spline = read_json(work / "spline.json")
        composition = read_json(composition_report)
        summary = inspect_outputs(python, work, environment)
        planted = {f"GENE{index:03d}" for index in range(5)}
        if sha256(source) != source_digest:
            raise RuntimeError("complex inference templates modified the source fixture")
        accounting = prepared["accounting"]
        if not all(accounting[key] for key in ("all_cells_accounted", "raw_counts_conserved", "composition_grid_complete", "sample_compositions_sum_to_one")):
            raise RuntimeError("cell, count, or composition accounting failed")
        if set(summary["linear_type_a_top_five"]) != planted or not summary["linear_type_a_top_five_significant"]:
            raise RuntimeError("linear longitudinal model did not recover the planted TypeA program")
        if set(summary["spline_type_a_joint_top_five"]) != planted or not summary["spline_type_a_joint_top_five_significant"]:
            raise RuntimeError("spline joint test did not recover the planted TypeA program")
        if not all(len(item["tested_coefficients"]) == 2 for item in spline["analyses"].values()):
            raise RuntimeError("spline verification did not fit and jointly test both basis coefficients")
        effects = summary["composition_primary_effects"]
        if effects["TypeA"] <= 0 or effects["TypeB"] >= 0:
            raise RuntimeError("composition primary model did not recover planted TypeA and TypeB directions")
        stability_items = composition["reference_stability"]
        if isinstance(stability_items, dict):
            stability_items = list(stability_items.values())
        stability_items = [item for group in stability_items for item in (group if isinstance(group, list) else [group])]
        stability = {item["cell_type"]: item for item in stability_items}
        if not stability["TypeA"]["admitted_reference_stable"] or not stability["TypeB"]["admitted_reference_stable"]:
            raise RuntimeError("planted composition effects were not stable across ALR references")
        if stability["TypeC"]["direction"] != "discordant" or stability["TypeC"]["admitted_reference_stable"]:
            raise RuntimeError("closure-related TypeC reference discordance was not preserved")
        for payload in (linear, spline, composition):
            quality = payload["quality"]
            if not quality.get("outputs_reloaded", quality.get("all_outputs_reloaded", False)):
                raise RuntimeError("one or more statistical outputs failed reload validation")

        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        return {
            "schema_version": 1, "passed": True, "module_id": MODULE_ID, "module_version": MODULE_VERSION,
            "compatibility_row_id": ROW_ID, "registry_digest": registry.digest,
            "templates": {
                "prepare": {"name": PREPARE.name, "sha256": sha256(PREPARE)},
                "dream": {"name": DREAM.name, "sha256": sha256(DREAM)},
                "composition": {"name": COMPOSITION.name, "sha256": sha256(COMPOSITION)},
            },
            "tool_versions": {"variancePartition": linear["versions"]["variancePartition"], "speckle": composition["versions"]["speckle"]},
            "dependency_versions": {
                "python": prepared["versions"]["python"], "anndata": prepared["versions"]["anndata"],
                "numpy": prepared["versions"]["numpy"], "pandas": prepared["versions"]["pandas"], "scipy": prepared["versions"]["scipy"],
                "r": linear["versions"]["R"], "edgeR": linear["versions"]["edgeR"], "limma": linear["versions"]["limma"],
                "lme4": linear["versions"]["lme4"], "lmerTest": linear["versions"]["lmerTest"],
                "BiocParallel": linear["versions"]["BiocParallel"], "jsonlite": linear["versions"]["jsonlite"], "digest": linear["versions"]["digest"],
            },
            "fixture": {"sha256": source_digest, "cells": prepared["input"]["cells"], "features": prepared["input"]["features"], "biological_samples": prepared["design"]["biological_samples"], "subjects": prepared["design"]["subjects"], "time_points": 3, "cell_types": 3},
            "execution": {"preparation_completed": True, "linear_dream_completed": True, "spline_dream_completed": True, "composition_completed": True, "outputs_reloaded": True},
            "model_summaries": {"linear": {"formula": linear["formula"], "cell_types": len(linear["analyses"]), "planted_top_five": summary["linear_type_a_top_five"]}, "spline": {"formula": spline["formula"], "cell_types": len(spline["analyses"]), "basis_coefficients_per_cell_type": 2, "planted_joint_top_five": summary["spline_type_a_joint_top_five"]}, "composition": {"primary_effects": effects, "reference_stability": stability}},
            "compatibility_observations": {"speckle_propeller_ttest_status": "excluded-after-observed-one-coefficient-dimension-drop", "propeller_backend_used": "propeller.anova-fixed-only-sensitivity", "primary_repeated_measure_backend": "variancePartition-dream"},
            "scientific_summary": {
                "biological_samples_used_as_replicates": True, "cells_not_used_as_replicates": True,
                "all_cells_and_counts_accounted": True, "subject_random_effect_enforced": True,
                "linear_longitudinal_effect_recovered": True, "nonlinear_spline_joint_test_executed": True,
                "variance_components_extracted": True, "complete_composition_grid_and_closure_checked": True,
                "repeated_measure_composition_effects_recovered": True, "propeller_fixed_only_sensitivity_explicit": True,
                "multi_reference_alr_sensitivity_completed": True, "reference_discordance_preserved": True,
                "outputs_reloaded": True, "no_environment_or_compute_infrastructure_managed": True,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--rscript", type=Path, required=True)
    parser.add_argument("--r-library", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.scientific_python, args.rscript, args.r_library)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": MODULE_ID, "passed": True, "tool_versions": report["tool_versions"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
