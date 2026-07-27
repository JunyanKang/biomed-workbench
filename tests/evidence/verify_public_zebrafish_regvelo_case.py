#!/usr/bin/env python3
"""Validate packaged RegVelo on the official zebrafish neural-crest dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import regvelo as rgv
import scanpy as sc
import scvelo as scv
from scipy import sparse
from scipy.stats import spearmanr


ROOT = Path(__file__).resolve().parents[2]
MODULE_ID = "single-cell-regulatory-velocity"
MODULE_VERSION = "1.1.0"
ROW_ID = "agent-protocol-1-regvelo-042-python-311-layer-semantics"
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
TEMPLATE = MODULE_ROOT / "templates" / "run_regvelo.py"

SOURCE_URL = "https://drive.google.com/uc?id=1Nzq1F6dGw-nR9lhRLfZdHOG7dcYq7P0i&export=download"
SOURCE_SHA256 = "eccab081c44cfe335b726aec8172bbcda072241b4f006f6420bb5d46d39611cb"
SOURCE_SHAPE = (697, 8012)
GRN_URL = "https://drive.google.com/uc?id=1ci_gCwdgGlZ0xSn6gSa_-LlIl9-aDa1c&export=download/"
GRN_SHA256 = "356bfde785af53e36f9334c4f5032c06f111d67d30b881b41e24a8ebde7a536a"
GRN_SHAPE = (4508, 4508)
DERIVED_SHAPE = (697, 1008)
EXPECTED_REGULATORS = 81
EXPECTED_EDGES = 4309
STAGE_ORDER = {
    "3ss": 0,
    "6-7ss": 1,
    "10ss": 2,
    "12-13ss": 3,
    "17-18ss": 4,
    "21-22ss": 5,
}
MINIMUM_STAGE_CELLS = 20


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def matrix_values(matrix) -> np.ndarray:
    return matrix.data if sparse.issparse(matrix) else np.asarray(matrix).reshape(-1)


def validate_source(source: ad.AnnData) -> dict[str, object]:
    if source.shape != SOURCE_SHAPE:
        raise RuntimeError("official zebrafish source shape changed")
    if not source.obs_names.is_unique or not source.var_names.is_unique:
        raise RuntimeError("official zebrafish identifiers are not unique")
    required_obs = {"stage", "cell_type"}
    required_var = {"is_tf"}
    required_layers = {"matrix", "spliced", "unspliced", "ambiguous"}
    if (
        not required_obs <= set(source.obs)
        or not required_var <= set(source.var)
        or not required_layers <= set(source.layers)
    ):
        raise RuntimeError("official zebrafish source lacks documented annotations or layers")
    layer_summary: dict[str, object] = {}
    for key in ("spliced", "unspliced"):
        values = matrix_values(source.layers[key])
        finite_nonnegative = bool(
            values.size and np.isfinite(values).all() and np.min(values) >= 0
        )
        integer_like = bool(np.allclose(values, np.rint(values), rtol=0, atol=1e-8))
        if not finite_nonnegative or integer_like:
            raise RuntimeError(
                "official zebrafish splicing layers do not demonstrate the declared continuous semantics"
            )
        layer_summary[key] = {
            "finite_nonnegative": True,
            "integer_like": False,
            "minimum": float(values.min()),
            "maximum": float(values.max()),
        }
    stage_counts = {
        str(key): int(value)
        for key, value in source.obs["stage"].astype(str).value_counts().sort_index().items()
    }
    if set(stage_counts) != set(STAGE_ORDER):
        raise RuntimeError("official zebrafish developmental stages changed")
    return {
        "cells": int(source.n_obs),
        "features": int(source.n_vars),
        "unique_cells": True,
        "unique_features": True,
        "stages": stage_counts,
        "cell_type_count": int(source.obs["cell_type"].astype(str).nunique()),
        "splicing_layers": layer_summary,
    }


def validate_grn(grn: pd.DataFrame) -> dict[str, object]:
    if grn.shape != GRN_SHAPE or not grn.index.is_unique or not grn.columns.is_unique:
        raise RuntimeError("official zebrafish GRN identity or dimensions changed")
    if not grn.index.equals(grn.columns):
        raise RuntimeError("official zebrafish GRN axes are not identically ordered")
    values = grn.to_numpy()
    if not np.isfinite(values).all():
        raise RuntimeError("official zebrafish GRN contains nonfinite values")
    return {
        "shape": list(grn.shape),
        "unique_identifiers": True,
        "identical_axis_order": True,
        "finite": True,
        "nonzero_edges_before_query_alignment": int(np.count_nonzero(values)),
    }


def derive_official_input(
    source: ad.AnnData,
    source_grn: pd.DataFrame,
    h5ad_path: Path,
    grn_path: Path,
) -> dict[str, object]:
    cell_ids = source.obs_names.copy()
    stages = source.obs["stage"].copy()
    cell_types = source.obs["cell_type"].copy()
    work = source.copy()
    work.obs = work.obs.drop(columns=["stage", "cell_type"])
    sc.pp.neighbors(work, n_neighbors=30, n_pcs=50, random_state=0)
    scv.pp.moments(work)
    work = rgv.pp.preprocess_data(work)
    work = rgv.pp.set_prior_grn(work, source_grn.T)
    if work.shape != DERIVED_SHAPE or not np.array_equal(work.obs_names, cell_ids):
        raise RuntimeError("official RegVelo preprocessing changed expected cells or feature count")
    if "stage" in work.obs or "cell_type" in work.obs:
        raise RuntimeError("withheld biological labels became visible during preprocessing")
    work.obs["stage"] = stages.reindex(work.obs_names)
    work.obs["cell_type"] = cell_types.reindex(work.obs_names)
    if work.obs["stage"].isna().any() or work.obs["cell_type"].isna().any():
        raise RuntimeError("withheld biological labels did not restore by exact cell identity")
    regulators = work.var_names[work.var["is_tf"].astype(bool)]
    skeleton = pd.DataFrame(
        work.uns["skeleton"],
        index=work.var_names,
        columns=work.var_names,
    )
    target_by_regulator = skeleton.T.loc[:, regulators]
    edge_count = int(np.count_nonzero(target_by_regulator.to_numpy()))
    if len(regulators) != EXPECTED_REGULATORS or edge_count != EXPECTED_EDGES:
        raise RuntimeError("official RegVelo feature or regulatory-network derivation changed")
    layer_summary = {}
    for key in ("Ms", "Mu"):
        values = matrix_values(work.layers[key])
        if (
            not values.size
            or not np.isfinite(values).all()
            or np.min(values) < 0
            or np.max(values) > 1.00001
        ):
            raise RuntimeError("official RegVelo moment layer is outside declared semantics")
        layer_summary[key] = {
            "finite_nonnegative": True,
            "integer_like": bool(
                np.allclose(values, np.rint(values), rtol=0, atol=1e-8)
            ),
            "minimum": float(values.min()),
            "maximum": float(values.max()),
        }
    work.uns["biomed_public_derivation"] = {
        "source": "official RegVelo zebrafish_nc",
        "labels_removed_before_preprocessing_and_restored_after": True,
        "neighbors": 30,
        "principal_components": 50,
        "random_seed": 0,
        "moments": "scvelo-0.3.4-default",
        "preprocessing": "regvelo-0.4.2-default",
        "grn_correlation_filter": "regvelo-0.4.2-default",
        "grn_input_orientation": "official-regulators-by-targets",
        "grn_export_orientation": "targets-by-regulators",
    }
    work.write_h5ad(h5ad_path, compression="gzip")
    target_by_regulator.to_csv(grn_path, sep="\t", index_label="target")
    return {
        "cells": int(work.n_obs),
        "features": int(work.n_vars),
        "regulators": int(len(regulators)),
        "edges": edge_count,
        "splicing_layers": layer_summary,
        "labels_used_for_preprocessing": False,
        "labels_removed_before_preprocessing_and_restored_after": True,
        "parameters": {
            "neighbors": 30,
            "principal_components": 50,
            "random_seed": 0,
            "moments": "scvelo-0.3.4-default",
            "preprocessing": "regvelo-0.4.2-default",
            "grn_correlation_filter": "regvelo-0.4.2-default",
        },
        "derived_h5ad_sha256": sha256(h5ad_path),
        "derived_target_by_regulator_grn_sha256": sha256(grn_path),
    }


def run_template(
    input_h5ad: Path,
    prior_grn: Path,
    work: Path,
    run_name: str,
) -> tuple[dict[str, object], ad.AnnData]:
    run_root = work / run_name
    run_root.mkdir()
    output_h5ad = run_root / "zebrafish-regvelo-output.h5ad"
    model_dir = run_root / "models"
    analysis_path = run_root / "analysis.json"
    environment = dict(os.environ)
    for name, variable in (
        ("home", "HOME"),
        ("cache", "XDG_CACHE_HOME"),
        ("matplotlib", "MPLCONFIGDIR"),
    ):
        path = run_root / name
        path.mkdir()
        environment[variable] = str(path)
    environment["PYTHONHASHSEED"] = "0"
    completed = subprocess.run(
        [
            sys.executable,
            str(TEMPLATE),
            "--input-h5ad",
            str(input_h5ad),
            "--prior-grn-tsv",
            str(prior_grn),
            "--output-h5ad",
            str(output_h5ad),
            "--model-dir",
            str(model_dir),
            "--report",
            str(analysis_path),
            "--spliced-layer",
            "Ms",
            "--unspliced-layer",
            "Mu",
            "--layer-semantics",
            "nonnegative-continuous",
            "--model-modes",
            "hard,soft",
            "--repeats",
            "1",
            "--max-epochs",
            "20",
            "--batch-size",
            "128",
            "--n-latent",
            "10",
            "--n-hidden",
            "256",
            "--lambda-grn",
            "1.0",
            "--lambda-l1",
            "0.01",
            "--minimum-regulators",
            "50",
            "--minimum-edges",
            "1000",
            "--maximum-dense-bytes",
            "10000000",
            "--seed",
            "2026",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"packaged RegVelo public case failed: {completed.stderr[-3000:]}"
        )
    return (
        json.loads(analysis_path.read_text(encoding="utf-8")),
        ad.read_h5ad(output_h5ad),
    )


def withheld_stage_review(output: ad.AnnData) -> dict[str, object]:
    latent_time = output.layers["regvelo_latent_time"]
    if sparse.issparse(latent_time):
        latent_time = latent_time.toarray()
    per_cell = np.median(np.asarray(latent_time), axis=1)
    stages = output.obs["stage"].astype(str)
    counts = stages.value_counts()
    included_stages = [
        stage for stage in STAGE_ORDER if int(counts.get(stage, 0)) >= MINIMUM_STAGE_CELLS
    ]
    excluded_stages = [
        {
            "stage": stage,
            "cells": int(counts.get(stage, 0)),
            "reason": f"fewer-than-{MINIMUM_STAGE_CELLS}-cells",
        }
        for stage in STAGE_ORDER
        if stage not in included_stages
    ]
    mask = stages.isin(included_stages)
    observed = stages[mask].map(
        {stage: index for index, stage in enumerate(included_stages)}
    )
    correlation = spearmanr(observed.to_numpy(), per_cell[mask.to_numpy()])
    if (
        int(mask.sum()) != 695
        or not np.isfinite(correlation.statistic)
        or correlation.statistic < 0.5
        or correlation.pvalue >= 1e-20
    ):
        raise RuntimeError("RegVelo latent time failed withheld developmental-stage direction")
    summaries = {}
    for stage in STAGE_ORDER:
        values = per_cell[np.asarray(stages == stage)]
        summaries[stage] = {
            "cells": int(values.size),
            "mean": float(np.mean(values)),
            "median": float(np.median(values)),
        }
    return {
        "evidence_field": "stage",
        "used_for_fitting_or_preprocessing": False,
        "aggregation": "median-across-gene-resolved-latent-time",
        "minimum_cells_per_stage": MINIMUM_STAGE_CELLS,
        "included_stages": included_stages,
        "excluded_stages": excluded_stages,
        "included_cells": int(mask.sum()),
        "spearman_rho": float(correlation.statistic),
        "spearman_pvalue": float(correlation.pvalue),
        "stage_summaries": summaries,
        "gate": "pass",
    }


def verify(source_path: Path | None = None, grn_path: Path | None = None) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="biomed-public-zebrafish-regvelo-") as temporary:
        work = Path(temporary)
        source_file = (
            source_path.resolve(strict=True)
            if source_path
            else work / "adata_zebrafish_preprocessed.h5ad"
        )
        if source_path is None:
            rgv.datasets.zebrafish_nc(source_file)
        if sha256(source_file) != SOURCE_SHA256:
            raise RuntimeError("official zebrafish H5AD digest changed")
        source = ad.read_h5ad(source_file)
        source_validation = validate_source(source)

        grn_file = grn_path.resolve(strict=True) if grn_path else work / "prior_GRN.csv"
        if grn_path is None:
            source_grn = rgv.datasets.zebrafish_grn(grn_file)
        else:
            source_grn = pd.read_csv(grn_file, index_col=0)
        if sha256(grn_file) != GRN_SHA256:
            raise RuntimeError("official zebrafish GRN digest changed")
        grn_validation = validate_grn(source_grn)

        derived_h5ad = work / "zebrafish-regvelo-input.h5ad"
        derived_grn = work / "zebrafish-target-by-regulator.tsv"
        derivation = derive_official_input(
            source,
            source_grn,
            derived_h5ad,
            derived_grn,
        )
        source_digest_before = sha256(source_file)
        grn_digest_before = sha256(grn_file)
        analysis, output = run_template(derived_h5ad, derived_grn, work, "run-a")
        repeat_analysis, repeat_output = run_template(
            derived_h5ad,
            derived_grn,
            work,
            "run-b",
        )
        if sha256(source_file) != source_digest_before or sha256(grn_file) != grn_digest_before:
            raise RuntimeError("RegVelo public case modified an official source artifact")
        if (
            output.shape != DERIVED_SHAPE
            or analysis["input"]["layer_semantics"] != "nonnegative-continuous"
            or analysis["input"]["spliced_layer"] != "Ms"
            or analysis["input"]["unspliced_layer"] != "Mu"
            or analysis["prior_grn"]["regulators"] != EXPECTED_REGULATORS
            or analysis["prior_grn"]["edges"] != EXPECTED_EDGES
            or len(analysis["runs"]) != 2
            or {item["mode"] for item in analysis["runs"]} != {"hard", "soft"}
            or not all(item["model_reloaded"] for item in analysis["runs"])
            or not all(analysis["quality"].values())
        ):
            raise RuntimeError("RegVelo public output failed execution or reload gates")
        repeat_fields = {
            "velocity": ("layers", "regvelo_velocity"),
            "latent_time": ("layers", "regvelo_latent_time"),
            "latent_state": ("obsm", "X_regvelo"),
        }
        repeat_differences = {}
        for name, (container, key) in repeat_fields.items():
            left = output.layers[key] if container == "layers" else output.obsm[key]
            right = (
                repeat_output.layers[key]
                if container == "layers"
                else repeat_output.obsm[key]
            )
            if sparse.issparse(left):
                left = left.toarray()
            if sparse.issparse(right):
                right = right.toarray()
            difference = np.abs(np.asarray(left) - np.asarray(right))
            repeat_differences[name] = {
                "shape": list(np.asarray(left).shape),
                "maximum_absolute_difference": float(difference.max(initial=0)),
                "exactly_equal": bool(np.array_equal(left, right)),
            }
        if (
            analysis["parameters"] != repeat_analysis["parameters"]
            or analysis["runs"] != repeat_analysis["runs"]
            or analysis["stability"] != repeat_analysis["stability"]
            or not all(item["exactly_equal"] for item in repeat_differences.values())
        ):
            raise RuntimeError("repeated RegVelo training is not exactly reproducible")
        stage_review = withheld_stage_review(output)
        mode_comparisons = analysis["stability"]["pairwise_velocity_correlations"]
        if len(mode_comparisons) != 1 or not np.isfinite(
            mode_comparisons[0]["velocity_pearson"]
        ):
            raise RuntimeError("RegVelo public case lacks a finite hard-soft comparison")

    return {
        "schema_version": 1,
        "passed": True,
        "case_id": "zebrafish-neural-crest-regvelo-public-data-v1",
        "case_type": "public-data-end-to-end",
        "module": {
            "id": MODULE_ID,
            "version": MODULE_VERSION,
            "compatibility_row_id": ROW_ID,
            "manifest_sha256": sha256(MANIFEST),
            "template_sha256": sha256(TEMPLATE),
        },
        "source": {
            "publisher": "RegVelo authors",
            "dataset": "zebrafish neural crest Smart-seq3",
            "url": SOURCE_URL,
            "sha256": SOURCE_SHA256,
            "documented_shape": list(SOURCE_SHAPE),
            "validation": source_validation,
        },
        "prior_grn": {
            "publisher": "RegVelo authors",
            "description": "zebrafish neural crest multiome-derived prior network",
            "url": GRN_URL,
            "sha256": GRN_SHA256,
            "documented_shape": list(GRN_SHAPE),
            "source_orientation": "regulators-by-targets",
            "validation": grn_validation,
        },
        "derivation": derivation,
        "runtime": analysis["versions"],
        "parameters": analysis["parameters"],
        "execution": {
            "runs": analysis["runs"],
            "mode_comparisons": mode_comparisons,
            "mode_sensitivity_status": "warning-no-robustness-claim",
            "deterministic_repeat_execution": {
                "independent_template_runs": 2,
                "same_parameters_histories_and_mode_comparison": True,
                "outputs": repeat_differences,
                "gate": "pass",
            },
            "withheld_stage_direction": stage_review,
            "all_outputs_finite": analysis["quality"]["all_outputs_finite"],
            "models_saved_and_reloaded": analysis["quality"]["models_saved_and_reloaded"],
            "source_layers_preserved": analysis["quality"][
                "source_count_layers_preserved_in_output"
            ],
            "output_reloaded": analysis["quality"]["output_reloaded"],
        },
        "quality_gates": {
            "official_h5ad_digest_and_shape": "pass",
            "official_grn_digest_orientation_and_shape": "pass",
            "continuous_layer_semantics_explicit": "pass",
            "label_free_official_preprocessing": "pass",
            "feature_regulator_and_edge_accounting": "pass",
            "hard_and_soft_execution": "pass",
            "finite_velocity_latent_time_and_state": "pass",
            "model_persistence_and_output_reload": "pass",
            "withheld_developmental_stage_direction": "pass",
            "mode_sensitivity_retained": "pass-with-warning",
            "deterministic_repeat_execution": "pass",
            "official_source_immutability": "pass",
        },
        "methods_not_run": {
            "scvelo_or_velovi_method_advantage_baseline": "not-run",
            "cellrank_terminal_state_and_fate_sensitivity": "not-run",
            "regulator_perturbation_screen": "not-run",
            "experimental_perturbation_validation": "not-run",
        },
        "scientific_boundaries": [
            "The public case validates exact official artifacts and a recorded RegVelo 0.4.2 preprocessing and runtime profile; it does not establish portability to another assay, organism, quantifier, GRN, or dependency profile.",
            "Developmental stage and cell type were withheld from preprocessing and model fitting; stage was inspected only after outputs were frozen as independent directional evidence.",
            "The two-cell 3ss stage was excluded from the direction gate by the predeclared minimum-stage-size rule and is not interpreted.",
            "Hard-versus-soft velocity agreement is retained as a sensitivity warning, so this case does not claim mode-robust velocities or superiority to scVelo or VeloVI.",
            "No CellRank fate, terminal-state sensitivity, regulator perturbation, causal mechanism, or experimental validation claim is made.",
            "The official prior is multiome-derived and then filtered by the documented RegVelo preprocessing on the query expression data; it is not treated as wholly independent causal evidence.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-h5ad", type=Path)
    parser.add_argument("--source-grn", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "public-case-zebrafish-regvelo.json",
    )
    args = parser.parse_args()
    report = verify(args.source_h5ad, args.source_grn)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "case_id": report["case_id"],
                "passed": True,
                "cells": report["derivation"]["cells"],
                "features": report["derivation"]["features"],
                "stage_spearman_rho": report["execution"][
                    "withheld_stage_direction"
                ]["spearman_rho"],
                "mode_velocity_pearson": report["execution"]["mode_comparisons"][0][
                    "velocity_pearson"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
