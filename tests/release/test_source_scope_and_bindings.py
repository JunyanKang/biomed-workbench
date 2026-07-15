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
        self.assertEqual(self.scope["changed_count"], 418)
        self.assertEqual(
            self.scope["policy_rules"],
            [
                "compute-infrastructure-explicitly-excluded",
                "materials-science-explicitly-excluded",
                "local-model-inference-explicitly-excluded",
            ],
        )
        self.assertEqual(
            self.scope["transitions"],
            {"redesign_schema->retire": 25, "rewrite_capability->retire": 393},
        )
        self.assertEqual(self.reconciliation["action_counts"]["retire"], 445)

    def test_public_database_sources_are_bound_to_current_evidence(self):
        self.assertEqual(self.bindings["schema_version"], 2)
        self.assertEqual(self.bindings["rule_count"], 16)
        self.assertEqual(self.bindings["matched_receipt_count"], 39)
        self.assertEqual(sum(self.bindings["bindings_by_rule"].values()), 39)
        self.assertEqual(self.bindings["total_binding_count"], self.reconciliation["binding_count"])
        self.assertEqual(self.reconciliation["reconciled_count"], 88099)
        self.assertEqual(self.reconciliation["pending_count"], 1215)

    def test_public_policy_reports_are_path_free(self):
        serialized = SCOPE_REPORT.read_text(encoding="utf-8") + BINDING_REPORT.read_text(encoding="utf-8")

        for marker in ("/Users/", "/private/", '"path"', '"private_path"'):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
