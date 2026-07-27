#!/usr/bin/env python3
"""Validate held-out-donor SingleR annotation on public GSE96583 PBMC data."""

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
import scanpy as sc
from scipy import sparse
from sklearn.metrics import accuracy_score, f1_score

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

MODULE_ID = "single-cell-reference-annotation"
ROW_ID = "agent-protocol-1-singler-241-scanpy-1115-r-432"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
PYTHON_TEMPLATE = MODULE_ROOT / "templates" / "annotate_reference.py"
R_TEMPLATE = MODULE_ROOT / "templates" / "run_singler.R"
REFERENCE_DONORS = ["101", "107", "1015", "1016", "1039", "1244"]
QUERY_DONORS = ["1256", "1488"]
HELD_OUT_LABEL = "Megakaryocytes"
UNKNOWN_LABEL = "Unknown"
MAX_REFERENCE_CELLS_PER_LABEL = 120
SEED = 96583

MARKERS = {
    "B cells": {
        "positive": ["MS4A1", "CD79A", "CD74", "CD37"],
        "negative": ["NKG7", "LST1", "S100A8"],
    },
    "CD14+ Monocytes": {
        "positive": ["LST1", "S100A8", "S100A9", "CTSD", "LYZ"],
        "negative": ["MS4A1", "NKG7", "CD3D"],
    },
    "CD4 T cells": {
        "positive": ["CD3D", "CD3E", "IL7R", "LTB"],
        "negative": ["NKG7", "LST1", "MS4A1"],
    },
    "CD8 T cells": {
        "positive": ["CD3D", "CD3E", "CD8A", "CCL5"],
        "negative": ["MS4A1", "LST1", "S100A8"],
    },
    "Dendritic cells": {
        "positive": ["FCER1A", "CST3", "CD1C"],
        "negative": ["CD3D", "NKG7", "MS4A1"],
    },
    "FCGR3A+ Monocytes": {
        "positive": ["LST1", "FCGR3A", "MS4A7", "IFITM3"],
        "negative": ["MS4A1", "CD3D", "NKG7"],
    },
    "NK cells": {
        "positive": ["NKG7", "GNLY", "KLRD1", "PRF1"],
        "negative": ["CD3D", "MS4A1", "LST1"],
    },
}

LABEL_TO_ONTOLOGY = {
    "B cells": "CL:0000236",
    "CD14+ Monocytes": "CL:0000860",
    "CD4 T cells": "CL:0000624",
    "CD8 T cells": "CL:0000625",
    "Dendritic cells": "CL:0000451",
    "FCGR3A+ Monocytes": "CL:0000875",
    "NK cells": "CL:0000623",
}

ONTOLOGY_PARENTS = {
    "CL:0000236": ["CL:0000542"],
    "CL:0000624": ["CL:0000084"],
    "CL:0000625": ["CL:0000084"],
    "CL:0000084": ["CL:0000542"],
    "CL:0000623": ["CL:0000542"],
    "CL:0000860": ["CL:0000576"],
    "CL:0000875": ["CL:0000576"],
    "CL:0000576": ["CL:0000763"],
    "CL:0000451": ["CL:0000763"],
    "CL:0000542": ["CL:0000738"],
    "CL:0000763": ["CL:0000738"],
    "CL:0000738": ["CL:0000000"],
    "CL:0000556": ["CL:0000000"],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_reference_indices(obs: pd.DataFrame) -> np.ndarray:
    selected: list[int] = []
    labels = obs["reference_label"].astype(str).to_numpy()
    for label in sorted(MARKERS):
        candidates = np.flatnonzero(labels == label)
        ranked = sorted(
            candidates,
            key=lambda index: hashlib.sha256(
                f"{SEED}:{obs.index[index]}".encode()
            ).hexdigest(),
        )
        selected.extend(ranked[:MAX_REFERENCE_CELLS_PER_LABEL])
    return np.asarray(sorted(selected), dtype=int)


def cluster_query(query: ad.AnnData) -> tuple[np.ndarray, dict[str, object]]:
    analysis = query.copy()
    sc.pp.normalize_total(analysis, target_sum=1e4)
    sc.pp.log1p(analysis)
    sc.pp.highly_variable_genes(
        analysis, n_top_genes=2500, flavor="seurat", subset=False
    )
    sc.pp.pca(
        analysis,
        n_comps=40,
        mask_var="highly_variable",
        random_state=SEED,
    )
    sc.pp.neighbors(analysis, n_neighbors=20, n_pcs=40, random_state=SEED)
    sc.tl.leiden(
        analysis,
        resolution=1.2,
        random_state=SEED,
        key_added="reference_query_cluster",
        flavor="leidenalg",
        n_iterations=-1,
        directed=True,
    )
    clusters = analysis.obs["reference_query_cluster"].astype(str).to_numpy()
    platelet_genes = ["PF4", "PPBP"]
    if any(gene not in analysis.var_names for gene in platelet_genes):
        raise RuntimeError("held-out platelet-lineage markers are absent")
    marker_values = analysis[:, platelet_genes].X
    marker_values = (
        marker_values.toarray() if sparse.issparse(marker_values) else np.asarray(marker_values)
    )
    marker_sum = marker_values.sum(axis=1)
    cluster_records: dict[str, object] = {}
    platelet_clusters: list[str] = []
    for cluster in sorted(set(clusters)):
        members = clusters == cluster
        record = {
            "cells": int(members.sum()),
            "mean_log1p_pf4_ppbp": float(marker_sum[members].mean()),
            "fraction_pf4_or_ppbp_detected": float(
                np.mean((marker_values[members] > 0).any(axis=1))
            ),
        }
        record["platelet_lineage_gate"] = (
            record["mean_log1p_pf4_ppbp"] >= 2.0
            and record["fraction_pf4_or_ppbp_detected"] >= 0.5
        )
        if record["platelet_lineage_gate"]:
            platelet_clusters.append(cluster)
        cluster_records[cluster] = record
    if not platelet_clusters:
        raise RuntimeError("predeclared PF4/PPBP rule found no platelet-lineage cluster")
    return clusters, {
        "method": "Scanpy PCA-neighbor-Leiden without publisher labels",
        "seed": SEED,
        "highly_variable_genes": 2500,
        "n_pcs": 40,
        "n_neighbors": 20,
        "resolution": 1.2,
        "platelet_rule": {
            "genes": platelet_genes,
            "minimum_mean_log1p_sum": 2.0,
            "minimum_detection_fraction": 0.5,
        },
        "platelet_clusters": platelet_clusters,
        "clusters": cluster_records,
    }


def run_template(
    python: Path,
    rscript: Path,
    query_path: Path,
    reference_path: Path,
    marker_path: Path,
    ontology_path: Path,
    output_path: Path,
    report_path: Path,
    environment: dict[str, str],
) -> None:
    command = [
        str(python),
        str(PYTHON_TEMPLATE),
        "--query-h5ad",
        str(query_path),
        "--reference-h5ad",
        str(reference_path),
        "--output-h5ad",
        str(output_path),
        "--report",
        str(report_path),
        "--rscript",
        str(rscript),
        "--query-raw-count-location",
        "layers.counts",
        "--reference-raw-count-location",
        "layers.counts",
        "--reference-label-key",
        "reference_label",
        "--query-group-key",
        "reference_query_cluster",
        "--existing-label-key",
        "existing_label",
        "--evaluation-label-key",
        "none",
        "--unknown-label",
        UNKNOWN_LABEL,
        "--marker-panel",
        str(marker_path),
        "--ontology-contract",
        str(ontology_path),
        "--minimum-common-genes",
        "30000",
        "--minimum-query-gene-fraction",
        "0.95",
        "--minimum-delta-next",
        "0.0",
        "--minimum-group-consensus",
        "0.55",
        "--minimum-positive-marker-support",
        "0.5",
        "--maximum-negative-marker-conflict",
        "0.5",
        "--minimum-marker-log-expression-difference",
        "0.1",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "public reference annotation failed:\n"
            + completed.stdout[-1500:]
            + "\n"
            + completed.stderr[-4000:]
        )


def verify(
    source_dir: Path | None,
    scientific_python: Path,
    rscript: Path,
) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    r = rscript.expanduser().resolve(strict=True)
    if not python.is_file():
        raise FileNotFoundError(f"scientific Python is absent: {python}")
    with tempfile.TemporaryDirectory(prefix="biomed-public-gse96583-reference-") as temp:
        work = Path(temp)
        paths = acquire_sources(
            work, source_dir.expanduser().resolve(strict=True) if source_dir else None
        )
        source_digests_before = {name: sha256(path) for name, path in paths.items()}
        members = extract_members(paths["archive"], work / "raw")
        metadata = pd.read_csv(paths["metadata"], sep="\t", index_col=0)
        genes = pd.read_csv(paths["genes"], sep="\t", header=None)
        counts, obs, normalization_count = read_condition(
            members["ctrl_matrix"],
            members["ctrl_barcodes"],
            metadata,
            "ctrl",
        )
        obs["donor"] = obs["donor"].astype(str)
        if set(obs["donor"]) != set(REFERENCE_DONORS + QUERY_DONORS):
            raise RuntimeError("GSE96583 donor identities differ from the frozen split")

        reference_mask = obs["donor"].isin(REFERENCE_DONORS) & ~obs["cell_type"].eq(
            HELD_OUT_LABEL
        )
        query_mask = obs["donor"].isin(QUERY_DONORS)
        reference_obs = obs.loc[reference_mask].copy()
        reference_obs["reference_label"] = reference_obs["cell_type"].astype(str)
        reference_indices = stable_reference_indices(reference_obs)
        reference_obs = reference_obs.iloc[reference_indices].copy()
        reference_counts = counts[np.flatnonzero(reference_mask), :][
            reference_indices, :
        ]
        query_obs_with_truth = obs.loc[query_mask].copy()
        query_counts = counts[np.flatnonzero(query_mask), :]
        truth = query_obs_with_truth["cell_type"].astype(str).copy()

        var = pd.DataFrame(
            {"ensembl_id": genes.iloc[:, 0].astype(str).tolist()},
            index=unique_gene_names(genes),
        )
        query_for_clustering = ad.AnnData(
            X=query_counts.copy(),
            obs=query_obs_with_truth[["donor"]].copy(),
            var=var.copy(),
        )
        clusters, clustering = cluster_query(query_for_clustering)
        query_obs = pd.DataFrame(
            {
                "donor": query_obs_with_truth["donor"].astype(str).to_numpy(),
                "reference_query_cluster": clusters,
                "existing_label": UNKNOWN_LABEL,
            },
            index=query_obs_with_truth.index.copy(),
        )
        query = ad.AnnData(X=query_counts.copy(), obs=query_obs, var=var.copy())
        query.layers["counts"] = query_counts.copy()
        reference = ad.AnnData(
            X=reference_counts.copy(), obs=reference_obs, var=var.copy()
        )
        reference.layers["counts"] = reference_counts.copy()

        query_path = work / "gse96583-held-out-query.h5ad"
        reference_path = work / "gse96583-reviewed-reference.h5ad"
        query.write_h5ad(query_path, compression="gzip")
        reference.write_h5ad(reference_path, compression="gzip")
        marker_path = work / "marker-contract.json"
        marker_path.write_text(
            json.dumps(MARKERS, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        allowed_by_group = {
            cluster: (
                ["CL:0000556"]
                if cluster in clustering["platelet_clusters"]
                else ["CL:0000738"]
            )
            for cluster in sorted(set(clusters))
        }
        ontology = {
            "label_to_ontology": LABEL_TO_ONTOLOGY,
            "parents": ONTOLOGY_PARENTS,
            "allowed_by_group": allowed_by_group,
        }
        ontology_path = work / "ontology-contract.json"
        ontology_path.write_text(
            json.dumps(ontology, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        environment = dict(os.environ)
        environment["PYTHONHASHSEED"] = "0"
        for name, variable in (
            ("numba", "NUMBA_CACHE_DIR"),
            ("matplotlib", "MPLCONFIGDIR"),
            ("cache", "XDG_CACHE_HOME"),
        ):
            directory = work / name
            directory.mkdir()
            environment[variable] = str(directory)
        output_path = work / "annotated.h5ad"
        analysis_report_path = work / "analysis.json"
        run_template(
            python,
            r,
            query_path,
            reference_path,
            marker_path,
            ontology_path,
            output_path,
            analysis_report_path,
            environment,
        )
        analysis = json.loads(analysis_report_path.read_text(encoding="utf-8"))
        output = ad.read_h5ad(output_path)
        prediction = output.obs["reference_conservative_label"].astype(str)
        truth = truth.loc[output.obs_names]
        known = truth != HELD_OUT_LABEL
        held_out = truth == HELD_OUT_LABEL
        accepted_known = known & prediction.ne(UNKNOWN_LABEL)
        known_accuracy = float(
            accuracy_score(truth.loc[accepted_known], prediction.loc[accepted_known])
        )
        known_coverage = float(np.mean(prediction.loc[known].ne(UNKNOWN_LABEL)))
        known_macro_f1 = float(
            f1_score(
                truth.loc[known],
                prediction.loc[known],
                labels=sorted(MARKERS),
                average="macro",
                zero_division=0,
            )
        )
        held_out_unknown_retention = float(
            np.mean(prediction.loc[held_out].eq(UNKNOWN_LABEL))
        )
        per_label = {}
        for label in sorted(set(truth)):
            members = truth == label
            per_label[label] = {
                "cells": int(members.sum()),
                "accepted_fraction": float(
                    np.mean(prediction.loc[members].ne(UNKNOWN_LABEL))
                ),
                "correct_or_unknown_fraction": float(
                    np.mean(
                        prediction.loc[members].isin(
                            [label, UNKNOWN_LABEL]
                            if label != HELD_OUT_LABEL
                            else [UNKNOWN_LABEL]
                        )
                    )
                ),
            }

        source_digests_after = {name: sha256(path) for name, path in paths.items()}
        quality_gates = {
            "source_identity_and_immutability": "pass"
            if source_digests_before == source_digests_after
            else "fail",
            "six_reference_two_query_donor_split": "pass",
            "publisher_labels_absent_from_method_inputs": "pass",
            "reference_missing_class_predeclared": "pass",
            "query_clusters_and_ontology_constraints_label_independent": "pass",
            "known_label_accuracy": "pass" if known_accuracy >= 0.75 else "fail",
            "known_label_coverage": "pass" if known_coverage >= 0.50 else "fail",
            "known_macro_f1": "pass" if known_macro_f1 >= 0.55 else "fail",
            "held_out_class_unknown_retention": "pass"
            if held_out_unknown_retention >= 0.50
            else "fail",
            "all_cells_counts_and_existing_labels_preserved": "pass"
            if all(analysis["quality_gates"].values())
            else "fail",
        }
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        report = {
            "schema_version": 1,
            "case_id": "gse96583-held-out-donor-reference-annotation-v1",
            "case_type": "public-data-end-to-end",
            "passed": set(quality_gates.values()) == {"pass"},
            "module": {
                "id": MODULE_ID,
                "version": registry.get(MODULE_ID).version,
                "compatibility_row_id": ROW_ID,
                "manifest_sha256": sha256(MANIFEST),
                "template_sha256": {
                    PYTHON_TEMPLATE.name: sha256(PYTHON_TEMPLATE),
                    R_TEMPLATE.name: sha256(R_TEMPLATE),
                },
                "registry_digest": registry.digest,
            },
            "source": {
                "accession": "GSE96583",
                "files": SOURCES,
                "source_validation": {
                    "control_singlets_with_cell_type": int(len(obs)),
                    "metadata_barcode_normalizations": normalization_count,
                    "reference_donors": REFERENCE_DONORS,
                    "query_donors": QUERY_DONORS,
                    "reference_cells_after_balancing": int(reference.n_obs),
                    "query_cells": int(query.n_obs),
                    "genes": int(query.n_vars),
                },
            },
            "parameters": {
                "donor_split_frozen_before_mapping": True,
                "publisher_labels_available_to_mapping": False,
                "publisher_labels_used_for_threshold_selection": False,
                "held_out_reference_label": HELD_OUT_LABEL,
                "reference_cells_per_label_maximum": MAX_REFERENCE_CELLS_PER_LABEL,
                "reference_selection": "stable SHA-256 order within each label",
                "clustering": clustering,
                "thresholds": analysis["thresholds"],
            },
            "runtime": analysis["versions"],
            "execution": {
                "accepted_cells": analysis["annotation"]["accepted_cells"],
                "unknown_cells": analysis["annotation"]["unknown_cells"],
                "known_label_accuracy_among_accepted": known_accuracy,
                "known_label_coverage": known_coverage,
                "known_macro_f1_with_unknown_penalty": known_macro_f1,
                "held_out_class_cells": int(held_out.sum()),
                "held_out_class_unknown_retention": held_out_unknown_retention,
                "per_publisher_label": per_label,
                "group_results": analysis["annotation"]["group_results"],
                "all_query_cells_accounted": len(prediction) == len(query),
                "source_artifacts_immutable": source_digests_before
                == source_digests_after,
                "output_reloaded": True,
                "raw_counts_preserved": analysis["quality_gates"][
                    "raw_counts_preserved"
                ],
                "existing_labels_preserved": analysis["quality_gates"][
                    "existing_labels_preserved"
                ],
            },
            "quality_gates": quality_gates,
            "scientific_boundaries": [
                "Six control-arm donors formed the reviewed reference and two disjoint control-arm donors formed the query.",
                "Publisher query labels were absent from the query H5AD, marker contract, ontology contract, clustering, SingleR execution, and all thresholds.",
                "Megakaryocytes were removed from the reference before execution and evaluated only as a predeclared absent-reference population.",
                "The PF4/PPBP platelet-lineage ontology rule was applied to label-independent query clusters before SingleR outputs were inspected.",
                "Publisher labels were joined by exact cell identity only after the annotated H5AD and all decisions were frozen.",
                "Performance is specific to GSE96583 control PBMCs, this donor split, reference balancing, contracts, thresholds, and recorded runtimes.",
            ],
        }
        if not report["passed"]:
            raise RuntimeError(
                "GSE96583 reference annotation failed frozen gates: "
                + json.dumps(quality_gates, sort_keys=True)
                + "\nmetrics="
                + json.dumps(
                    {
                        "accuracy": known_accuracy,
                        "coverage": known_coverage,
                        "macro_f1": known_macro_f1,
                        "held_out_unknown": held_out_unknown_retention,
                    },
                    sort_keys=True,
                )
            )
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--rscript", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "reports"
        / "public-case-gse96583-reference-annotation.json",
    )
    args = parser.parse_args()
    report = verify(args.source_dir, args.scientific_python, args.rscript)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "case_id": report["case_id"],
                "passed": report["passed"],
                "known_accuracy": report["execution"][
                    "known_label_accuracy_among_accepted"
                ],
                "known_coverage": report["execution"]["known_label_coverage"],
                "held_out_unknown_retention": report["execution"][
                    "held_out_class_unknown_retention"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
