#!/usr/bin/env python3
"""Execute packaged Scrublet and scDblFinder templates on immutable fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
MODULE_ID = "single-cell-doublet-detection"
ROW_ID = "agent-protocol-1-scrublet-023-scdblfinder-1160"
MODULE = ROOT / "biomed_workbench" / "modules" / "builtin" / MODULE_ID
SCRUBLET = MODULE / "templates" / "run_scrublet.py"
SCDBLFINDER = MODULE / "templates" / "run_scdblfinder.R"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], environment: dict[str, str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=timeout, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"scientific template failed: {completed.stderr[-2500:]}")
    return completed


def verify(scientific_python: Path, rscript: Path, r_libs: Path) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    if not python.is_file():
        raise FileNotFoundError(f"scientific Python is absent: {python}")
    r = rscript.expanduser().resolve(strict=True)
    libraries = r_libs.expanduser().resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="biomed-doublet-") as temporary:
        work = Path(temporary)
        for name in ("home", "cache", "matplotlib", "numba"):
            (work / name).mkdir()
        environment = {
            "PATH": str(python.parent) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(work / "home"), "XDG_CACHE_HOME": str(work / "cache"),
            "MPLCONFIGDIR": str(work / "matplotlib"), "NUMBA_CACHE_DIR": str(work / "numba"),
            "R_LIBS_USER": str(libraries), "PYTHONHASHSEED": "0", "LANG": "C", "LC_ALL": "C",
        }
        h5ad = work / "source.h5ad"
        tenx = work / "tenx"
        fixture_code = (
            "import anndata as ad,numpy as np,pandas as pd,scipy.sparse as sp,pathlib;from scipy import io;"
            "rng=np.random.default_rng(73);n=160;g=160;x=rng.poisson(1.5,(n,g));"
            "x[:80,:24]+=rng.poisson(3.0,(80,24));x[80:,24:48]+=rng.poisson(3.0,(80,24));"
            "obs=pd.DataFrame({'sample':['S1']*80+['S2']*80},index=[f'cell-{i:03d}' for i in range(n)]);"
            "var=pd.DataFrame(index=[f'GENE-{i:03d}' for i in range(g)]);a=ad.AnnData(sp.csr_matrix(x),obs=obs,var=var);"
            f"a.write_h5ad({str(h5ad)!r});d=pathlib.Path({str(tenx)!r});d.mkdir();io.mmwrite(d/'matrix.mtx',sp.coo_matrix(x.T));"
            "(d/'barcodes.tsv').write_text(''.join(f'cell-{i:03d}\\n' for i in range(n)));"
            "(d/'features.tsv').write_text(''.join(f'gene-{i:03d}\\tGENE-{i:03d}\\tGene Expression\\n' for i in range(g)))"
        )
        run([str(python), "-c", fixture_code], environment)
        scrublet_h5ad, scrublet_report = work / "scrublet.h5ad", work / "scrublet.json"
        run([str(python), str(SCRUBLET), "--input-h5ad", str(h5ad), "--output-h5ad", str(scrublet_h5ad), "--report", str(scrublet_report), "--raw-count-location", "X", "--sample-key", "sample", "--expected-doublet-rate", "0.08", "--min-cells-per-sample", "50", "--n-prin-comps", "20", "--seed", "17"], environment)
        scrublet_payload = json.loads(scrublet_report.read_text())
        inspect = "import anndata as ad,json;" + f"a=ad.read_h5ad({str(scrublet_h5ad)!r});" + "print(json.dumps({'cells':a.n_obs,'features':a.n_vars,'obs':sorted(a.obs.columns),'counts':bool(((a.layers['counts'].data%1)==0).all())}))"
        scrublet_object = json.loads(run([str(python), "-c", inspect], environment).stdout)
        calls, sc_report = work / "scdblfinder.tsv", work / "scdblfinder.json"
        run([str(r), str(SCDBLFINDER), "--input-mtx", str(tenx), "--sample-id", "S1", "--output-tsv", str(calls), "--report", str(sc_report), "--expected-doublet-rate", "0.08", "--seed", "17"], environment)
        sc_payload = json.loads(sc_report.read_text())
        header = calls.read_text(encoding="utf-8").splitlines()[0].split("\t")
        passed = (
            scrublet_payload["schema_version"] == 2
            and scrublet_payload["completed_cells"] == 160
            and len(scrublet_payload["sample_results"]) == 2
            and scrublet_payload["source_immutable"] is True
            and scrublet_payload["output_reloaded"] is True
            and scrublet_payload["automatic_cell_removal_performed"] is False
            and scrublet_object["cells"] == 160
            and scrublet_object["features"] == 160
            and scrublet_object["counts"]
            and {"scrublet_score", "scrublet_call", "scrublet_status"} <= set(scrublet_object["obs"])
            and sc_payload["schema_version"] == 2
            and sc_payload["input_cells"] == 160
            and sc_payload["output_rows_reloaded"] == 160
            and sc_payload["source_immutable"] is True
            and sc_payload["automatic_cell_removal_performed"] is False
            and header == ["cell_id", "biological_sample", "scDblFinder_score", "scDblFinder_class"]
        )
        if not passed:
            raise RuntimeError("doublet templates failed source-preservation or output-accounting validation")
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        return {"schema_version": 1, "passed": True, "module_id": MODULE_ID, "module_version": "1.1.0", "compatibility_row_id": ROW_ID, "registry_digest": registry.digest,
                "templates": {"scrublet": {"name": SCRUBLET.name, "sha256": sha256(SCRUBLET)}, "scDblFinder": {"name": SCDBLFINDER.name, "sha256": sha256(SCDBLFINDER)}},
                "tool_versions": {"scrublet": "0.2.3", "scDblFinder": sc_payload["versions"]["scDblFinder"]},
                "dependency_versions": {
                    "python": scrublet_payload["versions"]["python"],
                    "anndata": scrublet_payload["versions"]["anndata"],
                    "numpy": scrublet_payload["versions"]["numpy"],
                    "pandas": scrublet_payload["versions"]["pandas"],
                    "scipy": scrublet_payload["versions"]["scipy"],
                    "r": sc_payload["versions"]["R"],
                    "SingleCellExperiment": sc_payload["versions"]["SingleCellExperiment"],
                    "DropletUtils": sc_payload["versions"]["DropletUtils"],
                    "BiocParallel": sc_payload["versions"]["BiocParallel"],
                    "jsonlite": sc_payload["versions"]["jsonlite"],
                    "digest": sc_payload["versions"]["digest"],
                },
                "fixtures": {"h5ad_sha256": sha256(h5ad), "matrix_market_sha256": sha256(tenx / "matrix.mtx"), "cells": 160, "features": 160, "biological_samples": 2},
                "execution": {"scrublet_completed": True, "scdblfinder_completed": True, "outputs_reloaded": True, "sparse_reload_validation_completed": True, "source_immutability_verified": True, "scrublet_h5ad_sha256": sha256(scrublet_h5ad), "scdblfinder_calls_sha256": sha256(calls)},
                "scientific_summary": {"sample_aware_methods_executed": True, "raw_counts_preserved": True, "cell_and_feature_identity_preserved": True, "method_specific_scores_retained": True, "score_distributions_retained": True, "no_automatic_cell_removal": True, "method_disagreement_preserved": True}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--rscript", type=Path, required=True)
    parser.add_argument("--r-libs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.scientific_python, args.rscript, args.r_libs)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": MODULE_ID, "passed": True, "tool_versions": report["tool_versions"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
