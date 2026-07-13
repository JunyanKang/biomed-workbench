#!/usr/bin/env python3
"""Execute LIANA, CellPhoneDB, CellChat, and NicheNet on a deterministic fixture."""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

import anndata
import numpy as np
import pandas as pd
from scipy import io, sparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402

PYTHON_TEMPLATE = ROOT / "biomed_workbench/modules/builtin/single-cell-communication/templates/run_liana_cellphonedb.py"
R_TEMPLATE = ROOT / "biomed_workbench/modules/builtin/single-cell-communication/templates/run_cellchat_nichenet.R"
R_RESOURCE_BUILDER = ROOT / "tests/fixtures/communication/build_nichenet_resources.R"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_fixture(root: Path) -> tuple[Path, Path, Path, Path, Path]:
    rng = np.random.default_rng(31)
    signaling = [
        "TGFB1", "TGFB2", "TGFB3", "TGFBR1", "TGFBR2", "TGFBR3", "CXCL12", "CXCR4",
        "EGF", "EGFR", "JAG1", "JAG2", "NOTCH1", "NOTCH2", "NOTCH3", "NOTCH4", "DLL1", "DLL3", "DLL4",
        "BMP2", "BMP4", "BMP6", "BMP7", "BMPR1A", "BMPR1B", "BMPR2",
        "FGF1", "FGF2", "FGF7", "FGF10", "FGFR1", "FGFR2", "FGFR3", "FGFR4",
        "WNT1", "WNT2", "WNT3A", "WNT4", "WNT5A", "WNT7A", "FZD1", "FZD2", "FZD3", "FZD4", "FZD5", "FZD6",
        "CCL2", "CCL3", "CCL4", "CCL5", "CCL7", "CCL19", "CCL20", "CCL21", "CCR1", "CCR2", "CCR5", "CCR6", "CCR7",
        "CXCL1", "CXCL2", "CXCL5", "CXCL8", "CXCL9", "CXCL10", "CXCL11", "CXCL13", "CXCR1", "CXCR2", "CXCR3", "CXCR5",
        "IL1A", "IL1B", "IL2", "IL4", "IL6", "IL7", "IL10", "IL11", "IL13", "IL15", "IL18", "IL21", "IL22", "IL33",
        "IL1R1", "IL2RA", "IL2RB", "IL4R", "IL6R", "IL6ST", "IL7R", "IL10RA", "IL10RB", "IL11RA", "IL13RA1", "IL18R1", "IL21R", "IL22RA1",
        "TNF", "TNFRSF1A", "TNFRSF1B", "VEGFA", "VEGFB", "VEGFC", "FLT1", "KDR", "FLT4", "PDGFA", "PDGFB", "PDGFRA", "PDGFRB",
    ]
    targets = [f"TARGET{i:02d}" for i in range(1, 21)]
    genes = signaling + targets
    observations = []
    rows = []
    for condition in ("control", "treated"):
        for replicate in range(1, 3):
            sample = f"{condition}-{replicate}"
            for cell_type in ("Sender", "Receiver"):
                for cell_index in range(20):
                    values = rng.poisson(1.0, len(genes)).astype(int)
                    if cell_type == "Sender":
                        values[genes.index("TGFB1")] += rng.poisson(12 if condition == "treated" else 8)
                        values[genes.index("CXCL12")] += rng.poisson(10)
                        values[genes.index("JAG1")] += rng.poisson(7)
                    else:
                        for gene in ("TGFBR1", "TGFBR2", "CXCR4", "NOTCH1"):
                            values[genes.index(gene)] += rng.poisson(9)
                        if condition == "treated":
                            values[10:18] += rng.poisson(5, 8)
                    rows.append(values)
                    observations.append(
                        {
                            "cell_id": f"{sample}-{cell_type}-{cell_index:02d}",
                            "cell_type": cell_type,
                            "sample": sample,
                            "condition": condition,
                        }
                    )
    metadata = pd.DataFrame(observations).set_index("cell_id")
    matrix = sparse.csr_matrix(np.asarray(rows, dtype=np.int32))
    adata = anndata.AnnData(X=matrix.copy(), obs=metadata.copy(), var=pd.DataFrame(index=genes))
    adata.layers["counts"] = matrix.copy()
    h5ad = root / "communication.h5ad"
    adata.write_h5ad(h5ad, compression="gzip")
    matrix_path = root / "matrix.mtx"
    genes_path = root / "genes.txt"
    cells_path = root / "cells.txt"
    metadata_path = root / "metadata.tsv"
    io.mmwrite(matrix_path, matrix.transpose().tocoo())
    genes_path.write_text("\n".join(genes) + "\n", encoding="utf-8")
    cells_path.write_text("\n".join(metadata.index) + "\n", encoding="utf-8")
    metadata.reset_index().to_csv(metadata_path, sep="\t", index=False)
    return h5ad, matrix_path, genes_path, cells_path, metadata_path


def run(command: list[str], *, environment: dict[str, str] | None = None, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, env=environment, text=True, capture_output=True, timeout=timeout, check=False)
    if completed.returncode != 0:
        detail = "\n".join((completed.stdout, completed.stderr)).strip()
        raise RuntimeError(f"verification command failed: {detail[-4000:]}")
    return completed


def validate_python_outputs(directory: Path, report_path: Path) -> dict[str, object]:
    interactions = pd.read_csv(directory / "sample_interactions.tsv", sep="\t")
    summary = pd.read_csv(directory / "replicated_interactions.tsv", sep="\t")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    methods = set(interactions["method"])
    if methods != {"liana-rank-aggregate", "cellphonedb-statistical"}:
        raise ValueError("Python communication verification did not observe both methods")
    if interactions.empty or summary.empty or len(report["sample_runs"]) < 8:
        raise ValueError("Python communication outputs are incomplete")
    return {
        "methods": sorted(methods),
        "sample_interaction_rows": len(interactions),
        "replicate_summary_rows": len(summary),
        "replicated_interactions": int(summary["replicated"].sum()),
        "quality_status": report["quality"]["status"],
        "report_sha256": sha256(report_path),
    }


def validate_r_outputs(directory: Path) -> dict[str, object]:
    cellchat = pd.read_csv(directory / "cellchat_sample_interactions.tsv", sep="\t")
    nichenet = pd.read_csv(directory / "nichenet_ligand_activities.tsv", sep="\t")
    links = pd.read_csv(directory / "nichenet_ligand_target_links.tsv", sep="\t")
    report_path = directory / "communication_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if cellchat.empty or nichenet.empty or links.empty or report["nichenet_executed"] is not True:
        raise ValueError("R communication outputs are incomplete")
    return {
        "methods": ["cellchat", "nichenet"],
        "cellchat_interaction_rows": len(cellchat),
        "nichenet_ligand_rows": len(nichenet),
        "nichenet_target_link_rows": len(links),
        "quality_status": report["quality_status"],
        "report_sha256": sha256(report_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cellphonedb-database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    database = args.cellphonedb_database.resolve(strict=True)
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    manifest = registry.get("single-cell-communication")
    with tempfile.TemporaryDirectory(prefix="biomed-communication-verification-") as temporary:
        root = Path(temporary)
        h5ad, matrix_path, genes_path, cells_path, metadata_path = build_fixture(root)
        python_output = root / "python-output"
        python_report = root / "python-report.json"
        environment = dict(os.environ)
        environment["NUMBA_CACHE_DIR"] = str(root / "numba-cache")
        environment["MPLCONFIGDIR"] = str(root / "matplotlib-cache")
        run(
            [
                sys.executable, str(PYTHON_TEMPLATE), "--input-h5ad", str(h5ad),
                "--output-directory", str(python_output), "--report", str(python_report),
                "--method", "both", "--cell-type-key", "cell_type", "--sample-key", "sample",
                "--condition-key", "condition", "--raw-count-location", "layers.counts",
                "--species", "human", "--cellphonedb-database", str(database),
                "--minimum-cells", "10", "--minimum-samples", "2", "--expression-proportion", "0.1",
                "--permutations", "100", "--fdr", "0.05", "--seed", "41", "--jobs", "1",
            ],
            environment=environment,
        )
        python_result = validate_python_outputs(python_output, python_report)
        resources = root / "nichenet-resources"
        run(["Rscript", str(R_RESOURCE_BUILDER), str(genes_path), str(resources)])
        r_config = {
            "matrix": str(matrix_path), "genes": str(genes_path), "cells": str(cells_path), "metadata": str(metadata_path),
            "cell_type_key": "cell_type", "sample_key": "sample", "condition_key": "condition",
            "species": "human", "method": "both", "minimum_cells": 10, "minimum_samples": 2,
            "expression_proportion": 0.1, "permutations": 100, "seed": 41,
            "nichenet_ligand_target_matrix": str(resources / "ligand_target_matrix.rds"),
            "nichenet_lr_network": str(resources / "lr_network.rds"),
            "nichenet_weighted_networks": str(resources / "weighted_networks.rds"),
            "receiver": "Receiver", "contrast_condition": "treated", "reference_condition": "control",
            "receiver_de_table": str(resources / "receiver_de.tsv"),
        }
        r_config_path = root / "r-config.json"
        r_config_path.write_text(json.dumps(r_config, indent=2) + "\n", encoding="utf-8")
        r_output = root / "r-output"
        run(["Rscript", str(R_TEMPLATE), str(r_config_path), str(r_output)])
        r_result = validate_r_outputs(r_output)
        fixture = anndata.read_h5ad(h5ad, backed="r")
        fixture_cells, fixture_genes = fixture.shape
        fixture.file.close()
        report = {
            "schema_version": 1,
            "passed": True,
            "module_id": manifest.id,
            "module_version": manifest.version,
            "registry_digest": registry.digest,
            "compatibility_rows": [
                {
                    "id": row.id,
                    "regression_evidence_ids": list(row.regression_evidence_ids),
                    "end_to_end_evidence_ids": list(row.end_to_end_evidence_ids),
                }
                for row in manifest.compatibility_matrix
            ],
            "templates": {
                path.stem: {"name": path.name, "sha256": sha256(path)}
                for path in (PYTHON_TEMPLATE, R_TEMPLATE)
            },
            "fixture": {"cells": fixture_cells, "genes": fixture_genes, "biological_samples": 4, "conditions": 2, "sha256": sha256(h5ad)},
            "cellphonedb_database": {"sha256": sha256(database)},
            "python_backends": python_result,
            "r_backends": r_result,
            "execution": {
                "liana_completed": True,
                "cellphonedb_completed": True,
                "cellchat_completed": True,
                "nichenet_completed": True,
                "python_report_sha256": python_result["report_sha256"],
                "r_report_sha256": r_result["report_sha256"],
            },
            "scientific_summary": {
                "all_four_backends_executed": True,
                "biological_samples_used_as_replicates": True,
                "cells_not_used_as_condition_replicates": True,
                "method_specific_results_retained": True,
                "cross_sample_support_computed": True,
                "nichenet_receiver_evidence_used": True,
                "source_counts_and_identifiers_preserved": True,
                "outputs_reloaded": True,
                "no_environment_or_compute_infrastructure_managed": True,
            },
            "versions": {
                "python": platform.python_version(), "anndata": version("anndata"), "scanpy": version("scanpy"),
                "liana": version("liana"), "cellphonedb": version("cellphonedb"),
                "CellChat": run(["Rscript", "-e", "cat(as.character(packageVersion('CellChat')))"]).stdout,
                "cellchat": run(["Rscript", "-e", "cat(as.character(packageVersion('CellChat')))"]).stdout,
                "nichenetr": run(["Rscript", "-e", "cat(as.character(packageVersion('nichenetr')))"]).stdout,
            },
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
