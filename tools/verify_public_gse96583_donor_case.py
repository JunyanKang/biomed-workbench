#!/usr/bin/env python3
"""Run donor-aware pseudobulk inference on the paired public GSE96583 PBMC study."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

import anndata as ad
import numpy as np
import pandas as pd
import scipy
from scipy import sparse
from scipy.io import mmread


ROOT = Path(__file__).resolve().parents[1]
MODULE_ID = "single-cell-donor-inference"
ROW_ID = "agent-protocol-1-scanpy-110-edger-40-deseq2-142-limma-358"
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
AGGREGATE = MODULE_ROOT / "templates" / "pseudobulk_aggregate.py"
DIFFERENTIAL = MODULE_ROOT / "templates" / "donor_differential.R"
BASE_URL = "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE96nnn/GSE96583/suppl"
SOURCES = {
    "archive": {
        "filename": "GSE96583_RAW.tar",
        "sha256": "e5d41a3248a813f99d68fd5c9eb9773de7f46a83680a67f4a02d683b8955fe80",
    },
    "metadata": {
        "filename": "GSE96583_batch2.total.tsne.df.tsv.gz",
        "sha256": "1d57e72e92ca8695250e88cc0f1c3fa8c0be1175d974f8b427c58f1274dc6c09",
    },
    "genes": {
        "filename": "GSE96583_batch2.genes.tsv.gz",
        "sha256": "93aa4e9b530ef9d6411ca129b416324c5cc1cc5a01a1fa6ed4f4a845480ed3ca",
    },
}
ARCHIVE_MEMBERS = {
    "ctrl_matrix": "GSM2560248_2.1.mtx.gz",
    "ctrl_barcodes": "GSM2560248_barcodes.tsv.gz",
    "stim_matrix": "GSM2560249_2.2.mtx.gz",
    "stim_barcodes": "GSM2560249_barcodes.tsv.gz",
}
EXPECTED_MATRIX_SHAPES = {"ctrl": (35635, 14619), "stim": (35635, 14446)}
EXPECTED_METADATA_ROWS = 29065
EXPECTED_DONORS = {"101", "107", "1015", "1016", "1039", "1244", "1256", "1488"}
IFN_RESPONSE_GENES = {
    "IFI6", "IFIT1", "IFIT2", "IFIT3", "ISG15", "MX1", "OAS1", "OAS2", "OAS3", "STAT1",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_version(name: str) -> str:
    return importlib.metadata.version(name)


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "biomed-workbench-public-case/1"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)


def acquire_sources(work: Path, source_dir: Path | None) -> dict[str, Path]:
    paths = {}
    for key, source in SOURCES.items():
        filename = str(source["filename"])
        path = source_dir / filename if source_dir else work / filename
        if source_dir is None:
            download(f"{BASE_URL}/{filename}", path)
        path = path.resolve(strict=True)
        if sha256(path) != source["sha256"]:
            raise RuntimeError(f"GSE96583 source digest mismatch: {filename}")
        paths[key] = path
    return paths


def extract_members(archive: Path, destination: Path) -> dict[str, Path]:
    destination.mkdir()
    expected = set(ARCHIVE_MEMBERS.values())
    extracted = {}
    with tarfile.open(archive, "r:") as bundle:
        for member in bundle.getmembers():
            member_path = PurePosixPath(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise RuntimeError("GSE96583 archive contains an unsafe path")
            if member.name not in expected:
                continue
            if not member.isfile() or member.issym() or member.islnk():
                raise RuntimeError("GSE96583 archive member type is unsupported")
            stream = bundle.extractfile(member)
            if stream is None:
                raise RuntimeError("GSE96583 archive member is unreadable")
            target = destination / member.name
            target.write_bytes(stream.read())
            extracted[member.name] = target
    if set(extracted) != expected:
        raise RuntimeError("GSE96583 archive is missing batch-2 matrix members")
    return {key: extracted[name] for key, name in ARCHIVE_MEMBERS.items()}


def unique_gene_names(genes: pd.DataFrame) -> list[str]:
    symbols = genes.iloc[:, 1].fillna("").astype(str).str.strip()
    identifiers = genes.iloc[:, 0].astype(str).str.strip()
    counts = symbols.value_counts()
    return [
        symbol if symbol and counts[symbol] == 1 else f"{symbol or 'UNNAMED'}|{identifier}"
        for symbol, identifier in zip(symbols, identifiers)
    ]


def read_condition(
    matrix_path: Path,
    barcode_path: Path,
    metadata: pd.DataFrame,
    condition: str,
) -> tuple[sparse.csr_matrix, pd.DataFrame, int]:
    with gzip.open(matrix_path, "rb") as handle:
        matrix = sparse.csr_matrix(mmread(handle).transpose(), dtype=np.int64)
    with gzip.open(barcode_path, "rt", encoding="utf-8") as handle:
        barcodes = [line.strip() for line in handle if line.strip()]
    if matrix.shape != (len(barcodes), EXPECTED_MATRIX_SHAPES[condition][0]):
        raise RuntimeError(f"GSE96583 {condition} barcode and matrix axes differ")
    condition_metadata = metadata.loc[metadata["stim"].eq(condition)].copy()
    barcode_set = set(barcodes)
    normalized_index = []
    normalized_count = 0
    for value in condition_metadata.index.astype(str):
        normalized = value
        if value not in barcode_set and value.endswith("-11") and value[:-1] in barcode_set:
            normalized = value[:-1]
            normalized_count += 1
        normalized_index.append(normalized)
    condition_metadata.index = normalized_index
    if (
        len(condition_metadata) != len(barcodes)
        or not condition_metadata.index.is_unique
        or set(condition_metadata.index) != barcode_set
    ):
        raise RuntimeError(f"GSE96583 {condition} metadata and barcode identities differ")
    condition_metadata = condition_metadata.loc[barcodes]
    keep = condition_metadata["multiplets"].eq("singlet") & condition_metadata["cell"].notna()
    condition_metadata = condition_metadata.loc[keep].copy()
    matrix = matrix[np.asarray(keep), :]
    condition_metadata["donor"] = condition_metadata["ind"].astype(str)
    condition_metadata["condition"] = condition
    condition_metadata["biological_sample"] = (
        condition_metadata["donor"] + ":" + condition_metadata["condition"]
    )
    condition_metadata["cell_type"] = condition_metadata["cell"].astype(str)
    condition_metadata.index = [
        f"{condition}:{barcode}" for barcode in condition_metadata.index.astype(str)
    ]
    return matrix, condition_metadata, normalized_count


def run(command: list[str], environment: dict[str, str], timeout: int = 900) -> None:
    completed = subprocess.run(
        command, cwd=ROOT, env=environment, capture_output=True, text=True,
        timeout=timeout, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"public GSE96583 workflow failed: {completed.stderr[-3000:]}")


def read_result(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def verify(source_dir: Path | None, rscript: Path) -> dict[str, object]:
    if not (1, 10) <= tuple(map(int, package_version("scanpy").split(".")[:2])) < (1, 12):
        raise RuntimeError("GSE96583 case requires declared Scanpy >=1.10,<1.12")
    r_executable = rscript.expanduser().resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="biomed-public-gse96583-") as temporary:
        work = Path(temporary)
        paths = acquire_sources(work, source_dir.expanduser().resolve() if source_dir else None)
        members = extract_members(paths["archive"], work / "raw")
        metadata = pd.read_csv(paths["metadata"], sep="\t", index_col=0)
        genes = pd.read_csv(paths["genes"], sep="\t", header=None)
        required_columns = {"ind", "stim", "cell", "multiplets"}
        if (
            len(metadata) != EXPECTED_METADATA_ROWS
            or not required_columns <= set(metadata.columns)
            or set(metadata["ind"].astype(str)) != EXPECTED_DONORS
            or set(metadata["stim"]) != {"ctrl", "stim"}
            or genes.shape != (35635, 2)
        ):
            raise RuntimeError("GSE96583 published metadata identity or design differs")

        matrices, observations = [], []
        barcode_normalizations = {}
        for condition in ("ctrl", "stim"):
            matrix, obs, normalized_count = read_condition(
                members[f"{condition}_matrix"],
                members[f"{condition}_barcodes"],
                metadata,
                condition,
            )
            matrices.append(matrix)
            observations.append(obs)
            barcode_normalizations[condition] = normalized_count
        counts = sparse.vstack(matrices, format="csr", dtype=np.int64)
        obs = pd.concat(observations)
        if (
            not obs.index.is_unique
            or set(obs["donor"]) != EXPECTED_DONORS
            or set(obs.groupby("donor")["condition"].nunique()) != {2}
            or counts.shape != (24673, 35635)
            or int(counts.sum()) <= 0
        ):
            raise RuntimeError("GSE96583 singlet matrix or paired donor design failed validation")

        var = pd.DataFrame(
            {"ensembl_id": genes.iloc[:, 0].astype(str).tolist()},
            index=unique_gene_names(genes),
        )
        adata = ad.AnnData(X=counts.copy(), obs=obs, var=var)
        adata.layers["counts"] = counts
        adata.uns["annotation_provenance"] = {
            "source": "GSE96583_batch2.total.tsne.df.tsv.gz",
            "publisher_labels": True,
            "multiplet_policy": "retain published singlet calls only",
        }
        input_h5ad = work / "gse96583-singlets.h5ad"
        adata.write_h5ad(input_h5ad, compression="gzip")

        environment = dict(os.environ)
        for directory, variable in (
            ("numba", "NUMBA_CACHE_DIR"),
            ("matplotlib", "MPLCONFIGDIR"),
            ("cache", "XDG_CACHE_HOME"),
        ):
            target = work / directory
            target.mkdir()
            environment[variable] = str(target)
        environment["PYTHONHASHSEED"] = "0"

        pseudobulk_counts = work / "pseudobulk-counts.tsv"
        pseudobulk_metadata = work / "pseudobulk-metadata.tsv"
        accounting_path = work / "aggregation-accounting.json"
        run(
            [
                sys.executable, str(AGGREGATE),
                "--input-h5ad", str(input_h5ad),
                "--raw-count-location", "layers.counts",
                "--sample-key", "biological_sample",
                "--cell-type-key", "cell_type",
                "--condition-key", "condition",
                "--covariates", "none",
                "--subject-key", "donor",
                "--min-cells-per-pseudobulk", "20",
                "--min-library-size", "1000",
                "--output-counts", str(pseudobulk_counts),
                "--output-metadata", str(pseudobulk_metadata),
                "--accounting-report", str(accounting_path),
            ],
            environment,
        )
        accounting = json.loads(accounting_path.read_text(encoding="utf-8"))
        if not (
            accounting["input"]["cells"] == 24673
            and accounting["input"]["features"] == 35635
            and accounting["accounting"]["all_cells_accounted"] is True
            and accounting["accounting"]["raw_counts_conserved"] is True
            and accounting["accounting"]["pseudobulks"] == 128
        ):
            raise RuntimeError("GSE96583 pseudobulk accounting failed")

        result_path = work / "edger-results.tsv"
        diagnostics_path = work / "edger-diagnostics.json"
        run(
            [
                str(r_executable), str(DIFFERENTIAL),
                "--counts", str(pseudobulk_counts),
                "--metadata", str(pseudobulk_metadata),
                "--results", str(result_path),
                "--diagnostics", str(diagnostics_path),
                "--engine", "edger",
                "--condition-column", "condition",
                "--reference-level", "ctrl",
                "--contrast-level", "stim",
                "--cell-type-column", "cell_type",
                "--sample-column", "biological_sample",
                "--subject-column", "donor",
                "--categorical-covariates", "none",
                "--continuous-covariates", "none",
                "--min-replicates-per-group", "4",
                "--min-count", "10",
                "--min-samples-expressed", "4",
                "--fdr-threshold", "0.05",
            ],
            environment,
        )
        diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
        results = read_result(result_path)
        completed = [item for item in diagnostics["analyses"] if item["status"] == "completed"]
        ifn_rows = [
            row for row in results
            if row["gene_id"] in IFN_RESPONSE_GENES
            and row["cell_type"] in {"B cells", "CD14+ Monocytes", "CD4 T cells", "CD8 T cells", "NK cells"}
        ]
        positive_ifn = [
            row for row in ifn_rows
            if float(row["log2_fold_change"]) > 0
            and row["fdr"] not in {"NA", "NaN", ""}
            and float(row["fdr"]) <= 0.05
        ]
        recovered_genes = sorted({row["gene_id"] for row in positive_ifn})
        recovered_cell_types = sorted({row["cell_type"] for row in positive_ifn})
        major_cell_types = {
            "B cells", "CD14+ Monocytes", "CD4 T cells", "CD8 T cells",
            "FCGR3A+ Monocytes", "NK cells",
        }
        completed_by_cell_type = {item["cell_type"]: item for item in completed}
        acceptance_checks = {
            "cells_not_replicates": diagnostics["quality"]["cells_used_as_replicates"] is False,
            "completed_designs_full_rank": diagnostics["quality"]["all_completed_designs_full_rank"] is True,
            "result_reload_validated": diagnostics["quality"]["result_reload_validated"] is True,
            "at_least_six_completed_cell_types": len(completed) >= 6,
            "subject_fixed_effect_used": all(
                item["subject_design"]["mode"] == "subject-fixed-effect" for item in completed
            ),
            "at_least_five_complete_pairs_per_completed_cell_type": all(
                item["subject_design"]["complete_pairs"] >= 5 for item in completed
            ),
            "at_least_seven_complete_pairs_for_major_cell_types": all(
                completed_by_cell_type[cell_type]["subject_design"]["complete_pairs"] >= 7
                for cell_type in major_cell_types
            ),
            "at_least_eight_ifn_genes_recovered": len(recovered_genes) >= 8,
            "ifn_response_recovered_in_five_major_cell_types": len(recovered_cell_types) >= 5,
        }
        if not all(acceptance_checks.values()):
            raise RuntimeError(
                "GSE96583 paired design or expected IFN response failed validation: "
                + json.dumps(
                    {
                        "checks": acceptance_checks,
                        "completed": [
                            {
                                "cell_type": item["cell_type"],
                                "pairs": item["subject_design"]["complete_pairs"],
                            }
                            for item in completed
                        ],
                        "recovered_genes": recovered_genes,
                        "recovered_cell_types": recovered_cell_types,
                    },
                    sort_keys=True,
                )
            )

        source_validation = {
            "published_cells": EXPECTED_METADATA_ROWS,
            "retained_published_singlets_with_cell_type": int(adata.n_obs),
            "excluded_doublet_or_ambiguous_or_untyped": EXPECTED_METADATA_ROWS - int(adata.n_obs),
            "features": int(adata.n_vars),
            "donors": len(EXPECTED_DONORS),
            "conditions": 2,
            "paired_donors": 8,
            "cell_types": int(obs["cell_type"].nunique()),
            "combined_metadata_barcode_normalizations": barcode_normalizations,
            "total_raw_counts": int(counts.sum()),
            "integer_nonnegative_counts": bool(
                counts.data.size
                and np.isfinite(counts.data).all()
                and counts.data.min() >= 0
                and np.allclose(counts.data, np.rint(counts.data), rtol=0, atol=1e-8)
            ),
        }
        execution = {
            "pseudobulks": accounting["accounting"]["pseudobulks"],
            "eligible_pseudobulks": accounting["accounting"]["eligible_pseudobulks"],
            "excluded_pseudobulks": accounting["accounting"]["excluded_pseudobulks"],
            "all_cells_accounted": accounting["accounting"]["all_cells_accounted"],
            "raw_counts_conserved": accounting["accounting"]["raw_counts_conserved"],
            "completed_cell_types": len(completed),
            "complete_pairs_by_cell_type": {
                item["cell_type"]: item["subject_design"]["complete_pairs"] for item in completed
            },
            "result_rows": len(results),
            "paired_designs_full_rank": True,
            "result_reload_validated": True,
            "ifn_response_genes_recovered": recovered_genes,
            "ifn_response_cell_types": recovered_cell_types,
            "ephemeral_result_sha256": sha256(result_path),
        }
        runtime = {
            "python": sys.version.split()[0],
            "anndata": package_version("anndata"),
            "numpy": package_version("numpy"),
            "pandas": package_version("pandas"),
            "scanpy": package_version("scanpy"),
            "scipy": scipy.__version__,
            "R": diagnostics["versions"]["R"],
            "edgeR": diagnostics["versions"]["edgeR"],
        }

    return {
        "schema_version": 1,
        "passed": True,
        "case_id": "gse96583-donor-pseudobulk-public-data-v1",
        "case_type": "public-data-end-to-end",
        "module": {
            "id": MODULE_ID,
            "version": "1.0.0",
            "compatibility_row_id": ROW_ID,
            "manifest_sha256": sha256(MANIFEST),
            "template_sha256": {
                "pseudobulk_aggregate.py": sha256(AGGREGATE),
                "donor_differential.R": sha256(DIFFERENTIAL),
            },
        },
        "source": {
            "publisher": "NCBI Gene Expression Omnibus",
            "accession": "GSE96583",
            "title": "Multiplexing droplet-based single cell RNA-sequencing using genetic barcodes",
            "study_record": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE96583",
            "publication_pmid": "29227470",
            "assay": "10x single-cell RNA-seq PBMC control and IFN-beta stimulation",
            "files": {
                key: {
                    "filename": source["filename"],
                    "url": f"{BASE_URL}/{source['filename']}",
                    "sha256": source["sha256"],
                }
                for key, source in SOURCES.items()
            },
            "source_validation": source_validation,
        },
        "parameters": {
            "multiplet_policy": "published singlet calls only",
            "minimum_cells_per_pseudobulk": 20,
            "minimum_library_size": 1000,
            "engine": "edgeR",
            "design": "~ donor + condition",
            "contrast": "stim versus ctrl",
            "minimum_replicates_per_condition": 4,
            "minimum_count": 10,
            "minimum_samples_expressed": 4,
            "fdr": 0.05,
        },
        "runtime": runtime,
        "execution": execution,
        "quality_gates": {
            "official_source_digests": "pass",
            "matrix_metadata_and_barcode_identity": "pass",
            "published_multiplet_exclusion": "pass",
            "eight_donor_paired_design": "pass",
            "raw_count_and_cell_conservation": "pass",
            "biological_replicate_not_cell_inference": "pass",
            "full_rank_subject_fixed_effect_design": "pass",
            "result_schema_and_reload": "pass",
            "independent_expected_ifn_response_check": "pass",
        },
        "scientific_boundaries": [
            "Cell-type and multiplet labels are the publisher-provided annotations; this case does not independently reannotate cells or rerun demuxlet.",
            "The case validates one paired edgeR subject-fixed-effect analysis and does not claim cross-engine sensitivity until DESeq2 or limma-voom is run on the same public data.",
            "The expected interferon-response check is a bounded positive-control acceptance gate, not an exhaustive reproduction of the publication.",
            "Statistical evidence is limited to the eight sampled donors, published cell labels, retained pseudobulks, recorded filtering rules, and IFN-beta stimulation contrast.",
            "The recorded parameters are acceptance-case settings and are not universal defaults for another cohort, chemistry, tissue, or perturbation.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--rscript", type=Path, default=Path("/usr/local/bin/Rscript"))
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "public-case-gse96583-donor-inference.json",
    )
    args = parser.parse_args()
    report = verify(args.source_dir, args.rscript)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "passed": report["passed"],
        "case_id": report["case_id"],
        "cells": report["source"]["source_validation"]["retained_published_singlets_with_cell_type"],
        "completed_cell_types": report["execution"]["completed_cell_types"],
        "ifn_response_genes": len(report["execution"]["ifn_response_genes_recovered"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
