#!/usr/bin/env python3
"""Validate RNA+ATAC WNN and MOFA+ on public 10x PBMC multiome counts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

import anndata as ad
import h5py
import mudata
import numpy as np
import pandas as pd
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402

MODULE_ID = "single-cell-multimodal-integration"
ROW_ID = "agent-protocol-1-seurat-521-signac-116-mofapy2-074"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
PREPARE = MODULE_ROOT / "templates" / "prepare_10x_multiome.R"
WNN = MODULE_ROOT / "templates" / "run_wnn.R"
MOFA = MODULE_ROOT / "templates" / "fit_mofaplus.py"
SOURCE = {
    "filename": "pbmc_granulocyte_sorted_10k_filtered_feature_bc_matrix.h5",
    "url": (
        "https://cf.10xgenomics.com/samples/cell-arc/1.0.0/"
        "pbmc_granulocyte_sorted_10k/"
        "pbmc_granulocyte_sorted_10k_filtered_feature_bc_matrix.h5"
    ),
    "sha256": "03f946fc11984e6d4e8bf9a5d5904654c3d8b6b5776e08b7962796a9cb81c48d",
}
N_CELLS = 600
N_RNA_FEATURES = 800
N_ATAC_FEATURES = 1000
SEED = 20260723


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def acquire_source(work: Path, source_path: Path | None) -> Path:
    if source_path is None:
        source = work / SOURCE["filename"]
        urllib.request.urlretrieve(SOURCE["url"], source)
    else:
        candidate = source_path.expanduser().resolve(strict=True)
        source = candidate / SOURCE["filename"] if candidate.is_dir() else candidate
        source = source.resolve(strict=True)
    if sha256(source) != SOURCE["sha256"]:
        raise RuntimeError("public 10x multiome source digest mismatch")
    return source


def decode(values) -> np.ndarray:
    return np.asarray(
        [value.decode() if isinstance(value, bytes) else str(value) for value in values],
        dtype=object,
    )


def read_10x(source: Path) -> tuple[sparse.csr_matrix, np.ndarray, pd.DataFrame]:
    with h5py.File(source, "r") as handle:
        group = handle["matrix"]
        matrix = sparse.csc_matrix(
            (
                np.asarray(group["data"]),
                np.asarray(group["indices"]),
                np.asarray(group["indptr"]),
            ),
            shape=tuple(np.asarray(group["shape"], dtype=int)),
        ).transpose().tocsr()
        barcodes = decode(group["barcodes"])
        features = group["features"]
        feature_frame = pd.DataFrame(
            {
                "feature_id": decode(features["id"]),
                "feature_name": decode(features["name"]),
                "feature_type": decode(features["feature_type"]),
                "genome": decode(features["genome"]),
            }
        )
    if matrix.shape != (len(barcodes), len(feature_frame)):
        raise RuntimeError("10x matrix axes differ from feature or barcode tables")
    return matrix.astype(np.int64), barcodes, feature_frame


def stable_indices(values: np.ndarray, number: int, prefix: str) -> np.ndarray:
    ranked = sorted(
        range(len(values)),
        key=lambda index: hashlib.sha256(
            f"{prefix}:{SEED}:{values[index]}".encode()
        ).hexdigest(),
    )
    return np.asarray(sorted(ranked[:number]), dtype=int)


def top_detected(matrix: sparse.csr_matrix, number: int) -> np.ndarray:
    detected = np.asarray((matrix > 0).sum(axis=0)).ravel()
    totals = np.asarray(matrix.sum(axis=0)).ravel()
    ranked = np.lexsort((np.arange(matrix.shape[1]), -totals, -detected))
    return np.asarray(sorted(ranked[:number]), dtype=int)


def run(command: list[str], environment: dict[str, str], timeout: int = 1800) -> None:
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
            "public 10x multiome execution failed:\n"
            + completed.stdout[-2500:]
            + "\n"
            + completed.stderr[-6000:]
        )


def write_ids(path: Path, values: np.ndarray) -> None:
    path.write_text("\n".join(map(str, values)) + "\n", encoding="utf-8")


def verify(
    source_path: Path | None,
    scientific_python: Path,
    rscript: Path,
) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    r_executable = rscript.expanduser().absolute()
    if (
        not python.is_file()
        or not os.access(python, os.X_OK)
        or not r_executable.is_file()
        or not os.access(r_executable, os.X_OK)
    ):
        raise RuntimeError("scientific Python and Rscript must be executable")

    with tempfile.TemporaryDirectory(prefix="biomed-public-pbmc-multiome-") as temporary:
        work = Path(temporary)
        source = acquire_source(work, source_path)
        source_digest_before = sha256(source)
        matrix, barcodes, features = read_10x(source)
        if (
            matrix.shape != (11909, 144978)
            or set(features["feature_type"]) != {"Gene Expression", "Peaks"}
        ):
            raise RuntimeError("public 10x multiome dimensions differ from contract")
        cell_indices = stable_indices(barcodes, N_CELLS, "cell")
        cells = barcodes[cell_indices]
        rna_source_indices = np.flatnonzero(
            features["feature_type"].eq("Gene Expression").to_numpy()
            & ~features["feature_name"].duplicated(keep=False).to_numpy()
        )
        atac_source_indices = np.flatnonzero(
            features["feature_type"].eq("Peaks").to_numpy()
        )
        rna_local = top_detected(
            matrix[cell_indices][:, rna_source_indices], N_RNA_FEATURES
        )
        atac_local = top_detected(
            matrix[cell_indices][:, atac_source_indices], N_ATAC_FEATURES
        )
        rna_indices = rna_source_indices[rna_local]
        atac_indices = atac_source_indices[atac_local]
        rna_names = features.iloc[rna_indices]["feature_name"].to_numpy(dtype=object)
        atac_names = features.iloc[atac_indices]["feature_name"].to_numpy(dtype=object)
        rna_counts = matrix[cell_indices][:, rna_indices].tocsr()
        atac_counts = matrix[cell_indices][:, atac_indices].tocsr()
        if (
            rna_counts.shape != (N_CELLS, N_RNA_FEATURES)
            or atac_counts.shape != (N_CELLS, N_ATAC_FEATURES)
            or np.any(np.asarray(rna_counts.sum(axis=1)).ravel() == 0)
            or np.any(np.asarray(atac_counts.sum(axis=1)).ravel() == 0)
        ):
            raise RuntimeError("public multiome subset differs from contract")

        cell_path = work / "cells.txt"
        rna_path = work / "rna-features.txt"
        atac_path = work / "atac-features.txt"
        write_ids(cell_path, cells)
        write_ids(rna_path, rna_names)
        write_ids(atac_path, atac_names)

        environment = dict(os.environ)
        environment.update(
            {
                "PATH": str(python.parent)
                + os.pathsep
                + str(r_executable.parent)
                + os.pathsep
                + os.environ.get("PATH", ""),
                "PYTHONHASHSEED": "0",
                "LANG": "C",
                "LC_ALL": "C",
            }
        )
        for name, variable in (("home", "HOME"), ("cache", "XDG_CACHE_HOME")):
            directory = work / name
            directory.mkdir()
            environment[variable] = str(directory)

        input_rds = work / "multiome.rds"
        prepare_report_path = work / "prepare.json"
        run(
            [
                str(r_executable),
                str(PREPARE),
                "--input-h5",
                str(source),
                "--cell-allowlist",
                str(cell_path),
                "--rna-feature-allowlist",
                str(rna_path),
                "--atac-feature-allowlist",
                str(atac_path),
                "--genome-build",
                "hg38",
                "--output-rds",
                str(input_rds),
                "--report",
                str(prepare_report_path),
            ],
            environment,
        )
        wnn_output = work / "wnn.rds"
        cell_table_path = work / "wnn-cells.tsv"
        wnn_report_path = work / "wnn.json"
        run(
            [
                str(r_executable),
                str(WNN),
                "--input-rds",
                str(input_rds),
                "--output-rds",
                str(wnn_output),
                "--cell-table",
                str(cell_table_path),
                "--report",
                str(wnn_report_path),
                "--rna-assay",
                "RNA",
                "--secondary-assay",
                "ATAC",
                "--secondary-type",
                "atac",
                "--rna-variable-features",
                "500",
                "--rna-dims",
                "20",
                "--secondary-dims",
                "20",
                "--k-nn",
                "20",
                "--resolution",
                "0.5",
                "--seed",
                str(SEED),
            ],
            environment,
        )

        rna_library = np.asarray(rna_counts.sum(axis=1)).ravel()
        rna_model = rna_counts.multiply(1e4 / rna_library[:, None]).tocsr()
        rna_model.data = np.log1p(rna_model.data)
        atac_library = np.asarray(atac_counts.sum(axis=1)).ravel()
        atac_detected = np.asarray((atac_counts > 0).sum(axis=0)).ravel()
        atac_model = atac_counts.multiply(1.0 / atac_library[:, None]).tocsr()
        atac_model = atac_model.multiply(
            np.log1p(N_CELLS / (1.0 + atac_detected))
        ).tocsr()
        obs = pd.DataFrame(index=pd.Index(cells, name="cell_id"))
        rna_adata = ad.AnnData(
            X=rna_counts,
            obs=obs.copy(),
            var=pd.DataFrame(index=pd.Index(rna_names, name="feature_id")),
        )
        atac_adata = ad.AnnData(
            X=atac_counts,
            obs=obs.copy(),
            var=pd.DataFrame(index=pd.Index(atac_names, name="feature_id")),
        )
        rna_adata.layers["model"] = rna_model
        atac_adata.layers["model"] = atac_model
        h5mu_path = work / "multiome.h5mu"
        mudata.MuData({"RNA": rna_adata, "ATAC": atac_adata}).write_h5mu(
            h5mu_path
        )
        config_path = work / "mofa-views.json"
        config_path.write_text(
            json.dumps(
                [
                    {
                        "name": "RNA",
                        "location": "layers.model",
                        "top_variable_features": 120,
                    },
                    {
                        "name": "ATAC",
                        "location": "layers.model",
                        "top_variable_features": 120,
                    },
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        mofa_report_path = work / "mofa.json"
        run(
            [
                str(python),
                str(MOFA),
                "--input-h5mu",
                str(h5mu_path),
                "--view-config",
                str(config_path),
                "--model-output",
                str(work / "mofa.hdf5"),
                "--factor-table",
                str(work / "mofa-factors.tsv"),
                "--weight-table",
                str(work / "mofa-weights.tsv"),
                "--variance-table",
                str(work / "mofa-variance.tsv"),
                "--report",
                str(mofa_report_path),
                "--factors",
                "6",
                "--iterations",
                "100",
                "--convergence-mode",
                "fast",
                "--seed",
                str(SEED),
            ],
            environment,
        )

        prepared = json.loads(prepare_report_path.read_text(encoding="utf-8"))
        wnn = json.loads(wnn_report_path.read_text(encoding="utf-8"))
        mofa = json.loads(mofa_report_path.read_text(encoding="utf-8"))
        cell_table = pd.read_csv(cell_table_path, sep="\t")
        source_digest_after = sha256(source)
        quality_gates = {
            "official_source_identity": "pass"
            if source_digest_before == source_digest_after == SOURCE["sha256"]
            else "fail",
            "label_blind_cell_and_feature_selection": "pass",
            "paired_rna_atac_counts_preserved": "pass"
            if set(prepared["quality_gates"].values()) == {True}
            and wnn["quality_gates"]["source_counts_preserved"]
            else "fail",
            "wnn_graph_weights_clusters_and_reload": "pass"
            if set(wnn["quality_gates"].values()) == {True}
            and wnn["results"]["clusters"] >= 2
            and cell_table["RNA_weight"].between(0, 1).all()
            and cell_table["secondary_weight"].between(0, 1).all()
            else "fail",
            "mofaplus_factors_views_and_reload": "pass"
            if set(mofa["quality_gates"].values()) == {True}
            and mofa["results"]["variance_explained_rows"] == 2
            and mofa["results"]["weight_rows"] == 240
            else "fail",
        }
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        report = {
            "schema_version": 1,
            "case_id": "pbmc-multiome-10k-integration-v1",
            "case_type": "public-data-end-to-end",
            "passed": set(quality_gates.values()) == {"pass"},
            "module": {
                "id": MODULE_ID,
                "version": registry.get(MODULE_ID).version,
                "compatibility_row_id": ROW_ID,
                "manifest_sha256": sha256(MANIFEST),
                "template_sha256": {
                    path.name: sha256(path) for path in (PREPARE, WNN, MOFA)
                },
                "registry_digest": registry.digest,
            },
            "source": {
                "dataset": "10x PBMC 10k Multiome ATAC + Gene Expression",
                **SOURCE,
                "validation": {
                    "source_cells": matrix.shape[0],
                    "source_features": matrix.shape[1],
                    "selected_cells": N_CELLS,
                    "selected_rna_features": N_RNA_FEATURES,
                    "selected_atac_features": N_ATAC_FEATURES,
                    "selection": (
                        "stable barcode hash and detected-cell/total-count "
                        "feature ranking without cluster labels"
                    ),
                },
            },
            "parameters": {
                "wnn": wnn["model"],
                "mofaplus": mofa["model"],
                "mofa_views": ["RNA log-normalized counts", "ATAC TF-IDF"],
            },
            "runtime": {
                "prepare": prepared["versions"],
                "wnn": wnn["versions"],
                "mofaplus": mofa["versions"],
            },
            "execution": {
                "wnn": wnn["results"],
                "mofaplus": mofa["results"],
                "source_artifact_immutable": source_digest_before
                == source_digest_after,
                "outputs_reloaded": True,
            },
            "quality_gates": quality_gates,
            "scientific_boundaries": [
                "The public case validates paired-cell RNA+ATAC representation and source-preserving execution, not biological annotation or treatment inference.",
                "Cells and features are selected without cluster labels; resulting WNN clusters are exploratory and are not evaluated against a tuned label set.",
                "MOFA+ uses explicitly recorded log-normalized RNA and TF-IDF ATAC views under a Gaussian likelihood and does not infer missing modalities.",
                "WNN modality weights and MOFA+ factors are representation evidence, not causal cross-modal regulation.",
            ],
        }
        if not report["passed"]:
            raise RuntimeError(
                "public multiome gates failed: "
                + json.dumps(quality_gates, sort_keys=True)
            )
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--rscript", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "public-case-pbmc-multiome-integration.json",
    )
    args = parser.parse_args()
    report = verify(args.source, args.scientific_python, args.rscript)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "case_id": report["case_id"],
                "passed": report["passed"],
                "clusters": report["execution"]["wnn"]["clusters"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
