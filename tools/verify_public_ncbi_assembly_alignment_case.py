#!/usr/bin/env python3
"""Run the public NCBI J01673.1 minimap2 assembly-alignment acceptance case."""
import hashlib, json, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "biomed_workbench/modules/builtin/assembly-reference-alignment"
TEMPLATE = MODULE / "templates/run_minimap2_assembly.py"
FIXTURE = ROOT / "tests/fixtures/assembly-reference-alignment/ncbi-j01673.1-rho.fasta"
REPORT = ROOT / "reports/public-case-ncbi-assembly-alignment.json"
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    with tempfile.TemporaryDirectory() as d:
        out=Path(d)/"alignment"; run=subprocess.run(["python3",str(TEMPLATE),"--reference",str(FIXTURE),"--query",str(FIXTURE),"--preset","asm5","--minimum-query-coverage","0.9","--output-dir",str(out)],cwd=ROOT,text=True,capture_output=True,check=False,timeout=180)
        if run.returncode: raise RuntimeError(run.stdout+run.stderr)
        observed=json.loads((out/"assembly-alignment-report.json").read_text())
    payload={"case_id":"ncbi-j01673-assembly-alignment-v1","passed":observed.get("passed") is True and observed.get("alignment",{}).get("rows",0)>0,"module_id":"assembly-reference-alignment","module_manifest_sha256":sha(MODULE/"module.json"),"template_sha256":sha(TEMPLATE),"fixture_sha256":sha(FIXTURE),"source_record":"NCBI Nucleotide:J01673.1","analysis":observed,"scientific_boundary":["This case validates declared-sequence alignment and PAF reload only.","It does not establish variants, haplotypes, synteny, structural variation, orthology or functional conservation."]}
    REPORT.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"case_id":payload["case_id"],"passed":payload["passed"]},sort_keys=True)); return 0 if payload["passed"] else 1
if __name__ == "__main__": raise SystemExit(main())
