#!/usr/bin/env python3
"""Validate single-lineage topology on public mouse-gastrulation erythroid data."""

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

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402
from tests.evidence.verify_public_gastrulation_erythroid_velocity_case import (  # noqa: E402
    SOURCE,
    STAGE_TO_DAY,
    acquire_source,
    sha256,
)

MODULE_ID = "single-cell-trajectory-topology"
ROW_ID = "agent-protocol-1-slingshot-210-monocle3-1426-tradeseq-116"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
TEMPLATE = MODULE_ROOT / "templates" / "run_slingshot_monocle_tradeseq.R"
MAX_CELLS_PER_SAMPLE = 12
N_FEATURES = 160
SEED = 20260723
START_CLUSTER = "Blood progenitors 1"
END_CLUSTER = "Erythroid3"


def stable_sample_indices(obs: pd.DataFrame) -> np.ndarray:
    selected: list[int] = []
    sample = obs["sample"].astype(str).to_numpy()
    for value in sorted(set(sample)):
        candidates = np.flatnonzero(sample == value)
        ranked = sorted(
            candidates,
            key=lambda index: hashlib.sha256(
                f"{SEED}:{obs.index[index]}".encode()
            ).hexdigest(),
        )
        selected.extend(ranked[:MAX_CELLS_PER_SAMPLE])
    return np.asarray(sorted(selected), dtype=int)


def run(command: list[str], environment: dict[str, str]) -> None:
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
            "public erythroid topology failed:\n"
            + completed.stdout[-2000:]
            + "\n"
            + completed.stderr[-6000:]
        )


def verify(
    source_dir: Path | None,
    scientific_python: Path,
    rscript: Path,
    r_library: Path | None,
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

    with tempfile.TemporaryDirectory(
        prefix="biomed-public-erythroid-topology-"
    ) as temporary:
        work = Path(temporary)
        source = acquire_source(work, source_dir)
        source_digest_before = sha256(source)
        adata = ad.read_h5ad(source)
        if adata.shape != (9815, 53801) or "X_umap" not in adata.obsm:
            raise RuntimeError("public erythroid source differs from contract")
        counts = sparse.csr_matrix(adata.layers["spliced"])
        if (
            not counts.data.size
            or not np.isfinite(counts.data).all()
            or np.min(counts.data) < 0
            or not np.allclose(counts.data, np.rint(counts.data))
        ):
            raise RuntimeError("public spliced layer is not integer-like")

        selected_cells = stable_sample_indices(adata.obs)
        query_counts = counts[selected_cells]
        detected = np.asarray((query_counts > 0).sum(axis=0)).ravel()
        totals = np.asarray(query_counts.sum(axis=0)).ravel()
        ranked_features = np.lexsort(
            (np.arange(query_counts.shape[1]), -totals, -detected)
        )
        selected_features = np.sort(ranked_features[:N_FEATURES])
        query_counts = query_counts[:, selected_features].astype(np.int64)
        obs = adata.obs.iloc[selected_cells].copy()
        cells = obs.index.astype(str).tolist()
        genes = adata.var_names[selected_features].astype(str).tolist()
        obs["external_time"] = (
            obs["stage"].astype(str).map(STAGE_TO_DAY).astype(float)
        )
        if (
            obs["sample"].nunique() != 27
            or obs["external_time"].nunique() != 7
            or START_CLUSTER not in set(obs["celltype"].astype(str))
            or END_CLUSTER not in set(obs["celltype"].astype(str))
        ):
            raise RuntimeError("public erythroid subset lacks design anchors")
        root_candidates = sorted(
            obs.index[obs["celltype"].astype(str).eq(START_CLUSTER)].astype(str),
            key=lambda cell: hashlib.sha256(f"root:{SEED}:{cell}".encode()).hexdigest(),
        )
        root_cells = root_candidates[: min(20, len(root_candidates))]
        if len(root_cells) < 3:
            raise RuntimeError("public erythroid subset has too few root cells")

        counts_path = work / "counts.tsv"
        metadata_path = work / "metadata.tsv"
        embedding_path = work / "embedding.tsv"
        pd.DataFrame(
            query_counts.T.toarray(),
            index=genes,
            columns=cells,
        ).rename_axis("gene_id").reset_index().to_csv(
            counts_path, sep="\t", index=False
        )
        pd.DataFrame(
            {
                "cell_id": cells,
                "cluster": obs["celltype"].astype(str).to_numpy(),
                "sample": obs["sample"].astype(str).to_numpy(),
                "external_time": obs["external_time"].to_numpy(),
            }
        ).to_csv(metadata_path, sep="\t", index=False)
        pd.DataFrame(
            np.asarray(adata.obsm["X_umap"])[selected_cells],
            index=cells,
            columns=["UMAP1", "UMAP2"],
        ).rename_axis("cell_id").reset_index().to_csv(
            embedding_path, sep="\t", index=False
        )

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
        if r_library is not None:
            environment["R_LIBS_USER"] = str(
                r_library.expanduser().resolve(strict=True)
            )
        for name, variable in (("home", "HOME"), ("cache", "XDG_CACHE_HOME")):
            directory = work / name
            directory.mkdir()
            environment[variable] = str(directory)

        cell_results = work / "trajectory-cells.tsv"
        gene_results = work / "trajectory-genes.tsv"
        cds_output = work / "monocle-object"
        analysis_path = work / "topology.json"
        run(
            [
                str(r_executable),
                str(TEMPLATE),
                "--counts",
                str(counts_path),
                "--metadata",
                str(metadata_path),
                "--embedding",
                str(embedding_path),
                "--cell-results",
                str(cell_results),
                "--gene-results",
                str(gene_results),
                "--cds-output",
                str(cds_output),
                "--report",
                str(analysis_path),
                "--cluster-key",
                "cluster",
                "--sample-key",
                "sample",
                "--external-time-key",
                "external_time",
                "--start-cluster",
                START_CLUSTER,
                "--end-clusters",
                END_CLUSTER,
                "--root-cells",
                ",".join(root_cells),
                "--nknots",
                "5",
                "--minimum-lineage-cells",
                "40",
                "--minimum-time-correlation",
                "0.15",
                "--seed",
                str(SEED),
            ],
            environment,
        )
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        cells_reloaded = pd.read_csv(cell_results, sep="\t")
        genes_reloaded = pd.read_csv(gene_results, sep="\t")
        source_digest_after = sha256(source)
        results = analysis["results"]
        quality_gates = {
            "official_source_identity": "pass"
            if source_digest_before == source_digest_after == SOURCE["sha256"]
            else "fail",
            "integer_spliced_counts_and_label_blind_selection": "pass",
            "multiple_samples_and_external_stages": "pass"
            if obs["sample"].nunique() == 27
            and obs["external_time"].nunique() == 7
            else "fail",
            "single_lineage_supported": "pass"
            if len(results["lineage_cell_support"]) == 1
            and min(results["lineage_cell_support"].values()) >= 40
            else "fail",
            "independent_time_direction": "pass"
            if results["slingshot_external_time_spearman"] >= 0.15
            and results["monocle3_external_time_spearman"] >= 0.15
            else "fail",
            "independent_methods_concordant": "pass"
            if results["slingshot_monocle3_spearman"] > 0
            else "fail",
            "all_applicable_tradeseq_tests_completed": "pass"
            if results["association_rows"] == N_FEATURES
            and results["start_vs_end_rows"] == N_FEATURES
            and results["pattern_rows"] == 0
            and results["differential_end_rows"] == 0
            and results["test_applicability"]["pattern"]
            == "not_applicable_single_lineage"
            and results["test_applicability"]["differential_end"]
            == "not_applicable_single_lineage"
            else "fail",
            "outputs_reloaded_and_source_preserved": "pass"
            if analysis["quality_status"] == "passed"
            and len(cells_reloaded) == len(cells)
            and len(genes_reloaded) == N_FEATURES
            else "fail",
        }
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        report = {
            "schema_version": 1,
            "case_id": "gastrulation-erythroid-topology-v1",
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
                "dataset": "mouse gastrulation erythroid lineage",
                "publisher": "Pijuan-Sala et al.; scVelo public dataset",
                **SOURCE,
                "validation": {
                    "source_cells": adata.n_obs,
                    "source_genes": adata.n_vars,
                    "selected_cells": len(cells),
                    "selected_genes": N_FEATURES,
                    "samples": int(obs["sample"].nunique()),
                    "external_stages": int(obs["external_time"].nunique()),
                    "clusters": sorted(obs["celltype"].astype(str).unique()),
                    "root_cells": len(root_cells),
                    "feature_selection": (
                        "label-blind detected-cell count, then total count"
                    ),
                },
            },
            "parameters": {
                "maximum_cells_per_sample": MAX_CELLS_PER_SAMPLE,
                "start_cluster": START_CLUSTER,
                "end_clusters": [END_CLUSTER],
                "nknots": 5,
                "minimum_lineage_cells": 40,
                "minimum_time_correlation": 0.15,
                "seed": SEED,
            },
            "runtime": analysis["versions"],
            "execution": {
                "results": results,
                "source_artifact_immutable": source_digest_before
                == source_digest_after,
                "outputs_reloaded": True,
            },
            "quality_gates": quality_gates,
            "scientific_boundaries": [
                "Feature and cell sampling do not use stage or cell-type labels; external stage is used only for postfit direction validation.",
                "Published Blood progenitors 1 and Erythroid3 annotations are predeclared orientation anchors and do not establish ancestry.",
                "The 27 published samples establish dataset coverage, but tradeSeq cell-level trends are not donor-level condition inference.",
                "This public case validates one erythroid lineage; the deterministic bifurcation fixture separately validates two-lineage topology and differential-end tests.",
            ],
        }
        if not report["passed"]:
            raise RuntimeError(
                "public erythroid topology gates failed: "
                + json.dumps(quality_gates, sort_keys=True)
                + "; results="
                + json.dumps(results, sort_keys=True)
            )
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--rscript", type=Path, required=True)
    parser.add_argument("--r-library", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "reports"
        / "public-case-gastrulation-erythroid-topology.json",
    )
    args = parser.parse_args()
    report = verify(
        args.source_dir,
        args.scientific_python,
        args.rscript,
        args.r_library,
    )
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
                "lineages": len(
                    report["execution"]["results"]["lineage_cell_support"]
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
