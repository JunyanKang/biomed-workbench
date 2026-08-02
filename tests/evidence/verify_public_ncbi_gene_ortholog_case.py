#!/usr/bin/env python3
"""Capture the bounded public NCBI TP53-to-mouse ortholog acceptance case."""
import hashlib, json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from biomed_workbench.capabilities.evidence import gene_ortholog_evidence
from biomed_workbench.modules.evidence_scope import module_evidence_scope
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
MODULE=ROOT/"biomed_workbench/modules/builtin/gene-ortholog-evidence/module.json"
REPORT=ROOT/"reports/public-case-ncbi-gene-ortholog.json"
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    registry=ModuleRegistry.discover(BUILTIN_ROOT)
    observed=gene_ortholog_evidence("7157",10090,10)
    payload={"case_id":"ncbi-tp53-human-mouse-ortholog-v1","passed":observed.get("source",{}).get("gene_id")=="7157" and any(record.get("gene_id")=="22059" for record in observed.get("orthologs",[])),"module_id":"gene-ortholog-evidence","module_manifest_sha256":sha(MODULE),"registry_digest":registry.digest,"evidence_scope":module_evidence_scope(registry,["gene-ortholog-evidence"]).to_dict(),"source_query":{"gene_id":"7157","target_taxon_id":10090},"analysis":observed,"scientific_boundary":["This case verifies a current NCBI database ortholog record and bounded provenance.","It does not establish functional, regulatory, expression, phenotype, cell-state or experimental equivalence between TP53 and Trp53."]}
    REPORT.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"case_id":payload["case_id"],"passed":payload["passed"]},sort_keys=True)); return 0 if payload["passed"] else 1
if __name__=="__main__": raise SystemExit(main())
