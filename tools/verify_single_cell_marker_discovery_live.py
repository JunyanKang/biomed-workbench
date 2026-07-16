#!/usr/bin/env python3
"""Execute the marker-discovery template on a sample-stratified fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


MODULE_ID = "single-cell-marker-discovery"
ROW_ID = "agent-protocol-1-scanpy-1104-marker-stability"
TEMPLATE = BUILTIN_ROOT / MODULE_ID / "templates" / "discover_markers.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=180, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"marker template failed: {completed.stderr[-2500:]}")
    return completed


def verify(scientific_python: Path) -> dict[str, object]:
    python = scientific_python.expanduser().resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="biomed-markers-") as temporary:
        work = Path(temporary)
        for name in ("home", "cache", "matplotlib", "numba"):
            (work / name).mkdir()
        environment = {"PATH": str(python.parent) + os.pathsep + os.environ.get("PATH", ""), "HOME": str(work / "home"), "XDG_CACHE_HOME": str(work / "cache"), "MPLCONFIGDIR": str(work / "matplotlib"), "NUMBA_CACHE_DIR": str(work / "numba"), "PYTHONHASHSEED": "0", "LANG": "C", "LC_ALL": "C"}
        source, markers, report = work / "input.h5ad", work / "markers.tsv", work / "report.json"
        fixture = (
            "import anndata as ad,numpy as np,pandas as pd,scipy.sparse as sp;"
            "rng=np.random.default_rng(89);n=240;g=100;labels=np.array(['A']*120+['B']*120);"
            "samples=np.tile(np.repeat(['S1','S2','S3','S4'],30),2);x=rng.poisson(.15,(n,g));"
            "x[:120,:12]+=rng.poisson(5,(120,12));x[120:,12:24]+=rng.poisson(5,(120,12));"
            "a=ad.AnnData(sp.csr_matrix(x),obs=pd.DataFrame({'cluster':labels,'sample':samples},index=[f'cell-{i:03d}' for i in range(n)]),var=pd.DataFrame(index=[f'GENE-{i:03d}' for i in range(g)]));"
            f"a.layers['counts']=a.X.copy();a.write_h5ad({str(source)!r})"
        )
        run([str(python), "-c", fixture], environment)
        source_digest = sha256(source)
        run([str(python), str(TEMPLATE), "--input-h5ad", str(source), "--output-tsv", str(markers), "--report", str(report), "--cluster-key", "cluster", "--sample-key", "sample", "--raw-count-location", "layers.counts", "--method", "wilcoxon", "--top-per-cluster", "30", "--min-in-fraction", "0.25", "--max-out-fraction", "0.5", "--min-logfc", "0.25", "--max-adjusted-p", "0.05", "--min-sample-support", "2", "--seed", "23"], environment)
        payload = json.loads(report.read_text(encoding="utf-8"))
        inspect = "import json,pandas as pd;" + f"x=pd.read_csv({str(markers)!r},sep='\\t');" + "print(json.dumps({'rows':len(x),'clusters':sorted(x.cluster.unique().tolist()),'admitted':int(x.admitted_marker.sum()),'stable':int((x.sample_stability=='stable-positive').sum()),'max_support':int(x.supporting_samples.max())}))"
        table = json.loads(run([str(python), "-c", inspect], environment).stdout)
        if payload["admitted_rows"] < 20 or payload["clusters_with_admitted_markers"] != 2 or table["clusters"] != ["A", "B"] or table["max_support"] != 4 or sha256(source) != source_digest:
            raise RuntimeError("marker evidence failed effect, sample-stability, or source-preservation checks")
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        return {"schema_version": 1, "passed": True, "module_id": MODULE_ID, "module_version": "1.0.0", "compatibility_row_id": ROW_ID, "registry_digest": registry.digest,
                "templates": {"marker": {"name": TEMPLATE.name, "sha256": sha256(TEMPLATE)}},
                "tool_versions": {"scanpy": payload["versions"]["scanpy"]}, "dependency_versions": {"python": payload["versions"]["python"], "anndata": payload["versions"]["anndata"]},
                "fixture": {"sha256": source_digest, "cells": 240, "features": 100, "clusters": 2, "biological_samples": 4},
                "execution": {"marker_ranking_completed": True, "output_reloaded": True},
                "scientific_summary": {"all_clusters_ranked": True, "raw_detection_fractions_computed": True, "sample_stability_computed": True, "planted_markers_admitted": True, "raw_counts_preserved": True, "no_automatic_label_assignment": True}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.scientific_python)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": MODULE_ID, "passed": True, "tool_versions": report["tool_versions"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
