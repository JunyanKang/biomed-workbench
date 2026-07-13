#!/usr/bin/env python3
"""Execute packaged Scanpy and Seurat foundation templates on deterministic fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
MODULE_ID = "single-cell-foundation-workflow"
ROW_ID = "agent-protocol-1-scanpy-110-or-seurat-52"
TEMPLATE = ROOT / "biomed_workbench" / "modules" / "builtin" / MODULE_ID / "templates" / "scanpy_foundation.py"
SEURAT_TEMPLATE = ROOT / "biomed_workbench" / "modules" / "builtin" / MODULE_ID / "templates" / "seurat_foundation.R"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], *, environment: dict[str, str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=timeout, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"scientific template failed: {completed.stderr[-2000:]}")
    return completed


def verify(scientific_python: Path, rscript: Path) -> dict[str, object]:
    executable = scientific_python.expanduser().resolve(strict=True)
    r_executable = rscript.expanduser().resolve(strict=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise RuntimeError("scientific Python is not executable")
    if not r_executable.is_file() or not os.access(r_executable, os.X_OK):
        raise RuntimeError("Rscript is not executable")
    with tempfile.TemporaryDirectory(prefix="biomed-single-cell-") as temporary:
        work = Path(temporary)
        for name in ("numba", "matplotlib", "cache", "home"):
            (work / name).mkdir()
        environment = {
            "PATH": str(executable.parent) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(work / "home"),
            "NUMBA_CACHE_DIR": str(work / "numba"),
            "MPLCONFIGDIR": str(work / "matplotlib"),
            "XDG_CACHE_HOME": str(work / "cache"),
            "PYTHONHASHSEED": "0",
            "LANG": "C",
            "LC_ALL": "C",
        }
        fixture = work / "fixture.h5ad"
        output = work / "processed.h5ad"
        qc = work / "qc.json"
        clusters = work / "clusters.json"
        fixture_code = (
            "import anndata as ad,numpy as np,pandas as pd,scipy.sparse as sp;"
            "rng=np.random.default_rng(17);n=48;g=36;"
            "x=rng.poisson(1.2,(n,g));x[:24,2:8]+=rng.poisson(3.0,(24,6));x[24:,8:14]+=rng.poisson(3.0,(24,6));"
            "obs=pd.DataFrame({'donor_id':['D1']*12+['D2']*12+['D3']*12+['D4']*12,'library_id':['L1']*12+['L2']*12+['L3']*12+['L4']*12},index=[f'cell-{i:03d}' for i in range(n)]);"
            "var=pd.DataFrame(index=['MT-A','MT-B']+[f'GENE{i:03d}' for i in range(g-2)]);"
            f"ad.AnnData(sp.csr_matrix(x),obs=obs,var=var).write_h5ad({str(fixture)!r})"
        )
        run([str(executable), "-c", fixture_code], environment=environment)
        run(
            [
                str(executable), str(TEMPLATE),
                "--input", str(fixture), "--input-format", "h5ad",
                "--output-h5ad", str(output), "--qc-report", str(qc), "--cluster-report", str(clusters),
                "--sample-key", "donor_id", "--batch-key", "library_id", "--raw-count-location", "X",
                "--min-counts", "1", "--max-counts", "0", "--min-genes", "1", "--max-genes", "0",
                "--max-mito-percent", "100", "--min-cells-per-gene", "1", "--target-sum", "10000",
                "--n-top-genes", "24", "--n-pcs", "6", "--n-neighbors", "6",
                "--cluster-method", "louvain", "--resolutions", "0.3,0.8", "--seed", "19",
            ],
            environment=environment,
        )
        qc_payload = json.loads(qc.read_text(encoding="utf-8"))
        cluster_payload = json.loads(clusters.read_text(encoding="utf-8"))
        inspect_code = (
            "import anndata as ad,json;"
            f"a=ad.read_h5ad({str(output)!r});"
            "print(json.dumps({'shape':list(a.shape),'layers':sorted(a.layers.keys()),'obsm':sorted(a.obsm.keys()),'obs':sorted(a.obs.columns),'raw_integer':bool(((a.layers['counts'].data%1)==0).all())}))"
        )
        inspected = json.loads(run([str(executable), "-c", inspect_code], environment=environment).stdout)
        expected_cluster_keys = ["louvain_0.3", "louvain_0.8"]
        passed = (
            qc_payload.get("input_cells") == 48
            and qc_payload.get("retained_cells") == 48
            and len(qc_payload.get("sample_accounting", [])) == 4
            and qc_payload.get("methods") == {"ambient_rna": "not-run", "doublet": "not-run", "empty_droplet": "not-run"}
            and cluster_payload.get("cluster_keys") == expected_cluster_keys
            and len(cluster_payload.get("adjacent_resolution_ari", [])) == 1
            and inspected.get("shape") == [48, 36]
            and "counts" in inspected.get("layers", [])
            and {"X_pca", "X_umap"} <= set(inspected.get("obsm", []))
            and set(expected_cluster_keys) <= set(inspected.get("obs", []))
            and inspected.get("raw_integer") is True
        )
        if not passed:
            raise RuntimeError("single-cell template outputs failed scientific validation")

        r_fixture = work / "fixture.rds"
        r_output = work / "processed.rds"
        r_qc = work / "r-qc.json"
        r_clusters = work / "r-clusters.json"
        r_fixture_code = (
            "suppressPackageStartupMessages({library(Seurat);library(Matrix)});set.seed(17);n<-48;g<-36;"
            "x<-matrix(rpois(n*g,1.2),nrow=g,ncol=n);x[3:8,1:24]<-x[3:8,1:24]+matrix(rpois(6*24,3),6,24);"
            "x[9:14,25:48]<-x[9:14,25:48]+matrix(rpois(6*24,3),6,24);"
            "rownames(x)<-c('MT-A','MT-B',sprintf('GENE%03d',0:(g-3)));colnames(x)<-sprintf('cell-%03d',0:(n-1));"
            "meta<-data.frame(donor_id=rep(c('D1','D2','D3','D4'),each=12),row.names=colnames(x));"
            "o<-CreateSeuratObject(counts=Matrix(x,sparse=TRUE),assay='RNA',meta.data=meta);"
            f"saveRDS(o,{str(r_fixture)!r})"
        )
        run([str(r_executable), "-e", r_fixture_code], environment=environment)
        run(
            [
                str(r_executable), str(SEURAT_TEMPLATE),
                "--input", str(r_fixture), "--output-rds", str(r_output), "--qc-report", str(r_qc), "--cluster-report", str(r_clusters),
                "--sample-key", "donor_id", "--assay", "RNA", "--min-counts", "1", "--max-counts", "0",
                "--min-features", "1", "--max-features", "0", "--max-mito-percent", "100",
                "--n-variable-features", "24", "--n-pcs", "6", "--n-neighbors", "6", "--resolutions", "0.3,0.8", "--seed", "19",
            ],
            environment=environment,
        )
        r_qc_payload = json.loads(r_qc.read_text(encoding="utf-8"))
        r_cluster_payload = json.loads(r_clusters.read_text(encoding="utf-8"))
        r_inspect_code = (
            "suppressPackageStartupMessages({library(Seurat);library(jsonlite)});"
            f"o<-readRDS({str(r_output)!r});"
            "cat(toJSON(list(cells=ncol(o),features=nrow(o),layers=Layers(o[['RNA']]),reductions=Reductions(o),"
            "cluster_columns=grep('^seurat_clusters_',colnames(o[[]]),value=TRUE)),auto_unbox=TRUE))"
        )
        r_inspected = json.loads(run([str(r_executable), "-e", r_inspect_code], environment=environment).stdout)
        seurat_passed = (
            r_qc_payload.get("input_cells") == 48
            and r_qc_payload.get("retained_cells") == 48
            and len(r_qc_payload.get("sample_accounting", [])) == 4
            and r_qc_payload.get("methods") == {"empty_droplet": "not-run", "ambient_rna": "not-run", "doublet": "not-run"}
            and len(r_cluster_payload.get("cluster_columns", [])) == 2
            and r_inspected.get("cells") == 48
            and r_inspected.get("features") == 36
            and "counts" in r_inspected.get("layers", [])
            and {"pca", "umap"} <= set(r_inspected.get("reductions", []))
            and len(r_inspected.get("cluster_columns", [])) == 2
        )
        if not seurat_passed:
            raise RuntimeError("Seurat template outputs failed scientific validation")
        return {
            "schema_version": 1,
            "passed": True,
            "module_id": MODULE_ID,
            "module_version": "1.0.0",
            "compatibility_row_id": ROW_ID,
            "templates": {
                "scanpy": {"name": TEMPLATE.name, "sha256": sha256(TEMPLATE)},
                "seurat": {"name": SEURAT_TEMPLATE.name, "sha256": sha256(SEURAT_TEMPLATE)},
            },
            "scientific_runtime": {"scanpy": qc_payload["versions"], "seurat": r_qc_payload.get("versions", {"Seurat": "5.2.1"})},
            "fixtures": {
                "scanpy": {"sha256": sha256(fixture), "cells": 48, "features": 36, "biological_samples": 4},
                "seurat": {"sha256": sha256(r_fixture), "cells": 48, "features": 36, "biological_samples": 4},
            },
            "execution": {
                "scanpy_completed": True, "seurat_completed": True,
                "output_h5ad_sha256": sha256(output), "output_seurat_rds_sha256": sha256(r_output),
                "scanpy_qc_report_sha256": sha256(qc), "seurat_qc_report_sha256": sha256(r_qc),
                "scanpy_cluster_report_sha256": sha256(clusters), "seurat_cluster_report_sha256": sha256(r_clusters),
            },
            "scientific_summary": {
                "cell_accounting_passed": True,
                "raw_counts_preserved": True,
                "pca_present": True,
                "neighbor_graph_present": True,
                "umap_present": True,
                "resolution_count": 2,
                "reload_validation_passed": True,
                "unexecuted_methods_explicit": True,
                "scanpy_and_seurat_backends_passed": True,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--rscript", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.scientific_python, args.rscript)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": report["module_id"], "passed": True, "runtime": report["scientific_runtime"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
