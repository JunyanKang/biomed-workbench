#!/usr/bin/env python3
"""Validate emptyDrops and SoupX on official unfiltered and filtered PBMC3k counts."""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

import numpy as np
import pandas as pd
import scanpy as sc
from scipy.io import mmread

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402

MODULE_ID = "single-cell-droplet-decontamination"
ROW_ID = "agent-protocol-1-emptydrops-1220-soupx-162-cellbender-032"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
TEMPLATE = MODULE_ROOT / "templates" / "run_emptydrops_soupx.R"
BASE_URL = "https://cf.10xgenomics.com/samples/cell-exp/1.1.0/pbmc3k"
SOURCES = {
    "raw": {
        "filename": "pbmc3k_raw_gene_bc_matrices.tar.gz",
        "sha256": "6a8f903aa87d196f66f9b24414bf5ab3e875cf554be2613eb0409a7afd668f01",
    },
    "filtered": {
        "filename": "pbmc3k_filtered_gene_bc_matrices.tar.gz",
        "sha256": "847d6ebd9a1ec9a768f2be7e40ca42cbfe75ebeb6d76a4c24167041699dc28b5",
    },
}
EXPECTED_RAW_SHAPE = (32738, 737280)
EXPECTED_FILTERED_SHAPE = (32738, 2700)
MARKER_GENES = (
    "CD3D",
    "IL7R",
    "LST1",
    "S100A8",
    "MS4A1",
    "CD79A",
    "NKG7",
    "GNLY",
    "FCGR3A",
    "PPBP",
)
SEED = 719


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        url, headers={"User-Agent": "biomed-workbench-public-case/1"}
    )
    with urllib.request.urlopen(
        request, timeout=120
    ) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)


def acquire_sources(work: Path, source_dir: Path | None) -> dict[str, Path]:
    paths = {}
    for name, source in SOURCES.items():
        filename = str(source["filename"])
        path = source_dir / filename if source_dir else work / filename
        if source_dir is None:
            download(f"{BASE_URL}/{filename}", path)
        path = path.resolve(strict=True)
        if sha256(path) != source["sha256"]:
            raise RuntimeError(f"PBMC3k source digest mismatch: {filename}")
        paths[name] = path
    return paths


def extract_bundle(archive: Path, destination: Path) -> Path:
    expected = {"matrix.mtx", "genes.tsv", "barcodes.tsv"}
    extracted: dict[str, Path] = {}
    destination.mkdir()
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            member_path = PurePosixPath(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise RuntimeError("PBMC3k archive contains an unsafe path")
            if member.issym() or member.islnk() or member.isdev():
                raise RuntimeError("PBMC3k archive contains an unsupported member")
            if not member.isfile() or member_path.name not in expected:
                continue
            stream = bundle.extractfile(member)
            if stream is None:
                raise RuntimeError("PBMC3k archive member is unreadable")
            target = destination / member_path.name
            target.write_bytes(stream.read())
            extracted[member_path.name] = target
    if set(extracted) != expected:
        raise RuntimeError("PBMC3k archive lacks the expected 10x files")
    return destination


def matrix_market_shape(path: Path) -> tuple[int, int]:
    with path.open(encoding="ascii") as handle:
        first = handle.readline().strip()
        if not first.startswith("%%MatrixMarket matrix coordinate"):
            raise RuntimeError("PBMC3k matrix has an unsupported Matrix Market header")
        for line in handle:
            if not line.startswith("%"):
                rows, columns, _ = map(int, line.split())
                return rows, columns
    raise RuntimeError("PBMC3k matrix shape is absent")


def build_clusters(filtered: Path, destination: Path) -> dict[str, int]:
    adata = sc.read_10x_mtx(
        filtered, var_names="gene_ids", make_unique=False, cache=False
    )
    adata.var_names_make_unique()
    sc.pp.filter_genes(adata, min_cells=3)
    sc.pp.normalize_total(adata, target_sum=10000)
    sc.pp.log1p(adata)
    sc.pp.highly_variable_genes(
        adata, n_top_genes=2000, flavor="seurat"
    )
    sc.pp.pca(
        adata,
        n_comps=30,
        mask_var="highly_variable",
        random_state=SEED,
    )
    sc.pp.neighbors(
        adata, n_neighbors=10, n_pcs=30, random_state=SEED
    )
    sc.tl.leiden(
        adata,
        resolution=0.6,
        random_state=SEED,
        n_iterations=2,
        flavor="igraph",
        key_added="cluster",
    )
    adata.obs[["cluster"]].rename_axis("barcode").reset_index().to_csv(
        destination, sep="\t", index=False
    )
    return {
        str(key): int(value)
        for key, value in adata.obs["cluster"].value_counts().sort_index().items()
    }


def run_template(
    rscript: Path,
    r_libs: Path,
    raw: Path,
    filtered: Path,
    clusters: Path,
    output: Path,
    report: Path,
    work: Path,
) -> None:
    environment = dict(os.environ)
    environment["R_LIBS_USER"] = str(r_libs)
    environment["TMPDIR"] = str(work / "r-tmp")
    Path(environment["TMPDIR"]).mkdir()
    completed = subprocess.run(
        [
            str(rscript),
            str(TEMPLATE),
            "--raw-mtx",
            str(raw),
            "--filtered-mtx",
            str(filtered),
            "--output-dir",
            str(output),
            "--report",
            str(report),
            "--lower",
            "100",
            "--fdr",
            "0.001",
            "--niters",
            "1000",
            "--contamination-mode",
            "auto",
            "--seed",
            str(SEED),
            "--cluster-tsv",
            str(clusters),
            "--tfidf-min",
            "1",
            "--soup-quantile",
            "0.9",
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
            "public PBMC3k droplet execution failed:\n"
            + completed.stdout[-1500:]
            + "\n"
            + completed.stderr[-4000:]
        )


def verify(
    source_dir: Path | None, rscript: Path, r_libs: Path
) -> dict[str, object]:
    r_executable = rscript.expanduser().resolve(strict=True)
    library = r_libs.expanduser().resolve(strict=True)
    with tempfile.TemporaryDirectory(
        prefix="biomed-public-pbmc3k-droplet-"
    ) as temporary:
        work = Path(temporary)
        paths = acquire_sources(
            work,
            source_dir.expanduser().resolve(strict=True)
            if source_dir
            else None,
        )
        archive_digests_before = {
            name: sha256(path) for name, path in paths.items()
        }
        raw = extract_bundle(paths["raw"], work / "raw")
        filtered = extract_bundle(paths["filtered"], work / "filtered")
        if (
            matrix_market_shape(raw / "matrix.mtx") != EXPECTED_RAW_SHAPE
            or matrix_market_shape(filtered / "matrix.mtx")
            != EXPECTED_FILTERED_SHAPE
        ):
            raise RuntimeError("PBMC3k raw or filtered shape differs from contract")
        raw_barcodes = (raw / "barcodes.tsv").read_text().splitlines()
        filtered_barcodes = (
            filtered / "barcodes.tsv"
        ).read_text().splitlines()
        if (
            len(raw_barcodes) != EXPECTED_RAW_SHAPE[1]
            or len(filtered_barcodes) != EXPECTED_FILTERED_SHAPE[1]
            or len(set(raw_barcodes)) != len(raw_barcodes)
            or not set(filtered_barcodes) <= set(raw_barcodes)
            or (raw / "genes.tsv").read_bytes()
            != (filtered / "genes.tsv").read_bytes()
        ):
            raise RuntimeError("PBMC3k features or barcode identities differ")

        environment_backup = {
            name: os.environ.get(name)
            for name in ("NUMBA_CACHE_DIR", "MPLCONFIGDIR", "XDG_CACHE_HOME")
        }
        try:
            for name, variable in (
                ("numba", "NUMBA_CACHE_DIR"),
                ("matplotlib", "MPLCONFIGDIR"),
                ("cache", "XDG_CACHE_HOME"),
            ):
                directory = work / name
                directory.mkdir()
                os.environ[variable] = str(directory)
            clusters_path = work / "clusters.tsv"
            cluster_counts = build_clusters(filtered, clusters_path)
        finally:
            for name, value in environment_backup.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

        output_directory = work / "droplet-output"
        template_report_path = work / "droplet-report.json"
        run_template(
            r_executable,
            library,
            raw,
            filtered,
            clusters_path,
            output_directory,
            template_report_path,
            work,
        )
        template_report = json.loads(
            template_report_path.read_text(encoding="utf-8")
        )
        emptydrops = pd.read_csv(
            output_directory / "emptydrops_calls.tsv", sep="\t"
        )
        ambient = pd.read_csv(
            output_directory / "ambient_profile.tsv", sep="\t"
        )
        contamination = pd.read_csv(
            output_directory / "cell_contamination.tsv", sep="\t"
        )
        filtered_set = set(filtered_barcodes)
        filtered_rows = emptydrops["barcode"].isin(filtered_set)
        filtered_emptydrops_calls = int(
            emptydrops.loc[filtered_rows, "emptydrops_call"].sum()
        )
        calls_outside_filtered = int(
            emptydrops.loc[~filtered_rows, "emptydrops_call"].sum()
        )

        source_counts = mmread(filtered / "matrix.mtx").tocsr()
        corrected_counts = mmread(
            output_directory / "soupx_corrected" / "matrix.mtx"
        ).tocsr()
        genes = pd.read_csv(
            filtered / "genes.tsv", sep="\t", header=None
        )
        symbols = genes.iloc[:, 1].astype(str).to_numpy()
        marker_retention = {}
        for marker in MARKER_GENES:
            indices = np.flatnonzero(symbols == marker)
            source_total = float(source_counts[indices].sum())
            corrected_total = float(corrected_counts[indices].sum())
            marker_retention[marker] = {
                "source_counts": int(source_total),
                "corrected_counts": int(corrected_total),
                "retained_fraction": corrected_total / source_total,
            }
        minimum_marker_retention = min(
            item["retained_fraction"] for item in marker_retention.values()
        )
        archive_digests_after = {
            name: sha256(path) for name, path in paths.items()
        }
        quality_gates = {
            "official_archives_immutable": "pass"
            if archive_digests_before == archive_digests_after
            else "fail",
            "raw_filtered_features_and_barcodes_reconciled": "pass",
            "all_raw_barcodes_accounted": "pass"
            if len(emptydrops) == EXPECTED_RAW_SHAPE[1]
            else "fail",
            "emptydrops_tested_and_untested_states_preserved": "pass"
            if emptydrops["p_value"].notna().sum()
            == template_report["emptydrops_tested"]
            and emptydrops["p_value"].isna().any()
            else "fail",
            "cell_caller_disagreement_preserved": "pass"
            if 0 < filtered_emptydrops_calls < len(filtered_barcodes)
            and calls_outside_filtered == 0
            else "fail",
            "automatic_soupx_estimate_plausible": "pass"
            if 0
            < template_report["contamination_fraction_median"]
            < 0.30
            else "fail",
            "corrected_counts_and_identifiers_valid": "pass"
            if template_report["corrected_counts_never_exceed_source"]
            and template_report["integer_nonnegative_corrected_counts"]
            and template_report["source_identifiers_preserved"]
            else "fail",
            "broad_pbmc_marker_signal_retained": "pass"
            if minimum_marker_retention >= 0.80
            else "fail",
            "ambient_outputs_and_source_reload": "pass"
            if len(ambient) == EXPECTED_RAW_SHAPE[0]
            and len(contamination) == EXPECTED_FILTERED_SHAPE[1]
            and template_report["ambient_and_contamination_tables_reloaded"]
            and template_report["serialized_output_reloaded"]
            and not template_report["source_artifacts_mutated"]
            else "fail",
        }
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        report = {
            "schema_version": 1,
            "case_id": "pbmc3k-emptydrops-soupx-public-data-v1",
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
                "publisher": "10x Genomics",
                "dataset": "3k PBMCs from a healthy donor",
                "assay": "single-cell 3-prime gene expression",
                "files": SOURCES,
                "validation": {
                    "raw_droplets": EXPECTED_RAW_SHAPE[1],
                    "filtered_cells": EXPECTED_FILTERED_SHAPE[1],
                    "features": EXPECTED_RAW_SHAPE[0],
                    "filtered_barcodes_subset_of_raw": True,
                    "raw_filtered_features_identical": True,
                },
            },
            "parameters": {
                "emptydrops_lower": 100,
                "emptydrops_fdr": 0.001,
                "emptydrops_iterations": 1000,
                "soupx_contamination_mode": "auto",
                "soupx_tfidf_min": 1,
                "soupx_quantile": 0.9,
                "cluster_method": "Scanpy PCA-neighbors-Leiden",
                "cluster_resolution": 0.6,
                "seed": SEED,
            },
            "runtime": {
                **template_report["versions"],
                "scanpy": version("scanpy"),
            },
            "execution": {
                "cluster_counts": cluster_counts,
                "raw_barcodes_accounted": len(emptydrops),
                "emptydrops_tested": int(
                    emptydrops["p_value"].notna().sum()
                ),
                "emptydrops_called": int(
                    emptydrops["emptydrops_call"].sum()
                ),
                "filtered_cells_supported_by_emptydrops": filtered_emptydrops_calls,
                "filtered_cells_not_supported_by_emptydrops": len(
                    filtered_barcodes
                )
                - filtered_emptydrops_calls,
                "emptydrops_calls_outside_cellranger_filtered_set": calls_outside_filtered,
                "contamination_fraction": {
                    "minimum": template_report[
                        "contamination_fraction_min"
                    ],
                    "median": template_report[
                        "contamination_fraction_median"
                    ],
                    "maximum": template_report[
                        "contamination_fraction_max"
                    ],
                },
                "source_filtered_counts": template_report[
                    "source_filtered_counts"
                ],
                "corrected_counts": template_report["corrected_counts"],
                "removed_counts": template_report["removed_counts"],
                "removed_fraction": template_report["removed_fraction"],
                "top_ambient_features": template_report[
                    "top_ambient_features"
                ],
                "marker_retention": marker_retention,
                "minimum_marker_retention": minimum_marker_retention,
                "source_archives_immutable": archive_digests_before
                == archive_digests_after,
                "outputs_reloaded": True,
            },
            "quality_gates": quality_gates,
            "scientific_boundaries": [
                "Cell Ranger filtering and emptyDrops are retained as distinct cell-calling decisions; the 518 filtered barcodes not supported at emptyDrops FDR 0.001 are not automatically removed.",
                "SoupX contamination is estimated automatically from expression-derived clusters; the 5.7 percent estimate remains dataset- and clustering-specific.",
                "Marker retention is a broad subtraction sanity check, not proof that every cell type, state, rare population, or differential signal is preserved.",
                "This public case validates emptyDrops and SoupX on one healthy-donor PBMC capture; CellBender retains separate executable fixture evidence.",
                "Corrected counts remain an alternative representation, while the immutable raw and Cell Ranger filtered counts remain authoritative.",
            ],
        }
        if not report["passed"]:
            raise RuntimeError(
                "PBMC3k droplet public gates failed: "
                + json.dumps(quality_gates, sort_keys=True)
            )
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--rscript", type=Path, default=Path("Rscript"))
    parser.add_argument("--r-libs", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "reports"
        / "public-case-pbmc3k-droplet-decontamination.json",
    )
    args = parser.parse_args()
    report = verify(args.source_dir, args.rscript, args.r_libs)
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
                "emptydrops_called": report["execution"][
                    "emptydrops_called"
                ],
                "soupx_contamination_fraction": report["execution"][
                    "contamination_fraction"
                ]["median"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
