#!/usr/bin/env python3
"""Execute pySCENIC and SCENIC+ on planted regulatory programs."""

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


MODULE_ID = "single-cell-regulatory-network"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
PYSCENIC = MODULE_ROOT / "templates" / "run_pyscenic.py"
SCENICPLUS = MODULE_ROOT / "templates" / "score_scenicplus_eregulons.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], environment: dict[str, str], *, timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, check=False, timeout=timeout)
    if completed.returncode != 0:
        raise RuntimeError(
            f"regulatory command failed ({completed.returncode}): {' '.join(command[:3])}\n"
            f"stderr:\n{completed.stderr[-6000:]}\nstdout:\n{completed.stdout[-3000:]}"
        )
    return completed


def pyscenic_fixture_code(work: Path) -> str:
    return f"""
import numpy as np, pandas as pd
from pathlib import Path
w=Path({str(work)!r}); rng=np.random.default_rng(701); n=120; labels=np.repeat([0,1],60)
genes=['TF1','TF2']+[f'A{{i}}' for i in range(1,11)]+[f'B{{i}}' for i in range(1,11)]+[f'N{{i}}' for i in range(1,19)]
X=rng.poisson(1.0,(n,len(genes))).astype(float)
for i,y in enumerate(labels):
    if y==0:
        X[i,0]+=rng.poisson(12); X[i,2:12]+=rng.poisson(10,10)
    else:
        X[i,1]+=rng.poisson(12); X[i,12:22]+=rng.poisson(10,10)
pd.DataFrame(X,index=[f'cell-{{i:03d}}' for i in range(n)],columns=genes).to_csv(w/'expression.tsv',sep='\\t')
(w/'tfs.txt').write_text('TF1\\nTF2\\n')
rank=[]
for motif,preferred in [('MOTIF_TF1',['TF1']+[f'A{{i}}' for i in range(1,11)]),('MOTIF_TF2',['TF2']+[f'B{{i}}' for i in range(1,11)])]:
    order=preferred+[g for g in genes if g not in preferred]; positions={{g:i for i,g in enumerate(order)}}; rank.append([positions[g] for g in genes])
pd.DataFrame(rank,index=['MOTIF_TF1','MOTIF_TF2'],columns=genes).to_csv(w/'ranking.tsv',sep='\\t')
pd.DataFrame([['MOTIF_TF1','TF1',0.0,1.0,'direct motif'],['MOTIF_TF2','TF2',0.0,1.0,'direct motif']],columns=['#motif_id','gene_name','motif_similarity_qvalue','orthologous_identity','description']).to_csv(w/'motifs.tsv',sep='\\t',index=False)
"""


def scenicplus_fixture_code(work: Path) -> str:
    return f"""
import numpy as np, pandas as pd
from pathlib import Path
w=Path({str(work)!r}); rng=np.random.default_rng(711); n=120; labels=np.repeat([0,1],60); cells=[f'cell-{{i:03d}}' for i in range(n)]
genes=[f'G{{i}}' for i in range(1,41)]; regions=[f'chr1:{{1000+i*100}}-{{1049+i*100}}' for i in range(40)]
X=rng.gamma(1.5,1,(n,40)); A=rng.gamma(1.5,1,(n,40))
for i,y in enumerate(labels):
    idx=slice(0,10) if y==0 else slice(10,20); signal=rng.gamma(8,1); X[i,idx]+=signal+rng.normal(0,.2,10); A[i,idx]+=signal+rng.normal(0,.2,10)
pd.DataFrame(X,index=cells,columns=genes).to_csv(w/'rna.tsv',sep='\\t'); pd.DataFrame(A,index=cells,columns=regions).to_csv(w/'atac.tsv',sep='\\t')
rows=[]
for tf,start in [('TF_A',0),('TF_B',10)]:
    for j in range(start,start+10):
        rows.append({{'TF':tf,'Gene':genes[j],'Region':regions[j],'Gene_signature_name':tf+'_Gene','Region_signature_name':tf+'_Region','motif_id':'MOTIF_'+tf,'motif_evidence':'direct motif enrichment','region_gene_score':0.9,'region_gene_pvalue':1e-4,'tf_gene_score':0.8}})
pd.DataFrame(rows).to_csv(w/'eregulons.tsv',sep='\\t',index=False)
"""


def verify(pyscenic_python: Path, scenicplus_python: Path) -> dict[str, object]:
    pyscenic_python = pyscenic_python.expanduser().absolute()
    scenicplus_python = scenicplus_python.expanduser().absolute()
    with tempfile.TemporaryDirectory(prefix="biomed-regulatory-") as temporary:
        work = Path(temporary)
        (work / "home").mkdir()
        (work / "cache").mkdir()
        base_environment = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(work / "home"),
            "XDG_CACHE_HOME": str(work / "cache"),
            "PYTHONHASHSEED": "0",
            "LANG": "C",
            "LC_ALL": "C",
            "OMP_NUM_THREADS": "1",
        }
        run([str(pyscenic_python), "-c", pyscenic_fixture_code(work)], {**base_environment, "PATH": str(pyscenic_python.parent) + os.pathsep + base_environment["PATH"]})
        run([str(scenicplus_python), "-c", scenicplus_fixture_code(work)], {**base_environment, "PATH": str(scenicplus_python.parent) + os.pathsep + base_environment["PATH"]})

        pyscenic_environment = {**base_environment, "PATH": str(pyscenic_python.parent) + os.pathsep + base_environment["PATH"]}
        run([
            str(pyscenic_python), str(PYSCENIC), "--expression-tsv", str(work / "expression.tsv"),
            "--tf-list", str(work / "tfs.txt"), "--ranking-tsv", str(work / "ranking.tsv"),
            "--motif-annotations", str(work / "motifs.tsv"), "--adjacencies-output", str(work / "adjacencies.tsv"),
            "--motif-enrichment-output", str(work / "motif-enrichment.tsv"), "--regulons-output", str(work / "regulons.json"),
            "--auc-output", str(work / "regulon-auc.tsv"), "--report", str(work / "pyscenic-report.json"),
            "--seed", "701", "--min-targets", "5", "--rank-threshold", "30", "--cis-auc-threshold", "0.3",
            "--nes-threshold", "0", "--rho-threshold", "0.03", "--aucell-threshold", "0.25",
        ], pyscenic_environment)

        scenicplus_environment = {**base_environment, "PATH": str(scenicplus_python.parent) + os.pathsep + base_environment["PATH"]}
        run([
            str(scenicplus_python), str(SCENICPLUS), "--expression-tsv", str(work / "rna.tsv"),
            "--accessibility-tsv", str(work / "atac.tsv"), "--eregulons-tsv", str(work / "eregulons.tsv"),
            "--gene-auc-output", str(work / "gene-auc.tsv"), "--region-auc-output", str(work / "region-auc.tsv"),
            "--concordance-output", str(work / "concordance.tsv"), "--validated-eregulons-output", str(work / "validated-eregulons.tsv"),
            "--report", str(work / "scenicplus-report.json"), "--auc-threshold", "0.25", "--minimum-targets", "5",
        ], scenicplus_environment)

        pyscenic_report = json.loads((work / "pyscenic-report.json").read_text(encoding="utf-8"))
        scenicplus_report = json.loads((work / "scenicplus-report.json").read_text(encoding="utf-8"))
        pyscenic_evaluation = json.loads(run([str(pyscenic_python), "-c", f"""
import json, pandas as pd, numpy as np
reg=json.load(open({str(work / 'regulons.json')!r})); auc=pd.read_csv({str(work / 'regulon-auc.tsv')!r},sep='\\t',index_col=0)
target_recovery={{}}
for tf,prefix in [('TF1','A'),('TF2','B')]:
    record=next(x for x in reg if x['transcription_factor']==tf); truth={{f'{{prefix}}{{i}}' for i in range(1,11)}}; target_recovery[tf]=len(set(record['targets']) & truth)
groups=np.repeat([0,1],60); contrasts={{'TF1':float(auc.loc[groups==0,'TF1(+)'].mean()-auc.loc[groups==1,'TF1(+)'].mean()),'TF2':float(auc.loc[groups==1,'TF2(+)'].mean()-auc.loc[groups==0,'TF2(+)'].mean())}}
print(json.dumps({{'planted_targets_recovered':target_recovery,'activity_contrasts':contrasts}}))
"""], pyscenic_environment).stdout)
        scenicplus_evaluation = json.loads(run([str(scenicplus_python), "-c", f"""
import json, pandas as pd, numpy as np
g=pd.read_csv({str(work / 'gene-auc.tsv')!r},sep='\\t',index_col=0); r=pd.read_csv({str(work / 'region-auc.tsv')!r},sep='\\t',index_col=0); c=pd.read_csv({str(work / 'concordance.tsv')!r},sep='\\t'); groups=np.repeat([0,1],60)
contrasts={{}}
for tf,group in [('TF_A',0),('TF_B',1)]:
    contrasts[tf]={{'gene':float(g.loc[groups==group,tf+'_Gene'].mean()-g.loc[groups!=group,tf+'_Gene'].mean()),'region':float(r.loc[groups==group,tf+'_Region'].mean()-r.loc[groups!=group,tf+'_Region'].mean())}}
print(json.dumps({{'minimum_gene_region_pearson':float(c.pearson.min()),'minimum_gene_region_spearman':float(c.spearman.min()),'activity_contrasts':contrasts}}))
"""], scenicplus_environment).stdout)

        if pyscenic_report["quality_status"] != "passed" or scenicplus_report["quality_status"] != "passed":
            raise RuntimeError("a regulatory backend did not pass its own quality gates")
        if min(pyscenic_evaluation["planted_targets_recovered"].values()) < 10 or min(pyscenic_evaluation["activity_contrasts"].values()) < 0.3:
            raise RuntimeError("pySCENIC failed planted regulon recovery")
        if scenicplus_evaluation["minimum_gene_region_pearson"] < 0.95 or min(value for pair in scenicplus_evaluation["activity_contrasts"].values() for value in pair.values()) < 0.3:
            raise RuntimeError("SCENIC+ failed planted paired-regulon recovery")

        pv = pyscenic_report["versions"]
        sv = scenicplus_report["versions"]
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        return {
            "schema_version": 1,
            "passed": True,
            "module_id": MODULE_ID,
            "module_version": "1.1.0",
            "compatibility_row_id": "agent-protocol-1-pyscenic-0121-scenicplus-10a2",
            "registry_digest": registry.digest,
            "templates": {
                "pyscenic": {"name": PYSCENIC.name, "sha256": sha256(PYSCENIC)},
                "scenicplus": {"name": SCENICPLUS.name, "sha256": sha256(SCENICPLUS)},
            },
            "tool_versions": {"pyscenic": pv["pyscenic"], "scenicplus": sv["scenicplus"]},
            "dependency_versions": {
                "python-pyscenic": pv["python"], "arboreto": pv["arboreto"], "ctxcore": pv["ctxcore"],
                "numpy-pyscenic": pv["numpy"], "pandas-pyscenic": pv["pandas"], "scipy-pyscenic": pv["scipy"],
                "dask": pv["dask"], "distributed": pv["distributed"], "setuptools-pyscenic": pv["setuptools"], "python-scenicplus": sv["python"],
                "pycistopic": sv["pycistopic"], "numpy-scenicplus": sv["numpy"], "pandas-scenicplus": sv["pandas"],
                "scipy-scenicplus": sv["scipy"], "scikit-learn-scenicplus": sv["scikit-learn"], "tables": sv["tables"],
            },
            "fixture": {"cells": 120, "pyscenic_genes": 40, "transcription_factors": 2, "motifs": 2, "scenicplus_genes": 40, "regions": 40, "eregulon_pairs": 2},
            "execution": {"grnboost2_completed": True, "cistarget_completed": True, "aucell_completed": True, "scenicplus_gene_auc_completed": True, "scenicplus_region_auc_completed": True, "outputs_reloaded": True},
            "backend_summaries": {"pyscenic": pyscenic_report["results"], "scenicplus": scenicplus_report["results"]},
            "independent_evaluation": {"pyscenic": pyscenic_evaluation, "scenicplus": scenicplus_evaluation},
            "scientific_summary": {
                "grnboost2_executed": True, "cistarget_motif_pruning_executed": True, "regulons_constructed": True,
                "aucell_executed_for_every_cell": True, "scenicplus_gene_and_region_auc_executed": True,
                "planted_tf_target_programs_recovered": True, "paired_rna_atac_programs_recovered": True,
                "coexpression_motif_and_region_gene_evidence_separated": True, "resources_hashed": True,
                "paired_cells_and_source_inputs_preserved": True, "outputs_reloaded": True,
                "causal_claims_prohibited_without_independent_evidence": True,
                "no_environment_or_compute_infrastructure_managed": True,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pyscenic-python", type=Path, required=True)
    parser.add_argument("--scenicplus-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.pyscenic_python, args.scenicplus_python)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": MODULE_ID, "passed": True, "tool_versions": report["tool_versions"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
