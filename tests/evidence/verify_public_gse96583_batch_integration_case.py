#!/usr/bin/env python3
"""Benchmark Harmony, Scanorama, and BBKNN on public crossed GSE96583 PBMCs."""

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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402
from tests.evidence.verify_public_gse96583_donor_case import (  # noqa: E402
    SOURCES,
    acquire_sources,
    extract_members,
    read_condition,
    unique_gene_names,
)

MODULE_ID = "single-cell-batch-integration"
ROW_ID = "agent-protocol-1-scanpy-1104-harmony-020-scanorama-174-bbknn-160"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
TEMPLATE = MODULE_ROOT / "templates" / "benchmark_integration.py"
METHODS = ("harmony", "scanorama", "bbknn")
MAX_CELLS_PER_SAMPLE = 400
SEED = 96583


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_sample_indices(obs: pd.DataFrame) -> np.ndarray:
    selected: list[int] = []
    samples = obs["biological_sample"].astype(str).to_numpy()
    for sample in sorted(set(samples)):
        candidates = np.flatnonzero(samples == sample)
        ranked = sorted(
            candidates,
            key=lambda index: hashlib.sha256(
                f"{SEED}:{obs.index[index]}".encode()
            ).hexdigest(),
        )
        selected.extend(ranked[:MAX_CELLS_PER_SAMPLE])
    return np.asarray(sorted(selected), dtype=int)


def run_template(
    python: Path,
    input_path: Path,
    method: str,
    output_path: Path,
    report_path: Path,
    environment: dict[str, str],
) -> None:
    completed = subprocess.run(
        [
            str(python),
            str(TEMPLATE),
            "--input-h5ad",
            str(input_path),
            "--output-h5ad",
            str(output_path),
            "--report",
            str(report_path),
            "--method",
            method,
            "--raw-count-location",
            "layers.counts",
            "--batch-key",
            "donor",
            "--sample-key",
            "biological_sample",
            "--evaluation-label-key",
            "evaluation_stratum",
            "--unknown-label",
            "Unknown",
            "--n-top-genes",
            "2500",
            "--n-pcs",
            "30",
            "--n-neighbors",
            "20",
            "--maximum-label-purity-loss",
            "0.10",
            "--minimum-batch-entropy-gain",
            "0.02",
            "--minimum-label-connectivity",
            "0.70",
            "--silhouette-max-cells",
            "5000",
            "--seed",
            str(SEED),
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
            f"GSE96583 {method} integration failed:\n"
            + completed.stdout[-1500:]
            + "\n"
            + completed.stderr[-4000:]
        )


def verify(source_dir: Path | None, scientific_python: Path) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    if not python.is_file():
        raise FileNotFoundError(f"scientific Python is absent: {python}")
    with tempfile.TemporaryDirectory(prefix="biomed-public-gse96583-integration-") as temp:
        work = Path(temp)
        paths = acquire_sources(
            work, source_dir.expanduser().resolve(strict=True) if source_dir else None
        )
        source_digests_before = {name: sha256(path) for name, path in paths.items()}
        members = extract_members(paths["archive"], work / "raw")
        metadata = pd.read_csv(paths["metadata"], sep="\t", index_col=0)
        genes = pd.read_csv(paths["genes"], sep="\t", header=None)

        matrices, observations = [], []
        normalizations = {}
        for condition in ("ctrl", "stim"):
            matrix, obs, normalization_count = read_condition(
                members[f"{condition}_matrix"],
                members[f"{condition}_barcodes"],
                metadata,
                condition,
            )
            matrices.append(matrix)
            observations.append(obs)
            normalizations[condition] = normalization_count
        counts = sparse.vstack(matrices, format="csr", dtype=np.int64)
        obs = pd.concat(observations)
        obs["donor"] = obs["donor"].astype(str)
        obs["condition"] = obs["condition"].astype(str)
        obs["biological_sample"] = (
            obs["donor"] + ":" + obs["condition"]
        )
        obs["evaluation_stratum"] = (
            obs["cell_type"].astype(str) + "|" + obs["condition"]
        )
        selected = stable_sample_indices(obs)
        counts = counts[selected, :]
        obs = obs.iloc[selected].copy()
        if (
            counts.shape[0] != len(obs)
            or obs["donor"].nunique() != 8
            or obs["biological_sample"].nunique() != 16
            or obs["condition"].nunique() != 2
        ):
            raise RuntimeError("GSE96583 crossed integration design failed accounting")
        stratum_batch_counts = pd.crosstab(
            obs["evaluation_stratum"], obs["donor"]
        )
        donors_per_stratum = (stratum_batch_counts > 0).sum(axis=1)
        if int(donors_per_stratum.min()) < 2:
            raise RuntimeError("a cell-type-condition stratum does not span donors")

        var = pd.DataFrame(
            {"ensembl_id": genes.iloc[:, 0].astype(str).tolist()},
            index=unique_gene_names(genes),
        )
        adata = ad.AnnData(X=counts.copy(), obs=obs, var=var)
        adata.layers["counts"] = counts.copy()
        adata.uns["evaluation_contract"] = {
            "labels_used_for_integration": False,
            "evaluation_stratum": "publisher cell type crossed with condition",
        }
        input_path = work / "gse96583-crossed-integration.h5ad"
        adata.write_h5ad(input_path, compression="gzip")

        environment = dict(os.environ)
        environment["PYTHONHASHSEED"] = "0"
        for variable in (
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
        ):
            environment[variable] = "1"
        for name, variable in (
            ("numba", "NUMBA_CACHE_DIR"),
            ("matplotlib", "MPLCONFIGDIR"),
            ("cache", "XDG_CACHE_HOME"),
        ):
            directory = work / name
            directory.mkdir()
            environment[variable] = str(directory)

        reports: dict[str, dict[str, object]] = {}
        outputs: dict[str, Path] = {}
        for method in METHODS:
            outputs[method] = work / f"{method}.h5ad"
            report_path = work / f"{method}.json"
            run_template(
                python,
                input_path,
                method,
                outputs[method],
                report_path,
                environment,
            )
            reports[method] = json.loads(report_path.read_text(encoding="utf-8"))

        # Counterfactual labels prove that evaluation labels do not alter fitting.
        counterfactual = adata.copy()
        counterfactual.obs["evaluation_stratum"] = np.random.default_rng(
            SEED
        ).permutation(counterfactual.obs["evaluation_stratum"].astype(str).to_numpy())
        counterfactual_path = work / "gse96583-counterfactual-labels.h5ad"
        counterfactual.write_h5ad(counterfactual_path, compression="gzip")
        counterfactual_output = work / "harmony-counterfactual.h5ad"
        counterfactual_report = work / "harmony-counterfactual.json"
        run_template(
            python,
            counterfactual_path,
            "harmony",
            counterfactual_output,
            counterfactual_report,
            environment,
        )
        observed_harmony = ad.read_h5ad(outputs["harmony"])
        altered_harmony = ad.read_h5ad(counterfactual_output)
        observed_embedding = np.asarray(observed_harmony.obsm["X_integrated"])
        altered_embedding = np.asarray(altered_harmony.obsm["X_integrated"])
        observed_pca = np.asarray(observed_harmony.obsm["X_pca"])
        altered_pca = np.asarray(altered_harmony.obsm["X_pca"])
        counterfactual_pca_max_absolute_difference = float(
            np.max(np.abs(observed_pca - altered_pca))
        )
        counterfactual_max_absolute_difference = float(
            np.max(np.abs(observed_embedding - altered_embedding))
        )
        label_invariant_embedding = (
            np.array_equal(observed_pca, altered_pca)
            and counterfactual_max_absolute_difference <= 1e-6
        )
        if not label_invariant_embedding:
            raise RuntimeError(
                "altering evaluation labels changed Harmony fitting beyond "
                "numerical tolerance; "
                f"pca_max_abs_diff={counterfactual_pca_max_absolute_difference:.12g}, "
                f"harmony_max_abs_diff={counterfactual_max_absolute_difference:.12g}"
            )

        baseline = reports["harmony"]["baseline_metrics"]
        if any(
            any(
                abs(float(report["baseline_metrics"][key]) - float(baseline[key]))
                > 1e-10
                for key in (
                    "batch_neighbor_entropy",
                    "label_neighbor_purity",
                    "mean_label_graph_connectivity",
                )
            )
            for report in reports.values()
        ):
            raise RuntimeError("integration methods did not share one frozen baseline")
        eligible = sorted(
            method
            for method, report in reports.items()
            if report["quality_status"] == "passed"
        )
        if not eligible:
            raise RuntimeError("no integration method passed frozen public gates")
        selected_method = max(
            eligible,
            key=lambda method: reports[method]["metric_deltas"][
                "batch_neighbor_entropy_gain"
            ],
        )
        selected_report = reports[selected_method]

        source_digests_after = {name: sha256(path) for name, path in paths.items()}
        method_results = {
            method: {
                "quality_status": report["quality_status"],
                "baseline_metrics": report["baseline_metrics"],
                "integrated_metrics": report["integrated_metrics"],
                "metric_deltas": report["metric_deltas"],
                "quality_gates": report["quality_gates"],
                "source_immutable": report["source_immutable"],
                "identity_preserved": report[
                    "cell_feature_and_metadata_identity_preserved"
                ],
                "reload_validated": report["reload_validation_passed"],
            }
            for method, report in reports.items()
        }
        quality_gates = {
            "source_identity_and_immutability": "pass"
            if source_digests_before == source_digests_after
            else "fail",
            "crossed_donor_condition_design": "pass",
            "cell_type_condition_strata_span_donors": "pass",
            "evaluation_labels_removed_before_backends": "pass"
            if all(
                report["design"][
                    "evaluation_label_removed_before_backend_execution"
                ]
                for report in reports.values()
            )
            else "fail",
            "counterfactual_label_invariance": "pass"
            if label_invariant_embedding
            else "fail",
            "one_frozen_baseline": "pass",
            "at_least_one_eligible_method": "pass" if eligible else "fail",
            "selected_batch_mixing_gain": "pass"
            if selected_report["metric_deltas"]["batch_neighbor_entropy_gain"]
            >= 0.02
            else "fail",
            "selected_biology_preserved": "pass"
            if selected_report["metric_deltas"]["label_neighbor_purity_loss"]
            <= 0.10
            and selected_report["integrated_metrics"][
                "mean_label_graph_connectivity"
            ]
            >= 0.70
            else "fail",
            "all_outputs_reloaded_and_counts_preserved": "pass"
            if all(
                report["reload_validation_passed"]
                and report["quality_gates"]["raw_counts_preserved"]
                for report in reports.values()
            )
            else "fail",
        }
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        versions = reports["harmony"]["versions"]
        report = {
            "schema_version": 1,
            "case_id": "gse96583-crossed-batch-integration-v1",
            "case_type": "public-data-end-to-end",
            "passed": set(quality_gates.values()) == {"pass"},
            "module": {
                "id": MODULE_ID,
                "version": registry.get(MODULE_ID).version,
                "compatibility_row_id": ROW_ID,
                "manifest_sha256": sha256(MANIFEST),
                "template_sha256": sha256(TEMPLATE),
                "registry_digest": registry.digest,
            },
            "source": {
                "accession": "GSE96583",
                "files": SOURCES,
                "source_validation": {
                    "published_singlets_with_cell_type": 24673,
                    "selected_cells": int(len(obs)),
                    "genes": int(adata.n_vars),
                    "donors": 8,
                    "conditions": 2,
                    "biological_samples": 16,
                    "evaluation_strata": int(obs["evaluation_stratum"].nunique()),
                    "minimum_donors_per_stratum": int(donors_per_stratum.min()),
                    "metadata_barcode_normalizations": normalizations,
                },
            },
            "parameters": {
                "sample_selection": "up to 400 cells per donor-condition sample by stable SHA-256 order without evaluation labels",
                "maximum_cells_per_sample": MAX_CELLS_PER_SAMPLE,
                "batch_key": "donor",
                "biological_sample_key": "donor:condition",
                "posthoc_evaluation_label": "publisher cell type crossed with condition",
                "methods": list(METHODS),
                "n_top_genes": 2500,
                "n_pcs": 30,
                "n_neighbors": 20,
                "maximum_label_purity_loss": 0.10,
                "minimum_batch_entropy_gain": 0.02,
                "minimum_label_connectivity": 0.70,
                "seed": SEED,
            },
            "runtime": versions,
            "execution": {
                "method_results": method_results,
                "eligible_methods": eligible,
                "blocked_methods": {
                    method: [
                        gate
                        for gate, passed in report["quality_gates"].items()
                        if not passed
                    ]
                    for method, report in reports.items()
                    if report["quality_status"] != "passed"
                },
                "selected_method": selected_method,
                "selection_rule": "maximum batch entropy gain among methods passing all frozen mixing, conservation, source, and reload gates",
                "counterfactual_harmony_embedding_numerically_invariant": label_invariant_embedding,
                "counterfactual_pca_exact": np.array_equal(
                    observed_pca, altered_pca
                ),
                "counterfactual_pca_max_absolute_difference": counterfactual_pca_max_absolute_difference,
                "counterfactual_max_absolute_difference": counterfactual_max_absolute_difference,
                "counterfactual_harmony_max_absolute_tolerance": 1e-6,
                "all_cells_accounted": all(
                    ad.read_h5ad(path, backed="r").n_obs == len(obs)
                    for path in outputs.values()
                ),
                "source_artifacts_immutable": source_digests_before
                == source_digests_after,
            },
            "quality_gates": quality_gates,
            "scientific_boundaries": [
                "Donor is treated as the integration batch while donor-condition remains the biological sample; condition is not declared as a batch.",
                "Publisher cell type crossed with condition is used only after each backend has completed, so conservation requires both identity and stimulation state.",
                "The template physically removes evaluation labels from backend-visible AnnData metadata before feature selection, PCA, Harmony, Scanorama, BBKNN, neighbors, and UMAP.",
                "Under a single-thread numerical runtime, a counterfactual label permutation produced an exactly identical PCA representation and a Harmony representation with maximum absolute difference no greater than 1e-6.",
                "Method eligibility is dataset- and parameter-specific; the selected method is not a universal recommendation and downstream donor-aware inference still uses raw counts.",
            ],
        }
        if not report["passed"]:
            raise RuntimeError(
                "GSE96583 batch integration failed frozen gates: "
                + json.dumps(quality_gates, sort_keys=True)
                + "\nmethods="
                + json.dumps(method_results, sort_keys=True)
            )
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "public-case-gse96583-batch-integration.json",
    )
    args = parser.parse_args()
    report = verify(args.source_dir, args.scientific_python)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "case_id": report["case_id"],
                "passed": report["passed"],
                "eligible_methods": report["execution"]["eligible_methods"],
                "selected_method": report["execution"]["selected_method"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
