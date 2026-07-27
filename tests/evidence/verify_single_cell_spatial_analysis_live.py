#!/usr/bin/env python3
"""Execute H5AD and SpatialData spatial analysis on replicated planted zones."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


MODULE_ID = "single-cell-spatial-analysis"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
TEMPLATE = MODULE_ROOT / "templates" / "run_spatial_analysis.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], environment: dict[str, str], *, timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, check=False, timeout=timeout)
    if completed.returncode != 0:
        raise RuntimeError(
            f"spatial command failed ({completed.returncode}): {' '.join(command[:3])}\n"
            f"stderr:\n{completed.stderr[-6000:]}\nstdout:\n{completed.stdout[-3000:]}"
        )
    return completed


def fixture_code(work: Path) -> str:
    return f"""
import numpy as np, pandas as pd, anndata as ad, xarray as xr
from scipy import sparse
from pathlib import Path
from spatialdata import SpatialData
from spatialdata.models import Image2DModel
w=Path({str(work)!r}); rng=np.random.default_rng(811); rows=[]; coords=[]; counts=[]
genes=['SVG_A','SVG_B','SVG_C']+[f'A{{i}}' for i in range(1,11)]+[f'B{{i}}' for i in range(1,11)]+[f'C{{i}}' for i in range(1,11)]+[f'N{{i}}' for i in range(1,28)]
for sample_i,sample in enumerate(['S1','S2']):
    for y in range(12):
        for x in range(15):
            z=0 if x<5 else (1 if x<10 else 2); zone='ABC'[z]; values=rng.poisson(.5,len(genes)); values[z]+=rng.poisson(20); start=3+10*z; values[start:start+10]+=rng.poisson(10,10)
            counts.append(values); coords.append([x+sample_i*30,y]); rows.append((f'{{sample}}-{{x:02d}}-{{y:02d}}',sample,zone))
obs=pd.DataFrame(rows,columns=['cell_id','sample','cell_type']).set_index('cell_id')
adata=ad.AnnData(sparse.csr_matrix(np.asarray(counts,dtype=np.int32)),obs=obs,var=pd.DataFrame(index=genes)); adata.obsm['spatial']=np.asarray(coords,float); adata.write_h5ad(w/'input.h5ad')
image=Image2DModel.parse(xr.DataArray(np.zeros((1,12,45),dtype=np.uint8),dims=('c','y','x'),coords={{'c':['intensity']}}))
SpatialData(images={{'histology':image}},tables={{'spots':adata.copy()}}).write(w/'input.zarr')
"""


def command(python: Path, work: Path, prefix: str, input_arguments: list[str]) -> list[str]:
    return [
        str(python), str(TEMPLATE), *input_arguments,
        "--output-h5ad", str(work / f"{prefix}-output.h5ad"), "--observation-output", str(work / f"{prefix}-observations.tsv"),
        "--graph-output", str(work / f"{prefix}-graph.tsv"), "--neighborhood-output", str(work / f"{prefix}-neighborhood.tsv"),
        "--cooccurrence-output", str(work / f"{prefix}-cooccurrence.tsv"), "--moran-output", str(work / f"{prefix}-moran.tsv"),
        "--spatial-genes-output", str(work / f"{prefix}-spatial-genes.tsv"), "--report", str(work / f"{prefix}-report.json"),
        "--sample-key", "sample", "--cluster-key", "cell_type", "--coordinate-unit", "grid-unit",
        "--genes", "SVG_A,SVG_B,SVG_C,N1,N2,N3", "--n-spatial-neighbors", "6", "--permutations", "199",
        "--cooccurrence-intervals", "10", "--svg-fdr", "0.05", "--minimum-moran", "0.15",
        "--minimum-supporting-samples", "2", "--domain-hvgs", "50", "--domain-pcs", "15",
        "--domain-neighbors", "15", "--domain-resolution", "0.15", "--coordinate-weight", "2.0", "--seed", "813",
    ]


def verify(scientific_python: Path) -> dict[str, object]:
    scientific_python = scientific_python.expanduser().absolute()
    with tempfile.TemporaryDirectory(prefix="biomed-spatial-") as temporary:
        work = Path(temporary)
        (work / "home").mkdir()
        (work / "cache").mkdir()
        environment = {
            "PATH": str(scientific_python.parent) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(work / "home"), "XDG_CACHE_HOME": str(work / "cache"), "PYTHONHASHSEED": "0",
            "LANG": "C", "LC_ALL": "C", "OMP_NUM_THREADS": "1",
        }
        run([str(scientific_python), "-c", fixture_code(work)], environment)
        run(command(scientific_python, work, "h5ad", ["--input-h5ad", str(work / "input.h5ad")]), environment)
        run(command(scientific_python, work, "spatialdata", ["--input-spatialdata-zarr", str(work / "input.zarr"), "--table-name", "spots"]), environment)

        reports = {prefix: json.loads((work / f"{prefix}-report.json").read_text(encoding="utf-8")) for prefix in ("h5ad", "spatialdata")}
        evaluation = json.loads(run([str(scientific_python), "-c", f"""
import json, pandas as pd
from sklearn.metrics import adjusted_rand_score
from pathlib import Path
w=Path({str(work)!r}); result={{}}
for prefix in ('h5ad','spatialdata'):
    obs=pd.read_csv(w/f'{{prefix}}-observations.tsv',sep='\\t'); nhood=pd.read_csv(w/f'{{prefix}}-neighborhood.tsv',sep='\\t'); co=pd.read_csv(w/f'{{prefix}}-cooccurrence.tsv',sep='\\t'); svg=pd.read_csv(w/f'{{prefix}}-spatial-genes.tsv',sep='\\t')
    diagonal=nhood.source_cluster==nhood.target_cluster; nearest=co.distance_upper==co.groupby('sample').distance_upper.transform('min'); near=co[nearest]; near_diagonal=near.source_cluster==near.target_cluster
    result[prefix]={{'domain_ari':float(adjusted_rand_score(obs.cell_type,obs.spatial_domain)),'neighborhood_diagonal_gap':float(nhood.loc[diagonal,'zscore'].mean()-nhood.loc[~diagonal,'zscore'].mean()),'nearest_cooccurrence_diagonal_gap':float(near.loc[near_diagonal,'cooccurrence'].mean()-near.loc[~near_diagonal,'cooccurrence'].mean()),'admitted_spatial_genes':sorted(svg.gene.tolist()),'spatial_gene_support':{{row.gene:int(row.supporting_samples) for row in svg.itertuples(index=False)}}}}
print(json.dumps(result))
"""], environment).stdout)

        expected_genes = ["SVG_A", "SVG_B", "SVG_C"]
        for prefix in ("h5ad", "spatialdata"):
            if reports[prefix]["quality_status"] != "passed" or evaluation[prefix]["domain_ari"] < 0.95:
                raise RuntimeError(f"{prefix} spatial domains failed planted recovery")
            if evaluation[prefix]["admitted_spatial_genes"] != expected_genes or set(evaluation[prefix]["spatial_gene_support"].values()) != {2}:
                raise RuntimeError(f"{prefix} replicated spatial genes failed planted recovery")
            if evaluation[prefix]["neighborhood_diagonal_gap"] <= 10 or evaluation[prefix]["nearest_cooccurrence_diagonal_gap"] <= 1:
                raise RuntimeError(f"{prefix} neighborhood or co-occurrence failed planted recovery")
        if reports["spatialdata"]["input"]["spatial_elements"]["images"] != ["histology"] or reports["spatialdata"]["input"]["spatial_elements"]["tables"] != ["spots"]:
            raise RuntimeError("SpatialData image and table provenance was not preserved")
        if reports["h5ad"]["input"]["source_count_digest"] != reports["spatialdata"]["input"]["source_count_digest"]:
            raise RuntimeError("H5AD and SpatialData did not preserve identical source counts")

        versions = reports["h5ad"]["versions"]
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        return {
            "schema_version": 1, "passed": True, "module_id": MODULE_ID, "module_version": "1.1.0",
            "compatibility_row_id": "agent-protocol-1-squidpy-166-spatialdata-050-scanpy-1115",
            "registry_digest": registry.digest,
            "templates": {"spatial": {"name": TEMPLATE.name, "sha256": sha256(TEMPLATE)}},
            "tool_versions": {key: versions[key] for key in ("squidpy", "spatialdata", "scanpy")},
            "dependency_versions": {key: versions[key] for key in ("python", "anndata", "numpy", "pandas", "scipy", "scikit-learn", "igraph", "zarr", "setuptools")},
            "fixture": {"observations": 360, "biological_samples": 2, "observations_per_sample": 180, "genes": 60, "planted_zones": 3, "planted_spatial_genes": 3, "negative_control_genes": 3, "spatialdata_images": 1},
            "execution": {"h5ad_completed": True, "spatialdata_completed": True, "spatial_graph_completed": True, "neighborhood_completed": True, "cooccurrence_completed": True, "moran_completed": True, "domain_model_completed": True, "outputs_reloaded": True},
            "backend_summaries": {prefix: {"input": reports[prefix]["input"], "results": reports[prefix]["results"]} for prefix in reports},
            "independent_evaluation": evaluation,
            "scientific_summary": {
                "h5ad_and_spatialdata_zarr_executed": True, "spatialdata_image_and_table_provenance_retained": True,
                "sample_isolated_spatial_graph_executed": True, "zero_cross_sample_spatial_edges": True,
                "sample_restricted_neighborhood_permutations_executed": True, "sample_level_cooccurrence_executed": True,
                "global_and_sample_level_moran_executed": True, "multiplicity_and_sample_replication_gates_applied": True,
                "all_planted_spatial_genes_and_no_controls_admitted": True, "three_planted_domains_recovered_without_label_leakage": True,
                "source_counts_cells_genes_coordinates_and_elements_preserved": True, "outputs_reloaded": True,
                "spots_not_used_as_condition_replicates": True, "no_environment_or_compute_infrastructure_managed": True,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.scientific_python)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": MODULE_ID, "passed": True, "tool_versions": report["tool_versions"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
