#!/usr/bin/env python3
"""Validate count-backed spatial analysis on the public Squidpy SeqFISH data."""

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
import numpy as np
import pandas as pd
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402

MODULE_ID = "single-cell-spatial-analysis"
ROW_ID = "agent-protocol-1-squidpy-166-spatialdata-050-scanpy-1115"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
TEMPLATE = MODULE_ROOT / "templates" / "run_spatial_analysis.py"
SOURCE = {
    "dataset": "Squidpy SeqFISH mouse embryo",
    "filename": "seqfish.h5ad",
    "url": "https://ndownloader.figshare.com/files/26098403",
    "sha256": "7e544c0ede7538067537da69c52748ad01522ef7fc8691e077fd73c9434019f7",
}
SEED = 20260723
N_CELLS = 2000
N_MORAN_GENES = 20


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def acquire_source(work: Path, source: Path | None) -> Path:
    if source is None:
        path = work / SOURCE["filename"]
        urllib.request.urlretrieve(SOURCE["url"], path)
    else:
        path = source.expanduser().resolve(strict=True)
    if sha256(path) != SOURCE["sha256"]:
        raise RuntimeError("public SeqFISH source digest mismatch")
    return path


def run_template(
    python: Path,
    input_path: Path,
    genes: list[str],
    work: Path,
    environment: dict[str, str],
) -> None:
    completed = subprocess.run(
        [
            str(python),
            str(TEMPLATE),
            "--input-h5ad",
            str(input_path),
            "--output-h5ad",
            str(work / "spatial-output.h5ad"),
            "--observation-output",
            str(work / "observations.tsv"),
            "--graph-output",
            str(work / "spatial-graph.tsv"),
            "--neighborhood-output",
            str(work / "neighborhood.tsv"),
            "--cooccurrence-output",
            str(work / "cooccurrence.tsv"),
            "--moran-output",
            str(work / "moran.tsv"),
            "--spatial-genes-output",
            str(work / "spatial-genes.tsv"),
            "--report",
            str(work / "template-report.json"),
            "--sample-key",
            "biological_sample",
            "--cluster-key",
            "reviewed_cell_type",
            "--spatial-key",
            "spatial",
            "--coordinate-unit",
            "source-normalized-embryo-coordinate",
            "--genes",
            ",".join(genes),
            "--n-spatial-neighbors",
            "6",
            "--permutations",
            "99",
            "--cooccurrence-intervals",
            "10",
            "--svg-fdr",
            "0.05",
            "--minimum-moran",
            "0.1",
            "--minimum-supporting-samples",
            "1",
            "--domain-hvgs",
            "250",
            "--domain-pcs",
            "25",
            "--domain-neighbors",
            "15",
            "--domain-resolution",
            "0.5",
            "--coordinate-weight",
            "2.0",
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
            "public SeqFISH spatial execution failed:\n"
            + completed.stdout[-2000:]
            + "\n"
            + completed.stderr[-5000:]
        )


def verify(source: Path | None, scientific_python: Path) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    if not python.is_file() or not os.access(python, os.X_OK):
        raise RuntimeError("spatial scientific Python must be executable")
    with tempfile.TemporaryDirectory(
        prefix="biomed-public-seqfish-spatial-"
    ) as temporary:
        work = Path(temporary)
        source_path = acquire_source(work, source)
        source_digest_before = sha256(source_path)
        adata = ad.read_h5ad(source_path)
        values = adata.X.data if sparse.issparse(adata.X) else np.asarray(adata.X)
        coordinates = np.asarray(adata.obsm["spatial"], dtype=float)
        if (
            adata.shape != (19416, 351)
            or values.size == 0
            or not np.allclose(values, np.rint(values))
            or coordinates.shape != (adata.n_obs, 2)
            or "celltype_mapped_refined" not in adata.obs
        ):
            raise RuntimeError("public SeqFISH source differs from contract")

        center = np.median(coordinates, axis=0)
        scale = np.std(coordinates, axis=0)
        distance = np.square((coordinates - center) / scale).sum(axis=1)
        stable = np.asarray(
            [
                int(hashlib.sha256(f"{SEED}:{name}".encode()).hexdigest()[:16], 16)
                for name in adata.obs_names
            ],
            dtype=np.uint64,
        )
        selected = np.lexsort((stable, distance))[:N_CELLS]
        selected = np.sort(selected)
        subset = adata[selected].copy()
        subset.obs["biological_sample"] = "embryo1"
        labels = subset.obs["celltype_mapped_refined"].astype(str)
        support = labels.value_counts()
        subset.obs["reviewed_cell_type"] = labels.where(
            labels.map(support) >= 20,
            "Other",
        )
        detected = np.asarray((subset.X > 0).sum(axis=0)).ravel()
        totals = np.asarray(subset.X.sum(axis=0)).ravel()
        ranked = np.lexsort(
            (np.arange(subset.n_vars), -totals, -detected)
        )
        moran_genes = subset.var_names[ranked[:N_MORAN_GENES]].tolist()
        input_path = work / "seqfish-subset.h5ad"
        subset.write_h5ad(input_path, compression="gzip")

        environment = dict(os.environ)
        environment.update(
            {
                "PATH": str(python.parent)
                + os.pathsep
                + os.environ.get("PATH", ""),
                "PYTHONHASHSEED": "0",
                "LANG": "C",
                "LC_ALL": "C",
            }
        )
        run_template(python, input_path, moran_genes, work, environment)
        template_report = json.loads(
            (work / "template-report.json").read_text(encoding="utf-8")
        )
        source_digest_after = sha256(source_path)
        checks = template_report["scientific_checks"]
        quality_gates = {
            "official_source_identity": "pass"
            if source_digest_before == source_digest_after == SOURCE["sha256"]
            else "fail",
            "label_blind_spatially_coherent_selection": "pass",
            "integer_counts_coordinates_and_labels_preserved": "pass"
            if checks["raw_counts_cells_genes_and_coordinates_preserved"]
            else "fail",
            "spatial_statistics_domains_and_reload": "pass"
            if checks["outputs_reloaded"]
            and checks["moran_permutation_test_executed"]
            and checks["joint_expression_spatial_domains_executed"]
            and template_report["results"]["domains"] >= 2
            else "fail",
            "single_sample_boundary": "pass"
            if checks["single_sample_inference_boundary_applied"]
            and not checks["spatial_gene_sample_replication_required"]
            and template_report["input"]["samples"] == 1
            else "fail",
        }
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        report = {
            "schema_version": 1,
            "case_id": "seqfish-embryo-spatial-v1",
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
                **SOURCE,
                "validation": {
                    "source_observations": adata.n_obs,
                    "source_genes": adata.n_vars,
                    "selected_observations": subset.n_obs,
                    "selected_genes": subset.n_vars,
                    "reviewed_cell_types": subset.obs[
                        "reviewed_cell_type"
                    ].nunique(),
                    "selection": (
                        "nearest observations to the source-coordinate median "
                        "with stable-hash tie breaking and no cell-type labels"
                    ),
                },
            },
            "parameters": template_report["parameters"],
            "runtime": template_report["versions"],
            "execution": {
                **template_report["results"],
                "source_artifact_immutable": source_digest_before
                == source_digest_after,
                "outputs_reloaded": checks["outputs_reloaded"],
            },
            "quality_gates": quality_gates,
            "scientific_boundaries": [
                "The public source contains one embryo, so this case validates spatial methods and within-embryo structure rather than biological replication or condition inference.",
                "The spatially coherent subset and Moran candidate genes are selected without reviewed cell-type labels.",
                "A minimum supporting-sample value of one is explicit; admitted genes are single-embryo spatial candidates, not replicated spatial genes.",
                "Neighborhood enrichment, co-occurrence, Moran statistics, and exploratory domains do not establish lineage, interaction, or causal regulation.",
            ],
        }
        if not report["passed"]:
            raise RuntimeError(
                "public SeqFISH spatial gates failed: "
                + json.dumps(quality_gates, sort_keys=True)
            )
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "public-case-seqfish-spatial.json",
    )
    args = parser.parse_args()
    report = verify(args.source, args.scientific_python)
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
                "domains": report["execution"]["domains"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
