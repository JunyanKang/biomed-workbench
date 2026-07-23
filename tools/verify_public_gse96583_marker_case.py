#!/usr/bin/env python3
"""Validate held-out-donor marker discovery on public GSE96583 control PBMCs."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
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


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from verify_public_gse96583_donor_case import (  # noqa: E402
    EXPECTED_DONORS,
    SOURCES,
    acquire_sources,
    extract_members,
    read_condition,
    sha256,
    unique_gene_names,
)


MODULE_ID = "single-cell-marker-discovery"
ROW_ID = "agent-protocol-1-scanpy-1104-marker-stability"
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
TEMPLATE = MODULE_ROOT / "templates" / "discover_markers.py"
DISCOVERY_DONORS = ["101", "107", "1015", "1016", "1039", "1244"]
VALIDATION_DONORS = ["1256", "1488"]
CELL_TYPES = [
    "B cells",
    "CD14+ Monocytes",
    "CD4 T cells",
    "CD8 T cells",
    "FCGR3A+ Monocytes",
    "NK cells",
]
EXPECTED_MARKERS = {
    "B cells": {"CD74", "CD79A", "CD37", "HLA-DRA", "MS4A1"},
    "CD14+ Monocytes": {"CTSD", "LYZ", "LST1", "S100A8", "S100A9"},
    "CD4 T cells": {"CCR7", "IL7R", "LTB", "MAL", "MALAT1"},
    "CD8 T cells": {"CCL5", "CD8A", "CD8B", "CST7", "LINC02446"},
    "FCGR3A+ Monocytes": {"FCGR3A", "IFITM3", "LGALS3BP", "LST1", "MS4A7"},
    "NK cells": {"CCL5", "GNLY", "GZMB", "NKG7", "PRF1"},
}


def package_version(name: str) -> str:
    return importlib.metadata.version(name)


def run(command: list[str], environment: dict[str, str], timeout: int = 1200) -> None:
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
            "public GSE96583 marker workflow failed: "
            + completed.stderr[-4000:]
        )


def marker_command(
    scientific_python: Path,
    input_h5ad: Path,
    output_tsv: Path,
    report_path: Path,
) -> list[str]:
    return [
        str(scientific_python),
        str(TEMPLATE),
        "--input-h5ad",
        str(input_h5ad),
        "--output-tsv",
        str(output_tsv),
        "--report",
        str(report_path),
        "--cluster-key",
        "cell_type",
        "--sample-key",
        "donor",
        "--raw-count-location",
        "layers.counts",
        "--validation-samples",
        ",".join(VALIDATION_DONORS),
        "--method",
        "wilcoxon",
        "--top-per-cluster",
        "150",
        "--min-in-fraction",
        "0.10",
        "--max-out-fraction",
        "0.75",
        "--min-logfc",
        "0.25",
        "--max-adjusted-p",
        "0.05",
        "--min-sample-support",
        "5",
        "--min-validation-sample-support",
        "2",
        "--min-cells-per-sample-contrast",
        "3",
        "--seed",
        "2026",
    ]


def verify(source_dir: Path | None, scientific_python: Path) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    if not python.is_file():
        raise FileNotFoundError(f"scientific Python is absent: {python}")
    version_probe = subprocess.run(
        [
            str(python),
            "-c",
            "import importlib.metadata as m; print(m.version('scanpy')); print(m.version('anndata'))",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    ).stdout.splitlines()
    if version_probe != ["1.10.4", "0.10.8"]:
        raise RuntimeError("public marker case requires Scanpy 1.10.4 and AnnData 0.10.8")

    with tempfile.TemporaryDirectory(prefix="biomed-public-gse96583-markers-") as temporary:
        work = Path(temporary)
        paths = acquire_sources(
            work,
            source_dir.expanduser().resolve() if source_dir else None,
        )
        source_digests_before = {key: sha256(path) for key, path in paths.items()}
        members = extract_members(paths["archive"], work / "raw")
        metadata = pd.read_csv(paths["metadata"], sep="\t", index_col=0)
        genes = pd.read_csv(paths["genes"], sep="\t", header=None)
        counts, obs, normalized_barcodes = read_condition(
            members["ctrl_matrix"],
            members["ctrl_barcodes"],
            metadata,
            "ctrl",
        )
        cell_keep = obs["cell_type"].isin(CELL_TYPES).to_numpy()
        counts = sparse.csr_matrix(counts[cell_keep, :], dtype=np.int64)
        obs = obs.loc[cell_keep].copy()
        detected_cells = np.asarray((counts > 0).sum(axis=0)).reshape(-1)
        total_counts = np.asarray(counts.sum(axis=0)).reshape(-1)
        feature_keep = (detected_cells >= 20) & (total_counts >= 20)
        counts = sparse.csr_matrix(counts[:, feature_keep], dtype=np.int64)
        gene_names = np.asarray(unique_gene_names(genes), dtype=object)[feature_keep]
        var = pd.DataFrame(
            {
                "ensembl_id": genes.iloc[:, 0].astype(str).to_numpy()[feature_keep],
                "source_detected_cells": detected_cells[feature_keep],
                "source_total_counts": total_counts[feature_keep],
            },
            index=pd.Index(gene_names.astype(str)),
        )
        if (
            set(obs["donor"].astype(str)) != EXPECTED_DONORS
            or set(obs["cell_type"].astype(str)) != set(CELL_TYPES)
            or counts.shape[0] != len(obs)
            or counts.shape[1] < 10_000
            or not obs.index.is_unique
            or not var.index.is_unique
            or counts.data.size == 0
            or counts.data.min() < 0
            or not np.allclose(counts.data, np.rint(counts.data), rtol=0, atol=1e-8)
        ):
            raise RuntimeError("GSE96583 control marker input failed identity or count gates")
        sample_cross_tab = pd.crosstab(obs["cell_type"], obs["donor"]).reindex(
            index=CELL_TYPES,
            columns=DISCOVERY_DONORS + VALIDATION_DONORS,
            fill_value=0,
        )
        if int(sample_cross_tab.min().min()) < 15:
            raise RuntimeError("GSE96583 major cell types lack per-donor representation")

        adata = ad.AnnData(X=counts.copy(), obs=obs, var=var)
        adata.layers["counts"] = counts.copy()
        adata.uns["marker_public_case"] = {
            "accession": "GSE96583",
            "condition": "ctrl",
            "cell_type_source": "publisher-provided",
            "feature_filter": "detected-in-at-least-20-cells-and-total-count-at-least-20",
            "discovery_donors": DISCOVERY_DONORS,
            "validation_donors": VALIDATION_DONORS,
        }
        input_h5ad = work / "gse96583-control-major-cell-types.h5ad"
        adata.write_h5ad(input_h5ad, compression="gzip")
        input_digest = sha256(input_h5ad)

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

        marker_paths: list[Path] = []
        report_paths: list[Path] = []
        for repeat in (1, 2):
            marker_path = work / f"markers-{repeat}.tsv"
            report_path = work / f"marker-report-{repeat}.json"
            run(
                marker_command(python, input_h5ad, marker_path, report_path),
                environment,
            )
            marker_paths.append(marker_path)
            report_paths.append(report_path)
        if marker_paths[0].read_bytes() != marker_paths[1].read_bytes():
            raise RuntimeError("GSE96583 marker discovery is not exactly repeatable")

        marker_report = json.loads(report_paths[0].read_text(encoding="utf-8"))
        markers = pd.read_csv(marker_paths[0], sep="\t")
        validated = markers.loc[markers["independently_validated_marker"].eq(True)].copy()
        recovered_markers = {
            cell_type: sorted(
                set(
                    validated.loc[
                        validated["cluster"].eq(cell_type),
                        "gene",
                    ].astype(str)
                ).intersection(expected)
            )
            for cell_type, expected in EXPECTED_MARKERS.items()
        }
        recovered_families = [
            cell_type for cell_type, values in recovered_markers.items() if values
        ]
        validated_by_cluster = (
            validated.groupby("cluster").size().reindex(CELL_TYPES, fill_value=0)
        )
        quality_checks = {
            "official_source_digests": source_digests_before
            == {key: str(value["sha256"]) for key, value in SOURCES.items()},
            "control_singlets_and_major_labels_only": (
                set(obs["condition"]) == {"ctrl"}
                and set(obs["cell_type"]) == set(CELL_TYPES)
            ),
            "label_independent_feature_filter": counts.shape[1] >= 10_000,
            "six_discovery_and_two_validation_donors": (
                len(marker_report["sample_split"]["discovery_samples"]) == 6
                and set(marker_report["sample_split"]["discovery_samples"])
                == set(DISCOVERY_DONORS)
                and len(marker_report["sample_split"]["validation_samples"]) == 2
                and set(marker_report["sample_split"]["validation_samples"])
                == set(VALIDATION_DONORS)
            ),
            "validation_excluded_from_ranking_and_threshold_selection": (
                marker_report["sample_split"][
                    "validation_used_for_ranking_or_threshold_selection"
                ]
                is False
            ),
            "all_six_cell_types_have_five_validated_markers": bool(
                (validated_by_cluster >= 5).all()
            ),
            "five_canonical_marker_families_recovered": len(recovered_families) >= 5,
            "cell_level_statistics_limited_to_descriptive_scope": (
                set(markers["inferential_scope"])
                == {"descriptive-cell-level-ranking-not-donor-level-inference"}
            ),
            "exact_repeatability": True,
            "source_immutability": (
                sha256(input_h5ad) == input_digest
                and source_digests_before
                == {key: sha256(path) for key, path in paths.items()}
            ),
            "result_reload_and_quality_status": (
                marker_report["quality_status"] == "passed"
                and marker_report["quality"]["output_reloaded"] is True
            ),
        }
        if not all(quality_checks.values()):
            raise RuntimeError(
                "GSE96583 marker acceptance failed: "
                + json.dumps(
                    {
                        "checks": quality_checks,
                        "validated_by_cluster": validated_by_cluster.to_dict(),
                        "recovered_markers": recovered_markers,
                    },
                    sort_keys=True,
                )
            )
        runtime = {
            "python": marker_report["versions"]["python"],
            "scanpy": marker_report["versions"]["scanpy"],
            "anndata": marker_report["versions"]["anndata"],
            "numpy": marker_report["versions"]["numpy"],
            "pandas": marker_report["versions"]["pandas"],
            "scipy": marker_report["versions"]["scipy"],
        }
        execution = {
            "input_control_singlets": int(len(obs)),
            "retained_features": int(counts.shape[1]),
            "cell_types": len(CELL_TYPES),
            "discovery_donors": DISCOVERY_DONORS,
            "validation_donors": VALIDATION_DONORS,
            "cells_by_cell_type_and_donor": {
                cell_type: {
                    donor: int(sample_cross_tab.loc[cell_type, donor])
                    for donor in sample_cross_tab.columns
                }
                for cell_type in sample_cross_tab.index
            },
            "tested_marker_rows": int(len(markers)),
            "discovery_admitted_rows": int(
                markers["discovery_admitted_marker"].sum()
            ),
            "independently_validated_rows": int(len(validated)),
            "independently_validated_rows_by_cell_type": {
                key: int(value) for key, value in validated_by_cluster.items()
            },
            "expected_marker_families": {
                key: sorted(value) for key, value in EXPECTED_MARKERS.items()
            },
            "recovered_expected_markers": recovered_markers,
            "recovered_expected_marker_families": recovered_families,
            "exact_repeat_marker_tsv": True,
            "ephemeral_input_h5ad_sha256": input_digest,
            "ephemeral_marker_tsv_sha256": sha256(marker_paths[0]),
        }

    return {
        "schema_version": 1,
        "passed": True,
        "case_id": "gse96583-held-out-donor-marker-discovery-v1",
        "case_type": "public-data-end-to-end",
        "module": {
            "id": MODULE_ID,
            "version": "1.1.0",
            "compatibility_row_id": ROW_ID,
            "manifest_sha256": sha256(MANIFEST),
            "template_sha256": sha256(TEMPLATE),
        },
        "source": {
            "publisher": "NCBI Gene Expression Omnibus",
            "accession": "GSE96583",
            "title": "Multiplexing droplet-based single cell RNA-sequencing using genetic barcodes",
            "study_record": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE96583",
            "publication_pmid": "29227470",
            "assay": "10x single-cell RNA-seq PBMC control arm",
            "files": {
                key: {
                    "filename": str(value["filename"]),
                    "sha256": str(value["sha256"]),
                }
                for key, value in SOURCES.items()
            },
            "barcode_normalizations": normalized_barcodes,
        },
        "parameters": {
            "condition": "ctrl",
            "cell_types": CELL_TYPES,
            "feature_filter": {
                "minimum_detected_cells": 20,
                "minimum_total_count": 20,
                "uses_cell_type_labels": False,
            },
            "sample_split_frozen_before_ranking": True,
            "discovery_donors": DISCOVERY_DONORS,
            "validation_donors": VALIDATION_DONORS,
            "ranking": "Scanpy Wilcoxon cluster-versus-rest",
            "top_per_cluster": 150,
            "minimum_discovery_support": 5,
            "minimum_validation_support": 2,
            "minimum_in_fraction": 0.10,
            "maximum_out_fraction": 0.75,
            "minimum_log2_fold_change": 0.25,
            "maximum_adjusted_cell_level_p": 0.05,
        },
        "runtime": runtime,
        "execution": execution,
        "quality_gates": {
            key: "pass" for key, passed in quality_checks.items() if passed
        },
        "scientific_boundaries": [
            "Publisher-provided cell-type labels define the cluster contrasts; the case tests marker evidence generation and does not independently establish those labels.",
            "Discovery and held-out donor identities and all thresholds are frozen before ranking; held-out donors are used only after candidate generation.",
            "Scanpy cell-level p-values are retained as descriptive ranking evidence and are not interpreted as donor-level differential-expression inference.",
            "Canonical marker families are a bounded posthoc positive-control check and are not used to tune ranks, thresholds, or donor roles.",
            "Validation is limited to control PBMCs from eight GSE96583 donors and does not establish specificity in another tissue, disease, chemistry, cohort, or annotation granularity.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "public-case-gse96583-marker-discovery.json",
    )
    args = parser.parse_args()
    report = verify(args.source_dir, args.scientific_python)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "case_id": report["case_id"],
                "cells": report["execution"]["input_control_singlets"],
                "validated_markers": report["execution"][
                    "independently_validated_rows"
                ],
                "recovered_families": len(
                    report["execution"]["recovered_expected_marker_families"]
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
