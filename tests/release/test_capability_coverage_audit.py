import json
import hashlib
import unittest
from pathlib import Path

from biomed_workbench.catalog import all_capabilities


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "reports" / "capability-coverage-audit.json"
ASSIMILATION = ROOT / "reports" / "source-assimilation-summary.json"
RECONCILIATION = ROOT / "reports" / "source-reconciliation-summary.json"


class CapabilityCoverageAuditTests(unittest.TestCase):
    def test_audit_is_bound_to_learned_sources_and_current_registry(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        assimilation = json.loads(ASSIMILATION.read_text(encoding="utf-8"))
        reconciliation = json.loads(RECONCILIATION.read_text(encoding="utf-8"))
        learned = sum(source["file_count"] for source in assimilation["sources"])
        current_ids = sorted(capability.id for capability in all_capabilities())

        self.assertEqual(audit["learned_file_count"], learned)
        self.assertEqual(audit["current_capability_count"], len(current_ids))
        self.assertEqual(audit["current_capability_ids"], current_ids)
        self.assertEqual(
            audit["source_reconciliation"],
            {
                "file_count": reconciliation["file_count"],
                "reconciled_count": reconciliation["reconciled_count"],
                "pending_count": reconciliation["pending_count"],
                "binding_count": reconciliation["binding_count"],
                "bound_module_count": reconciliation["bound_module_count"],
                "receipt_root_digest": reconciliation["receipt_root_digest"],
                "completeness_claim_allowed": False,
            },
        )
        self.assertRegex(audit["reassessment_digest"], r"^[0-9a-f]{64}$")
        digest_basis = {
            key: audit[key]
            for key in (
                "learned_file_count",
                "current_capability_ids",
                "source_file_counts",
                "source_reconciliation",
                "implemented_expansion",
                "priority_gaps",
                "product_exclusions",
            )
        }
        digest = hashlib.sha256(json.dumps(digest_basis, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(audit["reassessment_digest"], digest)

    def test_audit_does_not_overstate_coverage(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))

        self.assertEqual(audit["verdict"]["breadth"], "source-union-stronger")
        self.assertEqual(audit["verdict"]["architecture"], "workbench-stronger")
        self.assertFalse(audit["verdict"]["overall_superiority_proven"])
        self.assertGreater(len(audit["priority_gaps"]), 10)
        self.assertIn("compute_infrastructure", audit["product_exclusions"])
        self.assertIn("Signals may overlap", audit["measurement_note"])

    def test_public_audit_is_source_neutral_and_path_free(self):
        serialized = AUDIT.read_text(encoding="utf-8")

        self.assertNotIn("/Users/", serialized)
        self.assertNotIn("Biomni", serialized)
        self.assertNotIn("openscience", serialized)
        self.assertNotIn("claude", serialized.lower())


if __name__ == "__main__":
    unittest.main()
