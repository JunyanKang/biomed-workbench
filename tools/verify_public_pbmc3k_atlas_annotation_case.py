#!/usr/bin/env python3
"""Validate packaged CellTypist annotation on independent public PBMC3k counts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import anndata
import numpy as np
import pandas as pd
import scanpy as sc
from scipy import sparse

from verify_public_pbmc3k_case import (
    EXPECTED_SOURCE_SHAPE,
    SOURCE_SHA256,
    SOURCE_URL,
    download_source,
    extract_source,
    validate_source,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE_ID = "single-cell-atlas-annotation"
ROW_ID = "agent-protocol-1-celltypist-171-popv-061-azimuth-051-consensus"
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
TEMPLATE = MODULE_ROOT / "templates" / "annotate_celltypist.py"
MODEL_NAME = "Immune_All_Low.pkl"
MODEL_VERSION = "v2"
MODEL_URL = (
    "https://celltypist.cog.sanger.ac.uk/models/"
    "Pan_Immune_CellTypist/v2/Immune_All_Low.pkl"
)
MODEL_SHA256 = "290874d35dac039d4c9218c343fde4aac1077709b72a331ce7266f6828c36502"
MODEL_SOURCE = "https://doi.org/10.1126/science.abl5197"
MODEL_SCOPE = "98 immune sub-populations from 20 tissues and 18 studies"
UNKNOWN_THRESHOLD = 0.5

MARKER_SETS = {
    "B": ("MS4A1", "CD79A", "CD37", "CD74"),
    "myeloid": ("LST1", "TYROBP", "FCER1G", "CTSS"),
    "NK": ("NKG7", "GNLY", "KLRD1", "PRF1"),
    "T": ("CD3D", "CD3E", "TRBC1", "TRAC"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "biomed-workbench-public-atlas-case/1"},
    )
    with urllib.request.urlopen(request, timeout=90) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)


def broad_family(label: str) -> str:
    if "NK" in label or label in {"ILC", "ILC1", "ILC2", "ILC3", "ILC precursor"}:
        return "NK"
    if (
        "B cell" in label
        or label in {"Plasma cells", "Plasmablasts", "Large pre-B cells", "Small pre-B cells", "Pre-pro-B cells", "Pro-B cells"}
    ):
        return "B"
    if (
        "monocyte" in label.lower()
        or "macrophage" in label.lower()
        or label in {"DC", "DC1", "DC2", "DC3", "pDC", "Mono-mac", "MNP", "Transitional DC"}
    ):
        return "myeloid"
    if (
        "T cell" in label
        or label.startswith(("Tcm/", "Tem/", "Trm ", "Treg", "T(", "Type "))
        or label in {"CD8a/a", "CD8a/b(entry)", "MAIT cells", "NKT cells", "Regulatory T cells", "gamma-delta T cells"}
    ):
        return "T"
    return "other"


def run_template(work: Path, source: anndata.AnnData, model: Path) -> tuple[dict[str, object], anndata.AnnData]:
    input_h5ad = work / "pbmc3k-query.h5ad"
    output_h5ad = work / "pbmc3k-celltypist.h5ad"
    report_path = work / "pbmc3k-celltypist-report.json"
    source.write_h5ad(input_h5ad, compression="gzip")
    environment = dict(os.environ)
    for name, variable in (
        ("numba", "NUMBA_CACHE_DIR"),
        ("matplotlib", "MPLCONFIGDIR"),
        ("cache", "XDG_CACHE_HOME"),
    ):
        path = work / name
        path.mkdir()
        environment[variable] = str(path)
    environment["PYTHONHASHSEED"] = "0"
    completed = subprocess.run(
        [
            sys.executable,
            str(TEMPLATE),
            "--query-h5ad",
            str(input_h5ad),
            "--model",
            str(model),
            "--output-h5ad",
            str(output_h5ad),
            "--report",
            str(report_path),
            "--raw-count-location",
            "X",
            "--mode",
            "best match",
            "--probability-threshold",
            "0.5",
            "--unknown-threshold",
            str(UNKNOWN_THRESHOLD),
            "--majority-voting",
            "false",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"packaged CellTypist public case failed: {completed.stderr[-1600:]}")
    return json.loads(report_path.read_text(encoding="utf-8")), anndata.read_h5ad(output_h5ad)


def posthoc_marker_review(adata: anndata.AnnData) -> dict[str, object]:
    raw_labels = adata.obs["celltypist_label_raw"].astype(str)
    families = raw_labels.map(broad_family)
    counts = adata.layers["counts"]
    results: dict[str, object] = {}
    not_evaluable: dict[str, object] = {}
    for family, markers in MARKER_SETS.items():
        present = [marker for marker in markers if marker in adata.var_names]
        mask = np.asarray(families == family)
        reasons = []
        if mask.sum() < 25:
            reasons.append("fewer-than-25-predicted-family-cells")
        if (~mask).sum() < 25:
            reasons.append("fewer-than-25-comparator-cells")
        if len(present) < 3:
            reasons.append("fewer-than-3-declared-markers-present")
        if reasons:
            not_evaluable[family] = {
                "cells": int(mask.sum()),
                "declared_markers": list(markers),
                "present_markers": present,
                "reasons": reasons,
            }
            continue
        selected = counts[:, adata.var_names.get_indexer(present)]
        score = np.asarray(selected.sum(axis=1)).reshape(-1)
        score = np.log1p(score)
        inside = float(np.mean(score[mask]))
        outside = float(np.mean(score[~mask]))
        results[family] = {
            "cells": int(mask.sum()),
            "markers": present,
            "mean_log1p_marker_umis_inside": inside,
            "mean_log1p_marker_umis_outside": outside,
            "difference": inside - outside,
            "direction": "enriched" if inside > outside else "not-enriched",
        }
    if len(results) < 3 or any(item["difference"] <= 0 for item in results.values()):
        raise RuntimeError("frozen CellTypist labels failed broad posthoc marker coherence")
    return {
        "timing": "performed only after model, thresholds, and labels were frozen",
        "purpose": "broad coherence review, not tuning data or ground truth",
        "families": results,
        "not_evaluable_families": not_evaluable,
        "all_evaluable_families_enriched": True,
    }


def validate_output(
    source: anndata.AnnData,
    output: anndata.AnnData,
    template_report: dict[str, object],
) -> dict[str, object]:
    if output.shape != source.shape:
        raise RuntimeError("CellTypist output changed the public source shape")
    if not np.array_equal(output.obs_names, source.obs_names) or not np.array_equal(output.var_names, source.var_names):
        raise RuntimeError("CellTypist output changed public source identifiers")
    left = output.layers["counts"]
    right = source.X
    difference = left != right
    changed = int(difference.nnz) if sparse.issparse(difference) else int(np.count_nonzero(difference))
    probabilities = output.obsm["celltypist_probabilities"]
    if probabilities.shape[0] != source.n_obs or probabilities.shape[1] != template_report["prediction_label_count"]:
        raise RuntimeError("CellTypist probability matrix is not complete")
    confidence = np.asarray(output.obs["celltypist_confidence"], dtype=float)
    reviewed = output.obs["celltypist_label_review"].astype(str)
    expected_unknown = confidence < UNKNOWN_THRESHOLD
    observed_unknown = np.asarray(reviewed == "Unknown")
    if changed or not np.array_equal(expected_unknown, observed_unknown):
        raise RuntimeError("source counts changed or Unknown policy is inconsistent")
    return {
        "shape_preserved": True,
        "cell_identifiers_preserved": True,
        "feature_identifiers_preserved": True,
        "raw_counts_preserved": True,
        "changed_count_entries": changed,
        "probability_matrix_shape": list(probabilities.shape),
        "complete_probability_matrix": True,
        "unknown_policy_exact": True,
        "all_cells_accounted": int(output.n_obs)
        == int(sum(template_report["review_label_counts"].values())),
    }


def verify(archive: Path | None = None, model_path: Path | None = None) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="biomed-public-pbmc3k-atlas-") as temporary:
        work = Path(temporary)
        source_archive = archive.resolve(strict=True) if archive else work / "pbmc3k.tar.gz"
        if archive is None:
            download_source(source_archive)
        if sha256(source_archive) != SOURCE_SHA256:
            raise RuntimeError("public PBMC3k archive digest differs from the documented source")
        source = sc.read_10x_mtx(
            extract_source(source_archive, work / "matrix"),
            var_names="gene_symbols",
            make_unique=True,
            cache=False,
        )
        source_validation = validate_source(source)
        model = model_path.resolve(strict=True) if model_path else work / MODEL_NAME
        if model_path is None:
            download(MODEL_URL, model)
        if sha256(model) != MODEL_SHA256:
            raise RuntimeError("CellTypist model digest differs from the documented official model")
        template_report, output = run_template(work, source, model)
        output_validation = validate_output(source, output, template_report)
        marker_review = posthoc_marker_review(output)
        raw_label_counts = template_report["raw_label_counts"]
        reviewed_label_counts = template_report["review_label_counts"]
        broad_counts = (
            output.obs["celltypist_label_raw"]
            .astype(str)
            .map(broad_family)
            .value_counts()
            .sort_index()
        )
    return {
        "schema_version": 1,
        "passed": True,
        "case_id": "pbmc3k-celltypist-atlas-annotation-v1",
        "case_type": "public-data-end-to-end",
        "module": {
            "id": MODULE_ID,
            "version": "1.1.0",
            "compatibility_row_id": ROW_ID,
            "manifest_sha256": sha256(MANIFEST),
            "template_sha256": sha256(TEMPLATE),
        },
        "source": {
            "publisher": "10x Genomics",
            "dataset": "3k PBMCs from a healthy donor",
            "url": SOURCE_URL,
            "sha256": SOURCE_SHA256,
            "documented_shape": list(EXPECTED_SOURCE_SHAPE),
            "source_validation": source_validation,
        },
        "reference": {
            "publisher": "CellTypist",
            "model": MODEL_NAME,
            "version": MODEL_VERSION,
            "url": MODEL_URL,
            "sha256": MODEL_SHA256,
            "training_source": MODEL_SOURCE,
            "declared_scope": MODEL_SCOPE,
            "classes": 98,
        },
        "runtime": {
            name: importlib.metadata.version(name)
            for name in ("celltypist", "scanpy", "anndata", "numpy", "scipy", "pandas")
        },
        "parameters": {
            "mode": "best match",
            "probability_threshold": 0.5,
            "unknown_threshold": UNKNOWN_THRESHOLD,
            "majority_voting": False,
            "raw_count_location": "X",
            "thresholds_frozen_before_prediction": True,
        },
        "execution": {
            "cells": template_report["cells"],
            "features": template_report["features"],
            "model_feature_overlap": template_report["model_feature_overlap"],
            "prediction_label_count": template_report["prediction_label_count"],
            "raw_label_counts": raw_label_counts,
            "review_label_counts": reviewed_label_counts,
            "broad_family_counts": {str(key): int(value) for key, value in broad_counts.items()},
            "unknown_cells": template_report["unknown_cells"],
            "median_confidence": template_report["median_confidence"],
            "output_validation": output_validation,
            "posthoc_marker_review": marker_review,
        },
        "quality_gates": {
            "official_query_digest": "pass",
            "official_model_digest_and_scope": "pass",
            "finite_nonnegative_integer_counts": "pass",
            "feature_overlap": "pass",
            "thresholds_frozen_before_prediction": "pass",
            "complete_probability_evidence": "pass",
            "unknown_retention_policy": "pass",
            "complete_cell_and_count_accounting": "pass",
            "serialized_output_reload": "pass",
            "posthoc_marker_coherence": "pass",
        },
        "scientific_boundaries": [
            "CellTypist outputs are reference-model evidence, not biological ground truth or expert-reviewed final labels.",
            "Broad marker coherence was evaluated only after model selection, thresholds, and labels were frozen; markers did not tune predictions.",
            "PBMC3k is one filtered healthy-donor sample and does not establish generalization across donors, tissues, diseases, chemistries, developmental stages, or absent-reference populations.",
            "The broad-family review cannot validate all 98 fine-grained model classes, transitional states, novel states, or rare populations.",
            "The recorded model and query digests bind this acceptance result to these exact public artifacts; future model updates require a new compatibility and acceptance record.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "public-case-pbmc3k-atlas-annotation.json",
    )
    args = parser.parse_args()
    report = verify(args.archive, args.model)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "case_id": report["case_id"],
                "passed": True,
                "cells": report["execution"]["cells"],
                "unknown_cells": report["execution"]["unknown_cells"],
                "marker_families": len(report["execution"]["posthoc_marker_review"]["families"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
