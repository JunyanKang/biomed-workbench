#!/usr/bin/env python3
"""Run bounded live E-utilities checks and write secret-free release evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.services.eutils import EUtilitiesClient  # noqa: E402
from biomed_workbench.capabilities.evidence import gene_evidence  # noqa: E402


def _check(name: str, database: str, passed: bool, detail: dict[str, int | bool]) -> dict[str, object]:
    return {"name": name, "database": database, "passed": bool(passed), "detail": detail}


def run() -> dict[str, object]:
    client = EUtilitiesClient(timeout=20, retries=2)
    checks: list[dict[str, object]] = []

    pubmed = client.search("pubmed", "TP53[Title]", retmax=1)
    checks.append(_check("search", "pubmed", pubmed.count > 0 and len(pubmed.ids) == 1, {"count": pubmed.count}))
    pubmed_summary = client.summary("pubmed", pubmed.ids)
    checks.append(_check("summary", "pubmed", len(pubmed_summary.records) == 1, {"records": len(pubmed_summary.records)}))

    pmc = client.search("pmc", "retinal development", retmax=1)
    checks.append(_check("search", "pmc", pmc.count > 0, {"count": pmc.count}))

    gene = client.search("gene", "TP53[Gene Name] AND human[Organism]", retmax=1)
    checks.append(_check("search", "gene", gene.count == 1 and len(gene.ids) == 1, {"count": gene.count}))
    gene_links = client.link("gene", "protein", gene.ids)
    checks.append(_check("link", "gene_to_protein", len(gene_links.links) > 0, {"links": len(gene_links.links)}))
    bundle = gene_evidence("TP53", organism="human", max_links=1)
    checks.append(
        _check(
            "composed_workflow",
            "gene_evidence_bundle",
            bool(bundle["gene_records"])
            and bundle["linked"]["protein"]["total"] > 0
            and bundle["linked"]["clinvar"]["total"] > 0
            and bundle["linked"]["pubmed"]["total"] > 0,
            {
                "gene_records": len(bundle["gene_records"]),
                "protein_links": bundle["linked"]["protein"]["total"],
                "clinvar_links": bundle["linked"]["clinvar"]["total"],
                "pubmed_links": bundle["linked"]["pubmed"]["total"],
            },
        )
    )

    protein = client.fetch("protein", ["NP_000537.3"], rettype="fasta", retmode="text")
    checks.append(_check("fetch", "protein", protein.text.startswith(">"), {"nonempty": bool(protein.text)}))
    nucleotide = client.fetch("nuccore", ["NM_000546.6"], rettype="fasta", retmode="text")
    checks.append(_check("fetch", "nuccore", nucleotide.text.startswith(">"), {"nonempty": bool(nucleotide.text)}))

    for database, term in (
        ("clinvar", "TP53[gene]"),
        ("sra", "retina AND human[organism]"),
        ("gds", "retina[All Fields]"),
        ("biosample", "Homo sapiens[Organism] AND retina"),
        ("bioproject", "retina AND human[organism]"),
    ):
        result = client.search(database, term, retmax=1)
        checks.append(_check("search", database, result.count > 0, {"count": result.count}))

    return {
        "schema_version": 1,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "service": "NCBI Entrez E-utilities",
        "credential_mode": "api_key" if os.environ.get("NCBI_API_KEY", "").strip() else "zero_key",
        "documentation": [
            "https://www.ncbi.nlm.nih.gov/books/NBK25497/",
            "https://www.ncbi.nlm.nih.gov/books/NBK25499/",
        ],
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": payload["passed"], "checks": len(payload["checks"]), "credential_mode": payload["credential_mode"]}))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
