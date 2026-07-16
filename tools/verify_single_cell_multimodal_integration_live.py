#!/usr/bin/env python3
"""Execute RNA+ATAC/ADT WNN and three-view MOFA+ on planted paired-cell fixtures."""

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


MODULE_ID = "single-cell-multimodal-integration"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
WNN = MODULE_ROOT / "templates" / "run_wnn.R"
MOFA = MODULE_ROOT / "templates" / "fit_mofaplus.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], environment: dict[str, str], *, timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, check=False, timeout=timeout)
    if completed.returncode != 0:
        raise RuntimeError(f"multimodal command failed ({completed.returncode}): {' '.join(command[:3])}\nstderr:\n{completed.stderr[-6000:]}\nstdout:\n{completed.stdout[-3000:]}")
    return completed


def r_fixture_code(work: Path) -> str:
    return f"""
suppressPackageStartupMessages({{library(Seurat);library(Signac);library(Matrix)}})
set.seed(901); n <- 180; labels <- rep(c('TypeA','TypeB','TypeC'), each=60); cells <- paste0('cell-',sprintf('%03d',1:n))
make_counts <- function(features, starts, boost) {{ m <- matrix(rpois(length(features)*n,1.5),nrow=length(features),dimnames=list(features,cells)); for(i in seq_len(n)){{s<-starts[[labels[[i]]]];m[s:(s+9),i]<-m[s:(s+9),i]+rpois(10,boost)}};as(m,'dgCMatrix') }}
rna <- make_counts(paste0('GENE',sprintf('%03d',1:120)),c(TypeA=1,TypeB=21,TypeC=41),7)
atac <- make_counts(paste0('chr1:',seq(1000,by=200,length.out=90),'-',seq(1099,by=200,length.out=90)),c(TypeA=1,TypeB=21,TypeC=41),5)
adt <- make_counts(paste0('PROT',sprintf('%02d',1:36)),c(TypeA=1,TypeB=13,TypeC=25),9)
a <- CreateSeuratObject(rna); a$truth <- labels; a[['ATAC']] <- CreateChromatinAssay(atac,sep=c(':','-')); saveRDS(a,{str(work / 'rna-atac.rds')!r})
c <- CreateSeuratObject(rna); c$truth <- labels; c[['ADT']] <- CreateAssayObject(adt); saveRDS(c,{str(work / 'rna-adt.rds')!r})
"""


def python_fixture_code(work: Path) -> str:
    return f"""
import anndata as ad, mudata as md, numpy as np, pandas as pd, json
from scipy import sparse
rng=np.random.default_rng(905); n=180; labels=np.repeat(np.arange(3),60); latent=np.array([-1,0,1])[labels]+rng.normal(0,.15,n); cells=[f'cell-{{i:03d}}' for i in range(n)]; mods={{}}
for name,p,scale in [('rna',100,1.6),('atac',80,1.3),('adt',30,2.0)]:
    load=np.zeros(p);load[:15]=np.linspace(.5,1.5,15)*scale; X=latent[:,None]*load[None,:]+rng.normal(0,.45,(n,p)); X[:,15:30]+=(labels==1)[:,None]*1.5
    a=ad.AnnData(sparse.csr_matrix(np.maximum(np.rint(np.exp(X-X.min()+.2)),0).astype(np.int32)),obs=pd.DataFrame({{'truth':labels,'latent_truth':latent}},index=cells),var=pd.DataFrame(index=[f'{{name.upper()}}_{{i:03d}}' for i in range(p)])); a.layers['model']=sparse.csr_matrix(X);mods[name]=a
m=md.MuData(mods);m.write_h5mu({str(work / 'multimodal.h5mu')!r})
open({str(work / 'mofa-config.json')!r},'w').write(json.dumps([{{'name':name,'location':'layers.model','top_variable_features':min(60,a.n_vars)}} for name,a in mods.items()],indent=2))
"""


def verify(python: Path, rscript: Path) -> dict[str, object]:
    python = python.expanduser().absolute(); rscript = rscript.expanduser().absolute()
    with tempfile.TemporaryDirectory(prefix="biomed-multimodal-") as temporary:
        work = Path(temporary); (work / "home").mkdir(); (work / "cache").mkdir()
        environment = {"PATH": str(python.parent) + os.pathsep + str(rscript.parent) + os.pathsep + os.environ.get("PATH", ""), "HOME": str(work / "home"), "XDG_CACHE_HOME": str(work / "cache"), "PYTHONHASHSEED": "0", "LANG": "C", "LC_ALL": "C"}
        run([str(rscript), "-e", r_fixture_code(work)], environment); run([str(python), "-c", python_fixture_code(work)], environment)
        reports = {}
        for prefix, assay, kind, dims, seed in (("rna-atac", "ATAC", "atac", "15", "902"), ("rna-adt", "ADT", "adt", "12", "903")):
            run([str(rscript), str(WNN), "--input-rds", str(work / f"{prefix}.rds"), "--output-rds", str(work / f"{prefix}-wnn.rds"), "--cell-table", str(work / f"{prefix}-cells.tsv"), "--report", str(work / f"{prefix}.json"), "--rna-assay", "RNA", "--secondary-assay", assay, "--secondary-type", kind, "--rna-variable-features", "80", "--rna-dims", "15", "--secondary-dims", dims, "--k-nn", "15", "--resolution", "0.5", "--seed", seed], environment)
            reports[prefix] = json.loads((work / f"{prefix}.json").read_text())
        run([str(python), str(MOFA), "--input-h5mu", str(work / "multimodal.h5mu"), "--view-config", str(work / "mofa-config.json"), "--model-output", str(work / "mofa.hdf5"), "--factor-table", str(work / "mofa-factors.tsv"), "--weight-table", str(work / "mofa-weights.tsv"), "--variance-table", str(work / "mofa-variance.tsv"), "--report", str(work / "mofa.json"), "--factors", "6", "--iterations", "300", "--convergence-mode", "fast", "--seed", "906"], environment)
        mofa = json.loads((work / "mofa.json").read_text())
        inspection = json.loads(run([str(python), "-c", f"""
import json, pandas as pd, mudata as md, numpy as np
from sklearn.metrics import adjusted_rand_score
def ari(prefix):
 d=pd.read_csv({str(work)!r}+f'/{{prefix}}-cells.tsv',sep='\\t'); truth=np.repeat(np.arange(3),60); return adjusted_rand_score(truth,d.wnn_cluster.astype(str))
f=pd.read_csv({str(work / 'mofa-factors.tsv')!r},sep='\\t'); m=md.read_h5mu({str(work / 'multimodal.h5mu')!r}); truth=m.mod['rna'].obs.loc[f.cell_id,'latent_truth'].to_numpy(); correlations={{c:float(np.corrcoef(f[c],truth)[0,1]) for c in f.columns[1:]}}
print(json.dumps({{'rna_atac_ari':ari('rna-atac'),'rna_adt_ari':ari('rna-adt'),'mofa_factor_truth_correlations':correlations,'maximum_absolute_mofa_truth_correlation':max(abs(x) for x in correlations.values())}}))
"""], environment).stdout)
        if any(item["quality_status"] != "passed" for item in reports.values()) or mofa["quality_status"] != "passed" or inspection["rna_atac_ari"] < 0.95 or inspection["rna_adt_ari"] < 0.95 or inspection["maximum_absolute_mofa_truth_correlation"] < 0.95:
            raise RuntimeError("WNN or MOFA+ failed planted multimodal recovery")
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        return {"schema_version": 1, "passed": True, "module_id": MODULE_ID, "module_version": "1.0.0", "compatibility_row_id": "agent-protocol-1-seurat-521-signac-116-mofapy2-074", "registry_digest": registry.digest, "templates": {"wnn": {"name": WNN.name, "sha256": sha256(WNN)}, "mofaplus": {"name": MOFA.name, "sha256": sha256(MOFA)}}, "tool_versions": {"Seurat": reports["rna-atac"]["versions"]["Seurat"], "Signac": reports["rna-atac"]["versions"]["Signac"], "mofapy2": mofa["versions"]["mofapy2"]}, "dependency_versions": {"r": reports["rna-atac"]["versions"]["R"], "Matrix": reports["rna-atac"]["versions"]["Matrix"], "uwot": reports["rna-atac"]["versions"]["uwot"], "jsonlite": reports["rna-atac"]["versions"]["jsonlite"], "digest": reports["rna-atac"]["versions"]["digest"], **{key: mofa["versions"][key] for key in ("python", "mudata", "anndata", "numpy", "pandas", "scipy", "h5py")}}, "fixture": {"cells": 180, "classes": 3, "rna_features": 120, "atac_features": 90, "adt_features": 36, "mofa_views": 3}, "execution": {"rna_atac_wnn_completed": True, "rna_adt_wnn_completed": True, "mofaplus_completed": True, "outputs_reloaded": True}, "backend_summaries": {"rna_atac_wnn": reports["rna-atac"]["results"], "rna_adt_wnn": reports["rna-adt"]["results"], "mofaplus": mofa["results"]}, "independent_evaluation": inspection, "scientific_summary": {"rna_atac_wnn_executed": True, "rna_adt_wnn_executed": True, "cell_specific_modality_weights_retained": True, "wknn_wsnn_neighbor_umap_and_clusters_retained": True, "mofaplus_three_view_model_converged": True, "mofaplus_factors_weights_and_variance_retained": True, "planted_shared_factor_recovered": True, "paired_cells_and_source_counts_preserved": True, "outputs_reloaded": True, "evaluation_labels_posthoc_only": True, "no_environment_or_compute_infrastructure_managed": True}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--scientific-python", type=Path, required=True); parser.add_argument("--rscript", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    report = verify(args.scientific_python, args.rscript); args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n"); print(json.dumps({"module_id": MODULE_ID, "passed": True, "tool_versions": report["tool_versions"]}, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
