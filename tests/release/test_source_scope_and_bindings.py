import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCOPE_REPORT = ROOT / "reports" / "source-scope-policy.json"
BINDING_REPORT = ROOT / "reports" / "source-capability-bindings.json"
RECONCILIATION_REPORT = ROOT / "reports" / "source-reconciliation-summary.json"


class SourceScopeAndBindingEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scope = json.loads(SCOPE_REPORT.read_text(encoding="utf-8"))
        cls.bindings = json.loads(BINDING_REPORT.read_text(encoding="utf-8"))
        cls.reconciliation = json.loads(RECONCILIATION_REPORT.read_text(encoding="utf-8"))

    def test_compute_infrastructure_policy_is_explicit_and_complete(self):
        self.assertEqual(self.scope["row_count"], self.reconciliation["file_count"])
        self.assertEqual(self.scope["changed_count"], 414)
        self.assertEqual(self.scope["policy_rules"], ["compute-infrastructure-explicitly-excluded"])
        self.assertEqual(
            self.scope["transitions"],
            {"redesign_schema->retire": 25, "rewrite_capability->retire": 389},
        )
        self.assertEqual(self.reconciliation["action_counts"]["retire"], 441)

    def test_clinical_trial_sources_are_bound_to_current_evidence(self):
        self.assertEqual(self.bindings["rule_count"], 2)
        self.assertEqual(self.bindings["added_binding_count"], 17)
        self.assertEqual(self.bindings["matched_receipt_count"], 17)
        self.assertEqual(self.bindings["added_by_rule"], self.bindings["matches_by_rule"])
        self.assertEqual(self.bindings["total_binding_count"], self.reconciliation["binding_count"])
        self.assertEqual(self.reconciliation["reconciled_count"], 88073)
        self.assertEqual(self.reconciliation["pending_count"], 1241)

    def test_public_policy_reports_are_path_free(self):
        serialized = SCOPE_REPORT.read_text(encoding="utf-8") + BINDING_REPORT.read_text(encoding="utf-8")

        for marker in ("/Users/", "/private/", '"path"', '"private_path"'):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
