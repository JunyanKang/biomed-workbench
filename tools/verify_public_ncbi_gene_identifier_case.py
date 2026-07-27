#!/usr/bin/env python3
"""Capture the bounded public NCBI TP53 identifier-resolution acceptance case."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.capabilities.evidence import resolve_gene_identifier


MODULE = ROOT / "biomed_workbench/modules/builtin/gene-identifier-resolution/module.json"
TEMPLATE = ROOT / "biomed_workbench/modules/builtin/gene-identifier-resolution/templates/resolve_gene_identifier.py"
REPORT = ROOT / "reports/public-case-ncbi-gene-identifier-resolution.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    observed = resolve_gene_identifier("TP53", "human")
    resolved = observed.get("resolved") or {}
    payload = {
        "case_id": "ncbi-tp53-gene-identifier-resolution-v1",
        "passed": observed.get("resolution_status") == "resolved" and resolved.get("gene_id") == "7157" and resolved.get("taxon_id") == "9606",
        "module_id": "gene-identifier-resolution",
        "module_manifest_sha256": digest(MODULE),
        "template_sha256": digest(TEMPLATE),
        "source_query": {"gene": "TP53", "organism": "human"},
        "analysis": observed,
        "scientific_boundary": [
            "This case verifies a current NCBI Gene identifier resolution and its explicit candidate policy.",
            "It does not establish orthology, functional conservation, expression, phenotype, mechanism, or experimental relevance.",
        ],
    }
    REPORT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"case_id": payload["case_id"], "passed": payload["passed"]}, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
