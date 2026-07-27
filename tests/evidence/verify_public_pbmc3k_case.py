#!/usr/bin/env python3
"""Run the packaged single-cell foundation workflow on public 10x PBMC3k data."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from packaging.version import InvalidVersion
from packaging.version import Version
import os
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

import anndata
import numpy as np
import scanpy as sc
from scipy import sparse


ROOT = Path(__file__).resolve().parents[2]
MODULE_ID = "single-cell-foundation-workflow"
ROW_ID = "agent-protocol-1-scanpy-110-or-seurat-52"
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
TEMPLATE = MODULE_ROOT / "templates" / "scanpy_foundation.py"
SOURCE_URL = (
    "https://cf.10xgenomics.com/samples/cell-exp/1.1.0/pbmc3k/"
    "pbmc3k_filtered_gene_bc_matrices.tar.gz"
)
SOURCE_SHA256 = "847d6ebd9a1ec9a768f2be7e40ca42cbfe75ebeb6d76a4c24167041699dc28b5"
EXPECTED_SOURCE_SHAPE = (2700, 32738)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_version(name: str) -> str:
    return importlib.metadata.version(name)


def version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split(".") if part.isdigit())


def declared_scanpy_specs() -> list[str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    specs: list[str] = []
    for row in manifest.get("compatibility_matrix", []):
        if row.get("id") != ROW_ID:
            continue
        for spec in row.get("tool_versions", {}).get("scanpy", ()):
            specs.append(str(spec))
        for spec in row.get("dependency_versions", {}).get("scanpy", ()):
            specs.append(str(spec))
        break
    if specs:
        return specs
    return [">=1.10,<1.12"]


def version_satisfies(version: str, spec: str) -> bool:
    try:
        parsed = Version(version)
    except InvalidVersion:
        return False
    for clause in spec.split(","):
        token = clause.strip()
        if not token:
            continue
        if token.startswith(">="):
            parsed_target = Version(token[2:])
            if parsed < parsed_target:
                return False
        elif token.startswith(">"):
            parsed_target = Version(token[1:])
            if parsed <= parsed_target:
                return False
        elif token.startswith("<="):
            parsed_target = Version(token[2:])
            if parsed > parsed_target:
                return False
        elif token.startswith("<"):
            parsed_target = Version(token[1:])
            if parsed >= parsed_target:
                return False
        elif token.startswith("=="):
            parsed_target = Version(token[2:])
            if parsed != parsed_target:
                return False
        else:
            return False
    return True


def download_source(destination: Path) -> None:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "biomed-workbench-public-case/1"},
    )
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)


def extract_source(archive: Path, destination: Path) -> Path:
    expected_suffixes = {"matrix.mtx", "genes.tsv", "barcodes.tsv"}
    extracted: dict[str, Path] = {}
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            member_path = PurePosixPath(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise RuntimeError("public archive contains an unsafe member path")
            if member.issym() or member.islnk() or member.isdev():
                raise RuntimeError("public archive contains an unsupported member type")
            if not member.isfile() or member_path.name not in expected_suffixes:
                continue
            source = bundle.extractfile(member)
            if source is None:
                raise RuntimeError("public archive member cannot be read")
            target = destination / member_path.name
            target.write_bytes(source.read())
            extracted[member_path.name] = target
    if set(extracted) != expected_suffixes:
        raise RuntimeError("public archive does not contain the expected 10x matrix bundle")
    return destination


def validate_source(adata: anndata.AnnData) -> dict[str, object]:
    if adata.shape != EXPECTED_SOURCE_SHAPE:
        raise RuntimeError("public PBMC3k source shape differs from its documented identity")
    if not adata.obs_names.is_unique or not adata.var_names.is_unique:
        raise RuntimeError("public PBMC3k identifiers are not unique after declared normalization")
    values = adata.X.data if sparse.issparse(adata.X) else np.asarray(adata.X).reshape(-1)
    if (
        values.size == 0
        or not np.isfinite(values).all()
        or float(values.min(initial=0)) < 0
        or not np.allclose(values, np.rint(values), rtol=0, atol=1e-8)
    ):
        raise RuntimeError("public PBMC3k matrix is not finite nonnegative integer-like count data")
    return {
        "cells": adata.n_obs,
        "features": adata.n_vars,
        "nonzero_counts": int(values.size),
        "total_umis": int(values.sum()),
        "unique_cell_ids": True,
        "unique_feature_ids": True,
        "integer_nonnegative_counts": True,
    }


def run_template(work: Path, source: anndata.AnnData) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    source.obs["biological_sample"] = "PBMC3K_DONOR_1"
    input_h5ad = work / "pbmc3k-input.h5ad"
    output_h5ad = work / "pbmc3k-foundation.h5ad"
    qc_path = work / "pbmc3k-qc.json"
    clusters_path = work / "pbmc3k-clusters.json"
    source.write_h5ad(input_h5ad, compression="gzip")
    environment = dict(os.environ)
    for name in ("numba", "matplotlib", "cache"):
        path = work / name
        path.mkdir()
        environment[
            {
                "numba": "NUMBA_CACHE_DIR",
                "matplotlib": "MPLCONFIGDIR",
                "cache": "XDG_CACHE_HOME",
            }[name]
        ] = str(path)
    environment["PYTHONHASHSEED"] = "0"
    completed = subprocess.run(
        [
            sys.executable,
            str(TEMPLATE),
            "--input",
            str(input_h5ad),
            "--input-format",
            "h5ad",
            "--output-h5ad",
            str(output_h5ad),
            "--qc-report",
            str(qc_path),
            "--cluster-report",
            str(clusters_path),
            "--sample-key",
            "biological_sample",
            "--batch-key",
            "none",
            "--raw-count-location",
            "X",
            "--min-counts",
            "0",
            "--max-counts",
            "0",
            "--min-genes",
            "200",
            "--max-genes",
            "2500",
            "--max-mito-percent",
            "5",
            "--min-cells-per-gene",
            "3",
            "--target-sum",
            "10000",
            "--n-top-genes",
            "2000",
            "--n-pcs",
            "40",
            "--n-neighbors",
            "10",
            "--cluster-method",
            "leiden",
            "--resolutions",
            "0.4,0.8",
            "--seed",
            "0",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"packaged PBMC3k workflow failed: {completed.stderr[-1200:]}")
    qc = json.loads(qc_path.read_text(encoding="utf-8"))
    clusters = json.loads(clusters_path.read_text(encoding="utf-8"))
    reloaded = sc.read_h5ad(output_h5ad)
    count_values = reloaded.layers["counts"].data
    reload_validation = {
        "shape_matches_report": list(reloaded.shape)
        == [qc["retained_cells"], qc["retained_features"]],
        "raw_counts_present": "counts" in reloaded.layers,
        "raw_counts_integer": bool(
            np.allclose(count_values, np.rint(count_values), rtol=0, atol=1e-8)
        ),
        "pca_present": "X_pca" in reloaded.obsm,
        "umap_present": "X_umap" in reloaded.obsm,
        "neighbor_graph_present": "connectivities" in reloaded.obsp,
        "cluster_keys_present": all(key in reloaded.obs for key in clusters["cluster_keys"]),
        "ephemeral_output_sha256": sha256(output_h5ad),
    }
    if not all(value for key, value in reload_validation.items() if key != "ephemeral_output_sha256"):
        raise RuntimeError("public PBMC3k output failed reload validation")
    return qc, clusters, reload_validation


def verify(archive: Path | None = None) -> dict[str, object]:
    scanpy_version = package_version("scanpy")
    accepted_specs = declared_scanpy_specs()
    if not any(version_satisfies(scanpy_version, spec) for spec in accepted_specs):
        raise RuntimeError(
            f"public case requires the declared Scanpy compatibility spec(s) {accepted_specs}; observed={scanpy_version}"
        )
    with tempfile.TemporaryDirectory(prefix="biomed-public-pbmc3k-") as temporary:
        work = Path(temporary)
        source_archive = archive.resolve(strict=True) if archive else work / "pbmc3k.tar.gz"
        if archive is None:
            download_source(source_archive)
        observed_sha256 = sha256(source_archive)
        if observed_sha256 != SOURCE_SHA256:
            raise RuntimeError("public PBMC3k archive digest does not match the documented source")
        matrix_dir = extract_source(source_archive, work / "matrix")
        adata = sc.read_10x_mtx(
            matrix_dir,
            var_names="gene_symbols",
            make_unique=True,
            cache=False,
        )
        source_validation = validate_source(adata)
        qc, clusters, reload_validation = run_template(work, adata)
    cluster_counts = {
        item["key"]: item["cluster_count"] for item in clusters["clusters"]
    }
    minimum_cluster_sizes = {
        item["key"]: min(item["cluster_sizes"].values()) for item in clusters["clusters"]
    }
    return {
        "schema_version": 1,
        "passed": True,
        "case_id": "pbmc3k-foundation-public-data-v1",
        "case_type": "public-data-end-to-end",
        "module": {
            "id": MODULE_ID,
            "version": "1.0.0",
            "compatibility_row_id": ROW_ID,
            "manifest_sha256": sha256(MANIFEST),
            "template_sha256": sha256(TEMPLATE),
        },
        "source": {
            "publisher": "10x Genomics",
            "dataset": "3k PBMCs from a healthy donor",
            "assay": "single-cell 3-prime gene expression",
            "archive": "pbmc3k_filtered_gene_bc_matrices.tar.gz",
            "url": SOURCE_URL,
            "sha256": SOURCE_SHA256,
            "documented_shape": list(EXPECTED_SOURCE_SHAPE),
            "source_validation": source_validation,
        },
        "runtime": {
            name: package_version(name)
            for name in (
                "scanpy",
                "anndata",
                "numpy",
                "scipy",
                "pandas",
                "scikit-learn",
                "igraph",
                "leidenalg",
                "umap-learn",
            )
        },
        "parameters": {
            "minimum_genes_per_cell": 200,
            "maximum_genes_per_cell": 2500,
            "maximum_mitochondrial_percent": 5,
            "minimum_cells_per_gene": 3,
            "normalization_target_sum": 10000,
            "highly_variable_genes": 2000,
            "principal_components": 40,
            "neighbors": 10,
            "cluster_method": "leiden",
            "resolutions": [0.4, 0.8],
            "random_seed": 0,
            "scope": "reproducible public-case baseline, not universal biological defaults",
        },
        "execution": {
            "input_cells": qc["input_cells"],
            "retained_cells": qc["retained_cells"],
            "excluded_cells": qc["excluded_cells"],
            "input_features": qc["input_features"],
            "retained_features": qc["retained_features"],
            "exclusion_reason_counts": qc["exclusion_reason_counts"],
            "cluster_counts": cluster_counts,
            "minimum_cluster_sizes": minimum_cluster_sizes,
            "adjacent_resolution_ari": clusters["adjacent_resolution_ari"],
            "reload_validation": reload_validation,
        },
        "quality_gates": {
            "official_archive_digest": "pass",
            "matrix_identity_and_orientation": "pass",
            "finite_nonnegative_integer_counts": "pass",
            "complete_cell_accounting": "pass",
            "raw_count_preservation": "pass",
            "pca_neighbor_umap_and_clustering": "pass",
            "serialized_output_reload": "pass",
            "unexecuted_methods_explicit": "pass",
        },
        "methods_not_run": qc["methods"],
        "scientific_boundaries": [
            "The source is a filtered matrix, so empty-droplet calling cannot be evaluated from this artifact.",
            "Ambient RNA correction and doublet detection were not run and no negative finding is claimed.",
            "The dataset represents one healthy donor; it cannot support donor-aware condition inference, differential abundance, population generalization, or causal claims.",
            "Clusters are technical workflow outputs until marker, reference, ontology, sample-composition, and unknown-state review is completed.",
            "The recorded thresholds reproduce this bounded public case and are not universal defaults for another chemistry, tissue, organism, or study design.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "public-case-pbmc3k-foundation.json",
    )
    args = parser.parse_args()
    report = verify(args.archive)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "case_id": report["case_id"],
                "passed": True,
                "retained_cells": report["execution"]["retained_cells"],
                "retained_features": report["execution"]["retained_features"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
