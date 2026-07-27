#!/usr/bin/env python3
"""Evaluate scVI/scANVI with two label-withheld public GSE96583 donors."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score

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

MODULE_ID = "single-cell-generative-modeling"
ROW_ID = "agent-protocol-1-scvi-120-scanpy-1115-torch-241"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
TEMPLATE = MODULE_ROOT / "templates" / "train_scvi_scanvi.py"
QUERY_DONORS = {"1256", "1488"}
MAX_CELLS_PER_SAMPLE = 100
N_FEATURES = 2500
SEED = 437


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_sample_indices(obs: pd.DataFrame) -> np.ndarray:
    samples = obs["biological_sample"].astype(str).to_numpy()
    selected: list[int] = []
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


def label_blind_features(counts: sparse.csr_matrix, count: int) -> np.ndarray:
    detected = np.asarray((counts > 0).sum(axis=0)).ravel()
    totals = np.asarray(counts.sum(axis=0)).ravel()
    ranked = np.lexsort((np.arange(counts.shape[1]), -totals, -detected))
    return np.sort(ranked[:count])


def run_template(
    python: Path,
    input_path: Path,
    mode: str,
    work: Path,
    environment: dict[str, str],
) -> tuple[Path, dict[str, object]]:
    output = work / f"{mode}.h5ad"
    report_path = work / f"{mode}.json"
    completed = subprocess.run(
        [
            str(python),
            str(TEMPLATE),
            "--input-h5ad",
            str(input_path),
            "--output-h5ad",
            str(output),
            "--model-dir",
            str(work / f"{mode}-model"),
            "--report",
            str(report_path),
            "--mode",
            mode,
            "--raw-count-location",
            "layers.counts",
            "--batch-key",
            "donor",
            "--sample-key",
            "biological_sample",
            "--reviewed-label-key",
            "reviewed_cell_type",
            "--unknown-label",
            "Unknown",
            "--n-hidden",
            "64",
            "--n-latent",
            "10",
            "--n-layers",
            "1",
            "--dropout-rate",
            "0.1",
            "--gene-likelihood",
            "nb",
            "--scvi-epochs",
            "60",
            "--scanvi-epochs",
            "40",
            "--batch-size",
            "128",
            "--train-size",
            "0.9",
            "--holdout-fraction",
            "0.2",
            "--n-neighbors",
            "20",
            "--minimum-batch-entropy-gain",
            "0.0",
            "--maximum-label-purity-loss",
            "0.15",
            "--minimum-label-connectivity",
            "0.70",
            "--minimum-heldout-macro-f1",
            "0.70",
            "--suggestion-confidence",
            "0.60",
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
            f"public GSE96583 {mode} execution failed:\n"
            + completed.stdout[-1500:]
            + "\n"
            + completed.stderr[-4000:]
        )
    return output, json.loads(report_path.read_text(encoding="utf-8"))


def verify(source_dir: Path | None, scientific_python: Path) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    if not python.is_file() or not os.access(python, os.X_OK):
        raise RuntimeError("scientific Python is not executable")
    with tempfile.TemporaryDirectory(prefix="biomed-public-gse96583-generative-") as temporary:
        work = Path(temporary)
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
        obs["biological_sample"] = obs["donor"] + ":" + obs["condition"]
        selected = stable_sample_indices(obs)
        counts = counts[selected]
        obs = obs.iloc[selected].copy()
        selected_features = label_blind_features(counts, N_FEATURES)
        counts = counts[:, selected_features]
        publisher_truth = obs["cell_type"].astype(str).copy()
        query_mask = obs["donor"].isin(QUERY_DONORS).to_numpy()
        obs["reviewed_cell_type"] = publisher_truth
        obs.loc[query_mask, "reviewed_cell_type"] = "Unknown"
        obs = obs.drop(columns=["cell_type"])
        var_names = np.asarray(unique_gene_names(genes), dtype=object)[
            selected_features
        ]
        var = pd.DataFrame(
            {
                "ensembl_id": genes.iloc[selected_features, 0]
                .astype(str)
                .to_numpy()
            },
            index=var_names,
        )
        adata = ad.AnnData(X=counts.copy(), obs=obs, var=var)
        adata.layers["counts"] = counts.copy()
        input_path = work / "gse96583-generative-input.h5ad"
        adata.write_h5ad(input_path, compression="gzip")
        if (
            adata.shape != (1600, 2500)
            or obs["donor"].nunique() != 8
            or obs["biological_sample"].nunique() != 16
            or int(query_mask.sum()) != 400
            or "cell_type" in adata.obs
            or set(obs.loc[query_mask, "reviewed_cell_type"]) != {"Unknown"}
        ):
            raise RuntimeError("GSE96583 generative design differs from contract")

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
            ("matplotlib", "MPLCONFIGDIR"),
            ("cache", "XDG_CACHE_HOME"),
            ("home", "HOME"),
        ):
            directory = work / name
            directory.mkdir()
            environment[variable] = str(directory)

        outputs = {}
        reports = {}
        for mode in ("scvi", "scanvi"):
            outputs[mode], reports[mode] = run_template(
                python, input_path, mode, work, environment
            )
        scanvi_output = ad.read_h5ad(outputs["scanvi"])
        suggestions = (
            scanvi_output.obs["scanvi_suggested_label"].astype(str).to_numpy()
        )
        truth = publisher_truth.to_numpy()
        query_evaluation = {
            "cells": int(query_mask.sum()),
            "accuracy": float(accuracy_score(truth[query_mask], suggestions[query_mask])),
            "balanced_accuracy": float(
                balanced_accuracy_score(
                    truth[query_mask], suggestions[query_mask]
                )
            ),
            "macro_f1": float(
                f1_score(truth[query_mask], suggestions[query_mask], average="macro")
            ),
            "truth_counts": {
                str(key): int(value)
                for key, value in zip(
                    *np.unique(truth[query_mask], return_counts=True)
                )
            },
            "prediction_counts": {
                str(key): int(value)
                for key, value in zip(
                    *np.unique(suggestions[query_mask], return_counts=True)
                )
            },
        }
        eligible = sorted(
            mode
            for mode, report in reports.items()
            if report["quality_status"] == "passed"
        )
        blocked = {
            mode: [
                gate
                for gate, passed in report["quality_gates"].items()
                if not passed
            ]
            for mode, report in reports.items()
            if report["quality_status"] != "passed"
        }
        selected_mode = (
            "scanvi"
            if "scanvi" in eligible
            else ("scvi" if "scvi" in eligible else None)
        )
        source_digests_after = {name: sha256(path) for name, path in paths.items()}
        quality_gates = {
            "official_sources_immutable": "pass"
            if source_digests_before == source_digests_after
            else "fail",
            "label_blind_cell_and_feature_selection": "pass",
            "held_out_donor_labels_absent_from_input": "pass",
            "base_scvi_label_isolation": "pass"
            if all(
                report["design"][
                    "reviewed_labels_removed_before_base_scvi_training"
                ]
                for report in reports.values()
            )
            else "fail",
            "internal_hidden_label_validation": "pass"
            if reports["scanvi"]["heldout_annotation_metrics"]["macro_f1"] >= 0.70
            else "fail",
            "unseen_donor_prediction_accuracy": "pass"
            if query_evaluation["accuracy"] >= 0.90
            and query_evaluation["macro_f1"] >= 0.70
            else "fail",
            "admission_decision_matches_all_model_gates": "pass"
            if all(
                (report["quality_status"] == "passed")
                == all(report["quality_gates"].values())
                for report in reports.values()
            )
            else "fail",
            "no_forced_model_selection": "pass"
            if selected_mode is not None or not eligible
            else "fail",
            "source_output_and_model_reload": "pass"
            if all(
                report["source_immutable"]
                and report["cell_feature_and_source_metadata_identity_preserved"]
                and report["quality_gates"]["raw_counts_preserved"]
                and report["quality_gates"]["model_reload_valid"]
                and report["quality_gates"]["h5ad_reload_valid"]
                for report in reports.values()
            )
            else "fail",
        }
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        report = {
            "schema_version": 1,
            "case_id": "gse96583-heldout-donor-generative-modeling-v1",
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
                "validation": {
                    "selected_cells": adata.n_obs,
                    "selected_genes": adata.n_vars,
                    "donors": int(obs["donor"].nunique()),
                    "biological_samples": int(
                        obs["biological_sample"].nunique()
                    ),
                    "query_donors": sorted(QUERY_DONORS),
                    "query_cells": int(query_mask.sum()),
                    "metadata_barcode_normalizations": normalizations,
                },
            },
            "parameters": {
                "cell_selection": "up to 100 cells per donor-condition sample by stable SHA-256 order without labels",
                "feature_selection": "2500 genes ranked by detection count then total count without labels",
                "scvi_epochs": 60,
                "scanvi_epochs": 40,
                "n_hidden": 64,
                "n_latent": 10,
                "n_neighbors": 20,
                "minimum_batch_entropy_gain": 0.0,
                "maximum_label_purity_loss": 0.15,
                "minimum_label_connectivity": 0.70,
                "minimum_heldout_macro_f1": 0.70,
                "seed": SEED,
            },
            "runtime": reports["scanvi"]["versions"],
            "execution": {
                "mode_results": {
                    mode: {
                        "quality_status": item["quality_status"],
                        "metric_deltas": item["metric_deltas"],
                        "heldout_annotation_metrics": item[
                            "heldout_annotation_metrics"
                        ],
                        "quality_gates": item["quality_gates"],
                        "source_immutable": item["source_immutable"],
                    }
                    for mode, item in reports.items()
                },
                "heldout_query_donor_evaluation": query_evaluation,
                "eligible_modes": eligible,
                "blocked_modes": blocked,
                "selected_mode": selected_mode,
                "all_models_and_outputs_reloaded": True,
                "source_artifacts_immutable": source_digests_before
                == source_digests_after,
            },
            "quality_gates": quality_gates,
            "scientific_boundaries": [
                "Publisher labels for donors 1256 and 1488 are absent from the input H5AD and are joined only after both models and outputs are frozen.",
                "The base scVI model is trained on metadata from which reviewed labels are physically removed; scANVI sees only the six-donor training labels and its own deterministic internal holdout.",
                "A model is admitted only if every mixing, conservation, annotation, source, and reload gate passes; reviewable suggestions may be evaluated even when no model is selected.",
                "Donor is modeled as the batch only for representation and annotation benchmarking; raw counts and donor identities remain authoritative for donor-aware inference.",
                "This public result is source-, split-, runtime-, parameter-, and gate-specific and does not justify automatic annotation without review.",
            ],
        }
        if not report["passed"]:
            raise RuntimeError(
                "GSE96583 generative-modeling public gates failed: "
                + json.dumps(quality_gates, sort_keys=True)
            )
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "reports"
        / "public-case-gse96583-generative-modeling.json",
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
                "eligible_modes": report["execution"]["eligible_modes"],
                "selected_mode": report["execution"]["selected_mode"],
                "query_accuracy": report["execution"][
                    "heldout_query_donor_evaluation"
                ]["accuracy"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
