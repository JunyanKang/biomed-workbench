#!/usr/bin/env python3
"""Benchmark doublet templates against withheld GSE96583 demultiplexing labels."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.metadata
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
from scipy.io import mmread
from sklearn.metrics import (
    average_precision_score,
    matthews_corrcoef,
    precision_recall_fscore_support,
    roc_auc_score,
)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402
from tools.verify_public_gse96583_donor_case import (  # noqa: E402
    ARCHIVE_MEMBERS,
    EXPECTED_MATRIX_SHAPES,
    EXPECTED_METADATA_ROWS,
    SOURCES,
    acquire_sources,
    extract_members,
    unique_gene_names,
)

MODULE_ID = "single-cell-doublet-detection"
ROW_ID = "agent-protocol-1-scrublet-023-scdblfinder-1160"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
SCRUBLET = MODULE_ROOT / "templates" / "run_scrublet.py"
SCDBLFINDER = MODULE_ROOT / "templates" / "run_scdblfinder.R"
EXPECTED_RATE = 0.10
SEED = 96583
LABEL_COUNTS = {
    "ctrl": {"ambs": 706, "doublet": 1598, "singlet": 12315},
    "stim": {"ambs": 511, "doublet": 1571, "singlet": 12364},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], environment: dict[str, str], timeout: int = 2400) -> None:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "GSE96583 doublet workflow failed:\n"
            + completed.stdout[-1500:]
            + "\n"
            + completed.stderr[-3500:]
        )


def align_library(
    matrix_path: Path,
    barcode_path: Path,
    metadata: pd.DataFrame,
    library: str,
) -> tuple[sparse.csr_matrix, pd.DataFrame, int]:
    with gzip.open(matrix_path, "rb") as handle:
        counts = sparse.csr_matrix(mmread(handle).transpose(), dtype=np.int64)
    with gzip.open(barcode_path, "rt", encoding="utf-8") as handle:
        barcodes = [line.strip() for line in handle if line.strip()]
    if counts.shape != (len(barcodes), EXPECTED_MATRIX_SHAPES[library][0]):
        raise RuntimeError(f"GSE96583 {library} barcode and matrix axes differ")

    obs = metadata.loc[metadata["stim"].eq(library), ["multiplets"]].copy()
    barcode_set = set(barcodes)
    normalized, normalized_count = [], 0
    for value in obs.index.astype(str):
        candidate = value
        if value not in barcode_set and value.endswith("-11") and value[:-1] in barcode_set:
            candidate = value[:-1]
            normalized_count += 1
        normalized.append(candidate)
    obs.index = normalized
    if len(obs) != len(barcodes) or not obs.index.is_unique or set(obs.index) != barcode_set:
        raise RuntimeError(f"GSE96583 {library} labels do not reconcile to barcodes")
    obs = obs.loc[barcodes]
    observed = obs["multiplets"].value_counts().to_dict()
    if observed != LABEL_COUNTS[library]:
        raise RuntimeError(f"GSE96583 {library} label counts changed: {observed}")
    obs["capture_library"] = library
    obs["cell_id"] = [f"{library}:{barcode}" for barcode in barcodes]
    obs.index = obs["cell_id"]
    return counts, obs, normalized_count


def write_tenx_directory(
    target: Path,
    matrix: Path,
    barcodes: Path,
    genes: pd.DataFrame,
) -> None:
    target.mkdir()
    os.symlink(matrix, target / "matrix.mtx.gz")
    os.symlink(barcodes, target / "barcodes.tsv.gz")
    with gzip.open(target / "features.tsv.gz", "wt", encoding="utf-8") as handle:
        for identifier, symbol in genes.iloc[:, :2].itertuples(index=False, name=None):
            handle.write(f"{identifier}\t{symbol}\tGene Expression\n")


def discrimination(
    frame: pd.DataFrame,
    score_column: str,
    call_column: str,
) -> dict[str, object]:
    labelled = frame.loc[frame["multiplets"].isin(["singlet", "doublet"])].copy()
    truth = labelled["multiplets"].eq("doublet").to_numpy()
    scores = labelled[score_column].astype(float).to_numpy()
    calls = labelled[call_column].astype(bool).to_numpy()
    precision, recall, f1, _ = precision_recall_fscore_support(
        truth, calls, average="binary", zero_division=0
    )
    return {
        "cells": int(len(labelled)),
        "published_doublets": int(truth.sum()),
        "prevalence": float(truth.mean()),
        "auroc": float(roc_auc_score(truth, scores)),
        "average_precision": float(average_precision_score(truth, scores)),
        "score_median_singlet": float(np.median(scores[~truth])),
        "score_median_doublet": float(np.median(scores[truth])),
        "called_doublets": int(calls.sum()),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "matthews_correlation": float(matthews_corrcoef(truth, calls)),
    }


def verify(
    source_dir: Path | None,
    scientific_python: Path,
    rscript: Path,
    r_libs: Path,
) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    r = rscript.expanduser().resolve(strict=True)
    libraries = r_libs.expanduser().resolve(strict=True)
    if not python.is_file():
        raise FileNotFoundError(f"scientific Python is absent: {python}")

    with tempfile.TemporaryDirectory(prefix="biomed-public-gse96583-doublet-") as temp:
        work = Path(temp)
        paths = acquire_sources(
            work, source_dir.expanduser().resolve(strict=True) if source_dir else None
        )
        source_digests_before = {key: sha256(path) for key, path in paths.items()}
        members = extract_members(paths["archive"], work / "raw")
        metadata = pd.read_csv(paths["metadata"], sep="\t", index_col=0)
        genes = pd.read_csv(paths["genes"], sep="\t", header=None)
        if (
            len(metadata) != EXPECTED_METADATA_ROWS
            or "multiplets" not in metadata
            or genes.shape != (35635, 2)
        ):
            raise RuntimeError("GSE96583 source identity differs from the frozen design")

        matrices: dict[str, sparse.csr_matrix] = {}
        observations: dict[str, pd.DataFrame] = {}
        normalizations: dict[str, int] = {}
        for library in ("ctrl", "stim"):
            matrix, obs, normalization_count = align_library(
                members[f"{library}_matrix"],
                members[f"{library}_barcodes"],
                metadata,
                library,
            )
            matrices[library] = matrix
            observations[library] = obs
            normalizations[library] = normalization_count

        combined_counts = sparse.vstack(
            [matrices["ctrl"], matrices["stim"]], format="csr", dtype=np.int64
        )
        labels = pd.concat([observations["ctrl"], observations["stim"]])
        if combined_counts.shape != (29065, 35635) or not labels.index.is_unique:
            raise RuntimeError("GSE96583 combined capture libraries failed accounting")

        # Publisher multiplet labels are intentionally withheld from method inputs.
        method_obs = labels[["capture_library"]].copy()
        var = pd.DataFrame(
            {"ensembl_id": genes.iloc[:, 0].astype(str).tolist()},
            index=unique_gene_names(genes),
        )
        input_h5ad = work / "gse96583-withheld-labels.h5ad"
        ad.AnnData(X=combined_counts, obs=method_obs, var=var).write_h5ad(
            input_h5ad, compression="gzip"
        )

        tenx: dict[str, Path] = {}
        for library in ("ctrl", "stim"):
            tenx[library] = work / f"tenx-{library}"
            write_tenx_directory(
                tenx[library],
                members[f"{library}_matrix"],
                members[f"{library}_barcodes"],
                genes,
            )

        environment = dict(os.environ)
        environment["R_LIBS_USER"] = str(libraries)
        environment["PYTHONHASHSEED"] = "0"
        for name, variable in (
            ("numba", "NUMBA_CACHE_DIR"),
            ("matplotlib", "MPLCONFIGDIR"),
            ("cache", "XDG_CACHE_HOME"),
        ):
            directory = work / name
            directory.mkdir()
            environment[variable] = str(directory)

        scrublet_h5ad = work / "scrublet.h5ad"
        scrublet_report = work / "scrublet-report.json"
        run(
            [
                str(python),
                str(SCRUBLET),
                "--input-h5ad",
                str(input_h5ad),
                "--output-h5ad",
                str(scrublet_h5ad),
                "--report",
                str(scrublet_report),
                "--raw-count-location",
                "X",
                "--sample-key",
                "capture_library",
                "--expected-doublet-rate",
                str(EXPECTED_RATE),
                "--n-prin-comps",
                "30",
                "--seed",
                str(SEED),
            ],
            environment,
        )

        sc_outputs: dict[str, Path] = {}
        sc_reports: dict[str, dict[str, object]] = {}
        for offset, library in enumerate(("ctrl", "stim")):
            sc_outputs[library] = work / f"scdblfinder-{library}.tsv"
            report_path = work / f"scdblfinder-{library}.json"
            run(
                [
                    str(r),
                    str(SCDBLFINDER),
                    "--input-mtx",
                    str(tenx[library]),
                    "--sample-id",
                    library,
                    "--output-tsv",
                    str(sc_outputs[library]),
                    "--report",
                    str(report_path),
                    "--expected-doublet-rate",
                    str(EXPECTED_RATE),
                    "--seed",
                    str(SEED + offset),
                ],
                environment,
            )
            sc_reports[library] = json.loads(report_path.read_text(encoding="utf-8"))

        scrublet = ad.read_h5ad(scrublet_h5ad)
        evidence = labels.copy()
        evidence["scrublet_score"] = scrublet.obs.loc[
            evidence.index, "scrublet_score"
        ].astype(float)
        evidence["scrublet_call"] = (
            scrublet.obs.loc[evidence.index, "scrublet_call"].astype(bool)
        )
        sc_frames = []
        for library in ("ctrl", "stim"):
            frame = pd.read_csv(sc_outputs[library], sep="\t")
            frame["cell_id"] = library + ":" + frame["cell_id"].astype(str)
            frame = frame.set_index("cell_id")
            frame["scDblFinder_call"] = frame["scDblFinder_class"].eq("doublet")
            sc_frames.append(frame)
        sc_evidence = pd.concat(sc_frames)
        if set(sc_evidence.index) != set(evidence.index):
            raise RuntimeError("scDblFinder cells do not reconcile to publisher labels")
        evidence["scDblFinder_score"] = sc_evidence.loc[
            evidence.index, "scDblFinder_score"
        ].astype(float)
        evidence["scDblFinder_call"] = sc_evidence.loc[
            evidence.index, "scDblFinder_call"
        ].astype(bool)

        metrics: dict[str, dict[str, object]] = {}
        for method, score, call in (
            ("scrublet", "scrublet_score", "scrublet_call"),
            ("scDblFinder", "scDblFinder_score", "scDblFinder_call"),
        ):
            metrics[method] = {"overall": discrimination(evidence, score, call)}
            for library in ("ctrl", "stim"):
                metrics[method][library] = discrimination(
                    evidence.loc[evidence["capture_library"].eq(library)], score, call
                )

        labelled = evidence.loc[
            evidence["multiplets"].isin(["singlet", "doublet"])
        ].copy()
        truth = labelled["multiplets"].eq("doublet")
        concordant_call = labelled["scrublet_call"] & labelled["scDblFinder_call"]
        baseline = float(truth.mean())
        concordant_prevalence = (
            float(truth.loc[concordant_call].mean()) if concordant_call.any() else 0.0
        )

        source_digests_after = {key: sha256(path) for key, path in paths.items()}
        method_quality = {}
        for method in ("scrublet", "scDblFinder"):
            overall = metrics[method]["overall"]
            method_quality[method] = (
                overall["auroc"] >= 0.55
                and overall["average_precision"] > overall["prevalence"]
                and overall["score_median_doublet"] > overall["score_median_singlet"]
                and all(metrics[method][library]["auroc"] >= 0.52 for library in ("ctrl", "stim"))
            )
        quality_gates = {
            "source_identity_and_immutability": "pass"
            if source_digests_before == source_digests_after
            else "fail",
            "all_cells_and_labels_accounted": "pass"
            if len(evidence) == 29065 and evidence.notna().all().all()
            else "fail",
            "labels_withheld_until_postfit": "pass",
            "ambiguous_labels_excluded_from_metrics": "pass",
            "scrublet_discrimination": "pass" if method_quality["scrublet"] else "fail",
            "scDblFinder_discrimination": "pass"
            if method_quality["scDblFinder"]
            else "fail",
            "concordant_call_enrichment": "pass"
            if concordant_prevalence > baseline
            else "fail",
            "no_automatic_cell_removal": "pass",
            "outputs_reloaded_and_identity_preserved": "pass",
        }
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        scrublet_payload = json.loads(scrublet_report.read_text(encoding="utf-8"))
        report = {
            "schema_version": 1,
            "case_id": "gse96583-doublet-detection-v1",
            "case_type": "public-data-end-to-end",
            "passed": set(quality_gates.values()) == {"pass"},
            "module": {
                "id": MODULE_ID,
                "version": registry.get(MODULE_ID).version,
                "compatibility_row_id": ROW_ID,
                "manifest_sha256": sha256(MANIFEST),
                "template_sha256": {
                    SCRUBLET.name: sha256(SCRUBLET),
                    SCDBLFINDER.name: sha256(SCDBLFINDER),
                },
                "registry_digest": registry.digest,
            },
            "source": {
                "accession": "GSE96583",
                "study": "Kang et al. multiplexed PBMC interferon response",
                "files": SOURCES,
                "source_validation": {
                    "published_cells": 29065,
                    "capture_libraries": 2,
                    "label_counts_by_library": LABEL_COUNTS,
                    "metadata_barcode_normalizations": normalizations,
                },
            },
            "parameters": {
                "expected_doublet_rate": EXPECTED_RATE,
                "rate_rationale": "predeclared pooled 10x loading-context prior",
                "seed": SEED,
                "capture_library_key": "capture_library",
                "labels_available_to_methods": False,
                "labels_used_for_threshold_selection": False,
                "ambiguous_label_policy": "retain in method execution; exclude from discrimination metrics",
                "frozen_acceptance_thresholds": {
                    "overall_auroc_minimum": 0.55,
                    "per_library_auroc_minimum": 0.52,
                    "average_precision": "greater than published-label prevalence",
                    "score_direction": "published doublet median greater than singlet median",
                },
            },
            "runtime": {
                "python": scrublet_payload["versions"]["python"],
                "scrublet": scrublet_payload["versions"]["scrublet"],
                "anndata": scrublet_payload["versions"]["anndata"],
                "numpy": scrublet_payload["versions"]["numpy"],
                "pandas": scrublet_payload["versions"]["pandas"],
                "scipy": scrublet_payload["versions"]["scipy"],
                "scikit_learn": importlib.metadata.version("scikit-learn"),
                "r": sc_reports["ctrl"]["versions"]["R"],
                "scDblFinder": sc_reports["ctrl"]["versions"]["scDblFinder"],
            },
            "execution": {
                "input_cells": 29065,
                "input_features": 35635,
                "labelled_singlet_or_doublet_cells": int(len(labelled)),
                "ambiguous_cells_excluded_from_metrics": int(
                    evidence["multiplets"].eq("ambs").sum()
                ),
                "method_metrics": metrics,
                "method_agreement": {
                    "both_called": int(concordant_call.sum()),
                    "scrublet_only": int(
                        (labelled["scrublet_call"] & ~labelled["scDblFinder_call"]).sum()
                    ),
                    "scDblFinder_only": int(
                        (~labelled["scrublet_call"] & labelled["scDblFinder_call"]).sum()
                    ),
                    "neither_called": int(
                        (~labelled["scrublet_call"] & ~labelled["scDblFinder_call"]).sum()
                    ),
                    "published_doublet_prevalence": baseline,
                    "published_doublet_prevalence_among_both_called": concordant_prevalence,
                },
                "all_cells_accounted": len(evidence) == 29065,
                "source_immutable": source_digests_before == source_digests_after,
                "outputs_reloaded": True,
                "automatic_cell_removal_performed": False,
            },
            "quality_gates": quality_gates,
            "scientific_boundaries": [
                "Publisher genetic-demultiplexing labels were withheld from fitting and inspected only after method outputs and thresholds were frozen.",
                "Ambiguous publisher labels were retained during both methods but excluded from AUROC, average-precision, and call metrics.",
                "Genetic-demultiplexing labels identify cross-genotype multiplets but miss same-donor doublets, so they are independent incomplete labels rather than complete ground truth.",
                "Scrublet and scDblFinder disagreement is retained for review; no cell was automatically removed.",
                "Performance is specific to these two pooled 10x PBMC capture libraries, the frozen parameters, and recorded runtimes.",
            ],
        }
        if not report["passed"]:
            raise RuntimeError(
                "GSE96583 doublet public case failed frozen gates: "
                + json.dumps(quality_gates, sort_keys=True)
                + "\nmetrics="
                + json.dumps(metrics, sort_keys=True)
            )
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--rscript", type=Path, required=True)
    parser.add_argument("--r-libs", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "public-case-gse96583-doublet-detection.json",
    )
    args = parser.parse_args()
    report = verify(
        args.source_dir, args.scientific_python, args.rscript, args.r_libs
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "case_id": report["case_id"],
                "passed": report["passed"],
                "method_auroc": {
                    method: report["execution"]["method_metrics"][method]["overall"][
                        "auroc"
                    ]
                    for method in ("scrublet", "scDblFinder")
                },
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
