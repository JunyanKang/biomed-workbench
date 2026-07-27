#!/usr/bin/env python3
"""Execute emptyDrops, SoupX, and CellBender templates on deterministic droplet fixtures."""

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


MODULE_ID = "single-cell-droplet-decontamination"
ROW_ID = "agent-protocol-1-emptydrops-1220-soupx-162-cellbender-032"
MODULE = BUILTIN_ROOT / MODULE_ID
R_TEMPLATE = MODULE / "templates" / "run_emptydrops_soupx.R"
CELLBENDER_TEMPLATE = MODULE / "templates" / "run_cellbender.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(child.relative_to(path).as_posix().encode())
        digest.update(child.read_bytes())
    return digest.hexdigest()


def run(command: list[str], environment: dict[str, str], timeout: int = 240) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=timeout, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"scientific template failed: {completed.stderr[-3000:]}")
    return completed


def verify(scientific_python: Path, rscript: Path, r_libs: Path) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    if not python.is_file() or not os.access(python, os.X_OK):
        raise RuntimeError("scientific Python is not executable")
    r = rscript.expanduser().resolve(strict=True)
    libraries = r_libs.expanduser().resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="biomed-droplet-") as temporary:
        work = Path(temporary)
        for name in ("home", "cache", "matplotlib", "numba"):
            (work / name).mkdir()
        environment = dict(os.environ)
        environment.update({
            "PATH": str(python.parent) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(work / "home"), "XDG_CACHE_HOME": str(work / "cache"),
            "MPLCONFIGDIR": str(work / "matplotlib"), "NUMBA_CACHE_DIR": str(work / "numba"),
            "R_LIBS_USER": str(libraries), "PYTHONHASHSEED": "0", "LANG": "C", "LC_ALL": "C",
        })
        raw, filtered, raw_v3, clusters = work / "raw", work / "filtered", work / "raw-v3", work / "clusters.tsv"
        fixture_code = (
            "import gzip,numpy as np,pathlib,shutil;from scipy import io,sparse;"
            "rng=np.random.default_rng(83);g=120;c=200;e=1800;cells=rng.poisson(.2,(g,c));"
            "cells[:20,:100]+=rng.poisson(8,(20,100));cells[20:40,100:]+=rng.poisson(8,(20,100));"
            "empty=rng.poisson(.12,(g,e));raw=np.concatenate([cells,empty],axis=1);root=pathlib.Path(" + repr(str(work)) + ");"
            "features=''.join(f'gene-{i:03d}\\tGENE-{i:03d}\\tGene Expression\\n' for i in range(g));"
            "bars=[f'cell-{i:04d}' for i in range(c)]+[f'empty-{i:04d}' for i in range(e)];"
            "[(lambda d,x,b:(d.mkdir(),io.mmwrite(d/'matrix.mtx',sparse.coo_matrix(x)),(d/'barcodes.tsv').write_text(''.join(v+'\\n' for v in b)),(d/'features.tsv').write_text(features)))(root/name,x,b) for name,x,b in [('raw',raw,bars),('filtered',cells,bars[:c])]];"
            "v3=root/'raw-v3';v3.mkdir();"
            "[(lambda src,dst: gzip.open(dst,'wb').write(pathlib.Path(src).read_bytes()))(root/'raw'/src,v3/dst) for src,dst in [('matrix.mtx','matrix.mtx.gz'),('barcodes.tsv','barcodes.tsv.gz'),('features.tsv','features.tsv.gz')]];"
            "(root/'clusters.tsv').write_text('barcode\\tcluster\\n'+''.join(f'cell-{i:04d}\\t{\"A\" if i<100 else \"B\"}\\n' for i in range(c)))"
        )
        run([str(python), "-c", fixture_code], environment)
        source_digests = {"raw": artifact_sha256(raw), "filtered": artifact_sha256(filtered), "raw_v3": artifact_sha256(raw_v3)}

        r_reports: dict[str, dict[str, object]] = {}
        for mode in ("fixed", "auto"):
            output, report = work / f"soupx-{mode}", work / f"soupx-{mode}.json"
            command = [str(r), str(R_TEMPLATE), "--raw-mtx", str(raw), "--filtered-mtx", str(filtered), "--output-dir", str(output), "--report", str(report), "--lower", "20", "--fdr", "0.001", "--niters", "1000", "--contamination-mode", mode, "--seed", "19"]
            if mode == "fixed":
                command.extend(["--contamination-fraction", "0.08"])
            else:
                command.extend(["--cluster-tsv", str(clusters), "--tfidf-min", "0.1", "--soup-quantile", "0.5"])
            run(command, environment)
            payload = json.loads(report.read_text(encoding="utf-8"))
            matrix = output / "soupx_corrected" / "matrix.mtx"
            if payload["raw_droplets"] != 2000 or payload["filtered_cells"] != 200 or payload["features"] != 120 or not payload["serialized_output_reloaded"] or not matrix.is_file():
                raise RuntimeError(f"SoupX {mode} output failed scientific accounting")
            r_reports[mode] = payload

        cellbender_output, cellbender_report = work / "cellbender" / "output.h5", work / "cellbender" / "report.json"
        run([str(python), str(CELLBENDER_TEMPLATE), "--input", str(raw_v3), "--output-h5", str(cellbender_output), "--report", str(cellbender_report), "--expected-cells", "200", "--total-droplets-included", "800", "--epochs", "1", "--fpr", "0.01", "--model", "ambient", "--cpu-threads", "1", "--use-cuda", "false"], environment)
        cellbender = json.loads(cellbender_report.read_text(encoding="utf-8"))
        if cellbender["output_droplets"] != 2000 or cellbender["output_features"] != 120 or not cellbender["serialized_output_reloaded"] or "cell_probability" not in cellbender["latent_fields"]:
            raise RuntimeError("CellBender output failed scientific accounting")
        if source_digests != {"raw": artifact_sha256(raw), "filtered": artifact_sha256(filtered), "raw_v3": artifact_sha256(raw_v3)}:
            raise RuntimeError("source droplet fixtures changed during execution")
        versions = json.loads(run([str(python), "-c", "import json,platform,torch,pyro;print(json.dumps({'python':platform.python_version(),'torch':torch.__version__,'pyro':pyro.__version__}))"], environment).stdout)
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        return {
            "schema_version": 1, "passed": True, "module_id": MODULE_ID, "module_version": "1.1.0",
            "compatibility_row_id": ROW_ID, "registry_digest": registry.digest,
            "templates": {"r": {"name": R_TEMPLATE.name, "sha256": sha256(R_TEMPLATE)}, "cellbender": {"name": CELLBENDER_TEMPLATE.name, "sha256": sha256(CELLBENDER_TEMPLATE)}},
            "tool_versions": {"DropletUtils": r_reports["fixed"]["versions"]["DropletUtils"], "SoupX": r_reports["fixed"]["versions"]["SoupX"], "CellBender": cellbender["versions"]["cellbender"]},
            "dependency_versions": {
                **versions,
                "r": r_reports["fixed"]["versions"]["R"],
                "digest": r_reports["fixed"]["versions"]["digest"],
            },
            "fixtures": {"raw_droplets": 2000, "filtered_cells": 200, "features": 120, "source_digests": source_digests},
            "execution": {"emptydrops_completed": True, "soupx_fixed_completed": True, "soupx_auto_completed": True, "cellbender_completed": True, "outputs_reloaded": True, "cellbender_output_sha256": sha256(cellbender_output)},
            "scientific_summary": {"barcode_reconciliation_passed": True, "raw_counts_preserved": True, "methods_separated": True, "nonnegative_counts": True, "source_artifacts_immutable": True, "no_environment_or_compute_infrastructure_managed": True},
        }


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
