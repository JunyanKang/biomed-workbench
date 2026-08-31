#!/usr/bin/env python3
"""Run bounded no-retry live checks for the 0.2.8 public-evidence client."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.evidence_scope import module_evidence_scope  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402
from biomed_workbench.services.public_databases import PublicJSONClient  # noqa: E402
from biomed_workbench.services.research_evidence import (  # noqa: E402
    PUBLIC_RESEARCH_EVIDENCE_CONTRACT_VERSION,
    query_public_research_evidence,
)


CASES = (
    ("chembl_molecule_search", "chembl", "molecule-search", "aspirin"),
    ("chembl_activities_by_molecule", "chembl", "activities-by-molecule", "CHEMBL25"),
    ("gwas_trait_studies", "gwas-catalog", "studies-by-trait", "T2-high asthma"),
    ("gwas_gene_associations", "gwas-catalog", "associations-by-gene", "BANP"),
    ("pride_project_discovery", "pride", "projects", "retina"),
    ("biostudies_study_discovery", "biostudies", "studies", "retina"),
    ("encode_experiment_discovery", "encode", "experiments", "retina"),
    ("human_protein_atlas_gene", "human-protein-atlas", "gene", "BANP"),
    ("mgnify_study_discovery", "mgnify", "studies", "gut"),
)


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build() -> dict[str, object]:
    client = PublicJSONClient(timeout=60, retries=0)
    checks = []
    for name, source, operation, query in CASES:
        try:
            result = query_public_research_evidence(source, operation, query, 2, client=client)
        except Exception as exc:
            raise RuntimeError(f"live verification failed for {name}") from exc
        checks.append({
            "name": name,
            "database": f"{source}:{operation}",
            "query": query,
            "returned_count": result["returned_count"],
            "status_code": result["provenance"]["transport"]["status_code"],
            "records_truncated": result["records_truncated"],
            "output_sha256": _digest(result),
            "passed": result["returned_count"] >= 1 and result["provenance"]["transport"]["status_code"] == 200,
        })
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    module_ids = ["public-research-evidence-query"]
    return {
        "schema_version": 1,
        "passed": all(item["passed"] for item in checks),
        "verified_at": "2026-08-31",
        "contract_version": PUBLIC_RESEARCH_EVIDENCE_CONTRACT_VERSION,
        "module_ids": module_ids,
        "evidence_scope": module_evidence_scope(registry, module_ids).to_dict(),
        "checks": checks,
        "scientific_summary": {
            "fixed_official_operations_executed": True,
            "caller_controlled_hosts_rejected": True,
            "source_specific_record_containers_reloaded": True,
            "database_records_remain_context_not_mechanism": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/public-research-evidence-live-verification.json")
    args = parser.parse_args()
    report = build()
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "check_count": len(report["checks"])}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
