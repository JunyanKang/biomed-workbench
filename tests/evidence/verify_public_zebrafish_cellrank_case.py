#!/usr/bin/env python3
"""Validate CellRank fate mapping on the accepted zebrafish RegVelo output."""

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
from scipy import sparse


ROOT = Path(__file__).resolve().parents[2]
MODULE_ID = "single-cell-fate-mapping"
MODULE_VERSION = "1.1.0"
ROW_ID = "agent-protocol-2-cellrank-232-moscot-051-velocity"
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
TEMPLATE = MODULE_ROOT / "templates" / "run_cellrank_fate.py"
UPSTREAM_REPORT = ROOT / "reports" / "public-case-zebrafish-regvelo.json"

SOURCE_SHA256 = "eccab081c44cfe335b726aec8172bbcda072241b4f006f6420bb5d46d39611cb"
EXPECTED_SHAPE = (697, 1008)
TERMINAL_STATES = (
    "mNC_head_mesenchymal",
    "mNC_arch2",
    "mNC_hox34",
    "Pigment",
)
TERMINAL_COUNTS = {
    "mNC_head_mesenchymal": 62,
    "mNC_arch2": 61,
    "mNC_hox34": 51,
    "Pigment": 56,
}
STAGE_NUMERIC = {
    "3ss": 3.0,
    "6-7ss": 6.5,
    "10ss": 10.0,
    "12-13ss": 12.5,
    "17-18ss": 17.5,
    "21-22ss": 21.5,
}
CONNECTIVITY_WEIGHT = 0.2
MINIMUM_STAGE_DELTA = 0.0
MINIMUM_SENSITIVITY_PEARSON = 0.95
MAXIMUM_SENSITIVITY_ABSOLUTE_DIFFERENCE = 0.15


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def matrix_values(matrix) -> np.ndarray:
    if sparse.issparse(matrix):
        return matrix.data
    return np.asarray(matrix).reshape(-1)


def validate_upstream_report() -> dict[str, object]:
    report = json.loads(UPSTREAM_REPORT.read_text(encoding="utf-8"))
    if (
        report.get("passed") is not True
        or report.get("case_id")
        != "zebrafish-neural-crest-regvelo-public-data-v1"
        or report.get("source", {}).get("sha256") != SOURCE_SHA256
        or report.get("module", {}).get("id")
        != "single-cell-regulatory-velocity"
        or report.get("runtime", {}).get("regvelo") != "0.4.2"
        or report.get("execution", {})
        .get("withheld_stage_direction", {})
        .get("gate")
        != "pass"
        or report.get("execution", {}).get("mode_sensitivity_status")
        != "warning-no-robustness-claim"
    ):
        raise RuntimeError("upstream RegVelo public-data evidence is not admitted")
    return report


def validate_regvelo_artifact(source: ad.AnnData) -> dict[str, object]:
    if source.shape != EXPECTED_SHAPE:
        raise RuntimeError("RegVelo public artifact shape changed")
    if not source.obs_names.is_unique or not source.var_names.is_unique:
        raise RuntimeError("RegVelo public artifact identifiers are not unique")
    if not {"stage", "cell_type"} <= set(source.obs):
        raise RuntimeError("RegVelo public artifact lacks withheld annotations")
    if not {
        "regvelo_velocity",
        "regvelo_latent_time",
        "spliced",
        "unspliced",
    } <= set(source.layers):
        raise RuntimeError("RegVelo public artifact lacks admitted dynamics layers")
    if "X_regvelo" not in source.obsm:
        raise RuntimeError("RegVelo public artifact lacks its latent representation")
    metadata = source.uns.get("biomed_regulatory_velocity", {})
    if (
        metadata.get("engine") != "RegVelo"
        or metadata.get("engine_version") != "0.4.2"
        or metadata.get("primary_run") != "hard-seed-2026"
        or metadata.get("layer_semantics") != "nonnegative-continuous"
        or metadata.get("experimental_labels_used_for_fitting") is not False
    ):
        raise RuntimeError("RegVelo public artifact provenance changed")
    expression = matrix_values(source.X)
    velocity = matrix_values(source.layers["regvelo_velocity"])
    representation = np.asarray(source.obsm["X_regvelo"])
    if (
        not expression.size
        or not np.isfinite(expression).all()
        or expression.min() < 0
        or np.allclose(expression, np.rint(expression), rtol=0, atol=1e-8)
        or not velocity.size
        or not np.isfinite(velocity).all()
        or not np.any(velocity < 0)
        or not np.any(velocity > 0)
        or representation.shape != (EXPECTED_SHAPE[0], 10)
        or not np.isfinite(representation).all()
    ):
        raise RuntimeError("RegVelo state, velocity, or representation semantics changed")
    observed_counts = {
        state: int((source.obs["cell_type"].astype(str) == state).sum())
        for state in TERMINAL_STATES
    }
    if observed_counts != TERMINAL_COUNTS:
        raise RuntimeError("official tutorial terminal-state cell counts changed")
    if set(source.obs["stage"].astype(str)) != set(STAGE_NUMERIC):
        raise RuntimeError("zebrafish stage labels changed")
    return {
        "cells": int(source.n_obs),
        "features": int(source.n_vars),
        "expression_semantics": "log-normalized-continuous",
        "velocity_finite_signed": True,
        "latent_representation_shape": list(representation.shape),
        "terminal_state_counts": observed_counts,
        "regvelo_primary_run": metadata["primary_run"],
        "regvelo_modes": list(metadata["model_modes"]),
    }


def run_template(
    input_h5ad: Path,
    work: Path,
    run_name: str,
    connectivity_weight: float,
) -> tuple[dict[str, object], ad.AnnData, pd.DataFrame]:
    run_root = work / run_name
    run_root.mkdir()
    output_h5ad = run_root / "cellrank.h5ad"
    fate_table = run_root / "fates.tsv"
    driver_table = run_root / "drivers.tsv"
    report_path = run_root / "analysis.json"
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
            "--output-h5ad",
            str(output_h5ad),
            "--fate-table",
            str(fate_table),
            "--driver-table",
            str(driver_table),
            "--report",
            str(report_path),
            "--expression-location",
            "X",
            "--expression-semantics",
            "log-normalized-continuous",
            "--time-key",
            "stage_numeric",
            "--terminal-state-key",
            "cell_type",
            "--terminal-states",
            ",".join(TERMINAL_STATES),
            "--mode",
            "velocity",
            "--state-location",
            "X",
            "--velocity-location",
            "layers.regvelo_velocity",
            "--representation-key",
            "X_regvelo",
            "--velocity-model",
            "deterministic",
            "--connectivity-weight",
            str(connectivity_weight),
            "--n-top-genes",
            "1000",
            "--n-pcs",
            "30",
            "--n-neighbors",
            "30",
            "--ot-epsilon",
            "0.05",
            "--ot-threshold",
            "0.001",
            "--minimum-terminal-own-fate",
            "0.9",
            "--minimum-terminal-cells",
            "20",
            "--minimum-time-direction",
            str(MINIMUM_STAGE_DELTA),
            "--seed",
            "0",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=1200,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "packaged CellRank public case failed: "
            f"{completed.stderr[-4000:]}"
        )
    return (
        json.loads(report_path.read_text(encoding="utf-8")),
        ad.read_h5ad(output_h5ad),
        pd.read_csv(fate_table, sep="\t"),
    )


def exact_array(left, right) -> dict[str, object]:
    left_array = left.toarray() if sparse.issparse(left) else np.asarray(left)
    right_array = right.toarray() if sparse.issparse(right) else np.asarray(right)
    difference = np.abs(left_array - right_array)
    return {
        "shape": list(left_array.shape),
        "exactly_equal": bool(np.array_equal(left_array, right_array)),
        "maximum_absolute_difference": float(difference.max(initial=0)),
    }


def compare_sensitivity(
    pure: ad.AnnData,
    blended: ad.AnnData,
    labels: pd.Series,
) -> dict[str, object]:
    pure_fate = np.asarray(pure.obsm["biomed_fate_probabilities"])
    blended_fate = np.asarray(blended.obsm["biomed_fate_probabilities"])
    terminal_mask = labels.astype(str).isin(TERMINAL_STATES).to_numpy()
    transient_mask = ~terminal_mask
    if not transient_mask.any():
        raise RuntimeError("public fate case contains no transient cells")
    pure_transient = pure_fate[transient_mask]
    blended_transient = blended_fate[transient_mask]
    correlation = float(
        np.corrcoef(pure_transient.reshape(-1), blended_transient.reshape(-1))[0, 1]
    )
    maximum_difference = float(
        np.max(np.abs(pure_transient - blended_transient))
    )
    mean_difference = float(np.mean(np.abs(pure_transient - blended_transient)))
    assignment_agreement = float(
        np.mean(
            np.argmax(pure_transient, axis=1)
            == np.argmax(blended_transient, axis=1)
        )
    )
    lineage_correlations = {}
    for index, state in enumerate(TERMINAL_STATES):
        lineage_correlations[state] = float(
            np.corrcoef(
                pure_transient[:, index],
                blended_transient[:, index],
            )[0, 1]
        )
    passed = (
        correlation >= MINIMUM_SENSITIVITY_PEARSON
        and maximum_difference <= MAXIMUM_SENSITIVITY_ABSOLUTE_DIFFERENCE
    )
    if not passed:
        raise RuntimeError("CellRank connectivity sensitivity exceeded frozen gates")
    return {
        "pure_velocity_weight": 1.0,
        "blended_velocity_weight": 1.0 - CONNECTIVITY_WEIGHT,
        "blended_connectivity_weight": CONNECTIVITY_WEIGHT,
        "transient_cells": int(transient_mask.sum()),
        "flattened_fate_pearson": correlation,
        "maximum_absolute_fate_difference": maximum_difference,
        "mean_absolute_fate_difference": mean_difference,
        "maximum_fate_assignment_agreement": assignment_agreement,
        "lineage_fate_pearson": lineage_correlations,
        "thresholds": {
            "minimum_flattened_fate_pearson": MINIMUM_SENSITIVITY_PEARSON,
            "maximum_absolute_fate_difference": (
                MAXIMUM_SENSITIVITY_ABSOLUTE_DIFFERENCE
            ),
        },
        "gate": "pass",
    }


def verify(regvelo_h5ad: Path) -> dict[str, object]:
    upstream = validate_upstream_report()
    source_path = regvelo_h5ad.resolve(strict=True)
    source_digest = sha256(source_path)
    source = ad.read_h5ad(source_path)
    artifact_validation = validate_regvelo_artifact(source)
    with tempfile.TemporaryDirectory(
        prefix="biomed-public-zebrafish-cellrank-"
    ) as temporary:
        work = Path(temporary)
        input_h5ad = work / "zebrafish-regvelo-cellrank-input.h5ad"
        derived = source.copy()
        derived.obs["stage_numeric"] = [
            STAGE_NUMERIC[str(value)] for value in derived.obs["stage"]
        ]
        derived.write_h5ad(input_h5ad, compression="gzip")
        pure_report, pure_output, pure_fates = run_template(
            input_h5ad,
            work,
            "pure-a",
            0.0,
        )
        repeat_report, repeat_output, repeat_fates = run_template(
            input_h5ad,
            work,
            "pure-b",
            0.0,
        )
        blend_report, blend_output, _ = run_template(
            input_h5ad,
            work,
            "velocity-connectivity",
            CONNECTIVITY_WEIGHT,
        )
        if sha256(source_path) != source_digest:
            raise RuntimeError("CellRank public case modified the RegVelo artifact")
        if any(
            report.get("quality_status") != "passed"
            for report in (pure_report, repeat_report, blend_report)
        ):
            raise RuntimeError("CellRank public execution failed a template gate")
        repeat = {
            "fate_probabilities": exact_array(
                pure_output.obsm["biomed_fate_probabilities"],
                repeat_output.obsm["biomed_fate_probabilities"],
            ),
            "transition_matrix": exact_array(
                pure_output.obsp["biomed_fate_transition"],
                repeat_output.obsp["biomed_fate_transition"],
            ),
        }
        fate_columns = [f"fate_{state}" for state in TERMINAL_STATES]
        repeat["fate_table"] = exact_array(
            pure_fates[fate_columns].to_numpy(),
            repeat_fates[fate_columns].to_numpy(),
        )
        if (
            pure_report["model"] != repeat_report["model"]
            or pure_report["results"] != repeat_report["results"]
            or not all(item["exactly_equal"] for item in repeat.values())
        ):
            raise RuntimeError("repeated CellRank fate mapping is not exact")
        stage_directions = {
            "pure_velocity": pure_report["results"][
                "expected_experimental_time_delta"
            ],
            "velocity_connectivity": blend_report["results"][
                "expected_experimental_time_delta"
            ],
        }
        if any(
            value is None or value <= MINIMUM_STAGE_DELTA
            for value in stage_directions.values()
        ):
            raise RuntimeError(
                "CellRank transition direction disagrees with withheld stage"
            )
        sensitivity = compare_sensitivity(
            pure_output,
            blend_output,
            source.obs["cell_type"],
        )
        terminal_consistency = pure_report["results"][
            "terminal_state_consistency"
        ]
        if set(terminal_consistency) != set(TERMINAL_STATES):
            raise RuntimeError("CellRank terminal-state outputs changed")
        runtime = pure_report["versions"]
        derived_digest = sha256(input_h5ad)

    return {
        "schema_version": 1,
        "passed": True,
        "case_id": "zebrafish-regvelo-cellrank-fate-public-data-v1",
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
            "official_h5ad_url": upstream["source"]["url"],
            "official_h5ad_sha256": SOURCE_SHA256,
            "upstream_case_id": upstream["case_id"],
            "upstream_report_sha256": sha256(UPSTREAM_REPORT),
            "regvelo_artifact_sha256": source_digest,
            "derived_cellrank_input_sha256": derived_digest,
            "validation": artifact_validation,
        },
        "design": {
            "primary_kernel": "CellRank VelocityKernel",
            "state_location": "X",
            "state_semantics": "log-normalized-continuous",
            "velocity_location": "layers.regvelo_velocity",
            "velocity_source": "RegVelo 0.4.2 hard-seed-2026",
            "representation": "X_regvelo",
            "neighbors": 30,
            "terminal_state_source": "official RegVelo tutorial annotations",
            "terminal_states": list(TERMINAL_STATES),
            "withheld_direction_field": "developmental stage",
            "stage_used_for_kernel_or_terminal_assignment": False,
            "sample_or_donor_replication_available": False,
        },
        "runtime": runtime,
        "execution": {
            "independent_template_runs": 3,
            "pure_velocity_runs": 2,
            "velocity_connectivity_runs": 1,
            "deterministic_repeat": repeat,
            "withheld_stage_direction": {
                "stage_mapping": STAGE_NUMERIC,
                "minimum_expected_delta": MINIMUM_STAGE_DELTA,
                "expected_deltas": stage_directions,
                "stage_used_for_fitting": False,
                "gate": "pass",
            },
            "connectivity_sensitivity": sensitivity,
            "terminal_state_consistency": terminal_consistency,
            "lineage_driver_rows": int(pure_report["results"]["driver_rows"]),
            "source_expression_preserved": pure_report["quality_gates"][
                "source_expression_preserved"
            ],
            "outputs_reloaded": pure_report["quality_gates"]["outputs_reloaded"],
        },
        "quality_gates": {
            "admitted_upstream_regvelo_public_case": "pass-with-warning",
            "regvelo_artifact_identity_and_semantics": "pass",
            "cellrank_232_velocity_kernel_execution": "pass",
            "transition_and_fate_stochasticity": "pass",
            "withheld_developmental_stage_direction": "pass",
            "deterministic_repeat_execution": "pass",
            "velocity_connectivity_sensitivity": "pass",
            "terminal_state_consistency": "pass-not-independent",
            "source_immutability_and_output_reload": "pass",
        },
        "methods_not_run": {
            "automatic_terminal_state_discovery": "not-run",
            "macrostate_number_sensitivity": "not-run",
            "hard_vs_soft_regvelo_downstream_fate": "not-run",
            "scvelo_or_velovi_fate_baseline": "not-run",
            "regulator_perturbation_fate_screen": "not-run",
            "clonal_or_experimental_fate_validation": "not-run",
            "condition_or_donor_level_inference": "not-run",
        },
        "scientific_boundaries": [
            "This case validates a CellRank 2.3.2 fate workflow on one admitted RegVelo 0.4.2 zebrafish artifact; it does not establish portability to another dataset, velocity model, representation, neighborhood, or terminal-state definition.",
            "Developmental stage was withheld from RegVelo fitting and CellRank kernel construction and was used only after transitions were frozen to test expected forward direction.",
            "The four terminal states follow the official RegVelo tutorial and are annotation-defined rather than discovered independently.",
            "Terminal cells are clamped by GPCCA, so terminal-state consistency is an implementation check and not independent biological validation.",
            "The hard RegVelo velocity field is the primary input. Upstream hard-versus-soft disagreement remains a warning, and downstream hard-versus-soft fate robustness is not claimed.",
            "Connectivity-weight sensitivity passed the frozen software acceptance bounds but does not prove biological robustness or lineage ancestry.",
            "No donor or experimental replicate field is available, so no condition-level or population-level inferential claim is made.",
            "Lineage-driver statistics are retained as candidate associations and are not treated as validated regulators or causal mechanisms.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regvelo-h5ad", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "public-case-zebrafish-cellrank.json",
    )
    args = parser.parse_args()
    report = verify(args.regvelo_h5ad)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "case_id": report["case_id"],
                "passed": True,
                "cells": report["source"]["validation"]["cells"],
                "stage_deltas": report["execution"][
                    "withheld_stage_direction"
                ]["expected_deltas"],
                "sensitivity_pearson": report["execution"][
                    "connectivity_sensitivity"
                ]["flattened_fate_pearson"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
