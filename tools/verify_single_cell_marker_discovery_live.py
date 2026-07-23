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
    python = scientific_python.expanduser().absolute()
    if not python.is_file():
        raise FileNotFoundError(f"scientific Python is absent: {python}")
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
        run([str(python), str(TEMPLATE), "--input-h5ad", str(source), "--output-tsv", str(markers), "--report", str(report), "--cluster-key", "cluster", "--sample-key", "sample", "--raw-count-location", "layers.counts", "--validation-samples", "S4", "--method", "wilcoxon", "--top-per-cluster", "30", "--min-in-fraction", "0.25", "--max-out-fraction", "0.5", "--min-logfc", "0.25", "--max-adjusted-p", "0.05", "--min-sample-support", "3", "--min-validation-sample-support", "1", "--seed", "23"], environment)
        payload = json.loads(report.read_text(encoding="utf-8"))
        inspect = "import json,pandas as pd;" + f"x=pd.read_csv({str(markers)!r},sep='\\t');" + "print(json.dumps({'rows':len(x),'clusters':sorted(x.cluster.unique().tolist()),'admitted':int(x.admitted_marker.sum()),'discovered':int(x.discovery_admitted_marker.sum()),'validated':int(x.independently_validated_marker.sum()),'max_discovery_support':int(x.discovery_supporting_samples.max()),'max_validation_support':int(x.validation_supporting_samples.max()),'scope':sorted(x.inferential_scope.unique().tolist())}))"
        table = json.loads(run([str(python), "-c", inspect], environment).stdout)
        if (
            payload["quality_status"] != "passed"
            or payload["sample_split"]["discovery_samples"] != ["S1", "S2", "S3"]
            or payload["sample_split"]["validation_samples"] != ["S4"]
            or payload["sample_split"]["validation_used_for_ranking_or_threshold_selection"] is not False
            or payload["accounting"]["independently_validated_rows"] < 20
            or payload["accounting"]["clusters_with_independently_validated_markers"] != 2
            or table["clusters"] != ["A", "B"]
            or table["max_discovery_support"] != 3
            or table["max_validation_support"] != 1
            or table["scope"] != ["descriptive-cell-level-ranking-not-donor-level-inference"]
            or sha256(source) != source_digest
        ):
            raise RuntimeError("marker evidence failed split, effect, held-out validation, or source-preservation checks")
        perturbed_source = work / "validation-perturbed.h5ad"
        perturb = (
            "import anndata as ad,numpy as np,scipy.sparse as sp;"
            f"a=ad.read_h5ad({str(source)!r});"
            "x=a.layers['counts'].tolil();"
            "x[np.asarray(a.obs['sample'].astype(str)=='S4'),:]=0;"
            "a.layers['counts']=x.tocsr();"
            f"a.write_h5ad({str(perturbed_source)!r})"
        )
        run([str(python), "-c", perturb], environment)
        perturbed_markers = work / "validation-perturbed-markers.tsv"
        perturbed_report = work / "validation-perturbed-report.json"
        run([str(python), str(TEMPLATE), "--input-h5ad", str(perturbed_source), "--output-tsv", str(perturbed_markers), "--report", str(perturbed_report), "--cluster-key", "cluster", "--sample-key", "sample", "--raw-count-location", "layers.counts", "--validation-samples", "S4", "--method", "wilcoxon", "--top-per-cluster", "30", "--min-in-fraction", "0.25", "--max-out-fraction", "0.5", "--min-logfc", "0.25", "--max-adjusted-p", "0.05", "--min-sample-support", "3", "--min-validation-sample-support", "1", "--seed", "23"], environment)
        compare = (
            "import json,pandas as pd;"
            f"x=pd.read_csv({str(markers)!r},sep='\\t');"
            f"y=pd.read_csv({str(perturbed_markers)!r},sep='\\t');"
            "cols=['cluster','rank','gene','score','log2_fold_change','p_value','adjusted_p_value','discovery_fraction_in','discovery_fraction_out','discovery_supporting_samples','discovery_discordant_samples','discovery_evaluable_samples','discovery_sample_stability','discovery_admitted_marker'];"
            "print(json.dumps({'ranking_and_discovery_evidence_exact':x[cols].equals(y[cols]),'validation_evidence_changed':not x.filter(regex='^validation_').equals(y.filter(regex='^validation_'))}))"
        )
        leakage = json.loads(run([str(python), "-c", compare], environment).stdout)
        if (
            leakage["ranking_and_discovery_evidence_exact"] is not True
            or leakage["validation_evidence_changed"] is not True
        ):
            raise RuntimeError("held-out validation values leaked into marker discovery")
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        return {"schema_version": 1, "passed": True, "module_id": MODULE_ID, "module_version": "1.1.0", "compatibility_row_id": ROW_ID, "registry_digest": registry.digest,
                "templates": {"marker": {"name": TEMPLATE.name, "sha256": sha256(TEMPLATE)}},
                "tool_versions": {"scanpy": payload["versions"]["scanpy"]}, "dependency_versions": {"python": payload["versions"]["python"], "anndata": payload["versions"]["anndata"]},
                "fixture": {"sha256": source_digest, "cells": 240, "features": 100, "clusters": 2, "biological_samples": 4},
                "execution": {"marker_ranking_completed": True, "held_out_validation_completed": True, "held_out_perturbation_rank_invariance_completed": True, "output_reloaded": True},
                "scientific_summary": {"all_clusters_ranked": True, "raw_detection_fractions_computed": True, "discovery_sample_stability_computed": True, "held_out_sample_stability_computed": True, "validation_excluded_from_ranking_and_threshold_selection": True, "held_out_values_do_not_change_discovery_ranks": True, "held_out_perturbation_changes_validation_evidence": True, "cell_level_p_values_limited_to_descriptive_scope": True, "planted_markers_independently_validated": True, "raw_counts_preserved": True, "no_automatic_label_assignment": True}}


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
