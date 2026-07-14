#!/usr/bin/env python3
"""Refresh dynamic capability coverage evidence while preserving reviewed gap policy."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


DIGEST_FIELDS = (
    "learned_file_count",
    "current_capability_ids",
    "source_file_counts",
    "source_reconciliation",
    "implemented_expansion",
    "priority_gaps",
    "product_exclusions",
)

MODULE_GAP_COVERAGE = {
    "citation-record-resolution": ("evidence", "citation_verification"),
    "preprint-evidence": ("evidence", "preprint_discovery"),
    "chemical-evidence": ("evidence", "chemical_database_query"),
    "clinical-trial-evidence": ("evidence", "clinical_trial_registry"),
    "structure-evidence": ("evidence", "structure_database_query"),
}


def refresh(path: Path) -> dict[str, object]:
    audit = json.loads(path.read_text(encoding="utf-8"))
    assimilation = json.loads((ROOT / "reports" / "source-assimilation-summary.json").read_text(encoding="utf-8"))
    reconciliation = json.loads((ROOT / "reports" / "source-reconciliation-summary.json").read_text(encoding="utf-8"))
    snapshot = json.loads((ROOT / "reports" / "module-registry-verification.json").read_text(encoding="utf-8"))
    compatibility = json.loads((ROOT / "reports" / "compatibility-execution-evidence.json").read_text(encoding="utf-8"))
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    ids = [module.id for module in registry.all()]
    source_counts = {source["source"]: source["file_count"] for source in assimilation["sources"]}
    audit.update(
        learned_file_count=sum(source_counts.values()),
        current_capability_count=len(ids),
        current_capability_ids=ids,
        source_file_counts=source_counts,
        module_registry_verification={
            "module_count": len(ids),
            "registry_digest": registry.digest,
            "installed_cache_verified": snapshot.get("passed") is True,
            "dynamic_registration_verified": snapshot.get("installed_cache", {}).get("index_matches_registry") is True,
            "strict_compatibility_rows": compatibility["compatibility_row_count"],
        },
        source_reconciliation={
            "file_count": reconciliation["file_count"],
            "reconciled_count": reconciliation["reconciled_count"],
            "pending_count": reconciliation["pending_count"],
            "binding_count": reconciliation["binding_count"],
            "bound_module_count": reconciliation["bound_module_count"],
            "bound_project_evidence_count": reconciliation["bound_project_evidence_count"],
            "receipt_root_digest": reconciliation["receipt_root_digest"],
            "completeness_claim_allowed": reconciliation["pending_count"] == 0,
        },
    )
    audit["family_signal_summary"]["covered"] = len(ids)
    covered_gap_keys = {MODULE_GAP_COVERAGE[module_id] for module_id in ids if module_id in MODULE_GAP_COVERAGE}
    audit["priority_gaps"] = [
        gap for gap in audit["priority_gaps"] if (gap["domain"], gap["family"]) not in covered_gap_keys
    ]
    expansions = (
        "count_verified_clinicaltrials_v2_with_declarative_filters_and_request_provenance",
        "cross_source_citation_preprint_chemical_and_structure_database_evidence",
        "independently_verified_static_raster_chroma_key_and_despill",
        "hash_bound_manuscript_revision_lineage_and_reviewer_commitment_gates",
    )
    for expansion in reversed(expansions):
        if expansion not in audit["implemented_expansion"]:
            audit["implemented_expansion"].insert(5, expansion)
    basis = {key: audit[key] for key in DIGEST_FIELDS}
    audit["reassessment_digest"] = hashlib.sha256(
        json.dumps(basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    path.write_text(json.dumps(audit, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "capability-coverage-audit.json")
    args = parser.parse_args()
    audit = refresh(args.output)
    print(json.dumps({"current_capability_count": audit["current_capability_count"], "pending_source_files": audit["source_reconciliation"]["pending_count"], "reassessment_digest": audit["reassessment_digest"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
