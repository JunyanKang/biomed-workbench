import hashlib
import json
import re
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
RECONCILIATION = ROOT / "reports" / "source-reconciliation-summary.json"
ASSIMILATION = ROOT / "reports" / "source-assimilation-summary.json"
DESIGN = ROOT / "reports" / "rewrite-design-summary.json"
RESEARCH = ROOT / "reports" / "research-engine-verification.json"


class SourceReconciliationEvidenceTests(unittest.TestCase):
    def test_summary_binds_every_private_receipt_to_current_release_evidence(self):
        report = json.loads(RECONCILIATION.read_text(encoding="utf-8"))
        assimilation = json.loads(ASSIMILATION.read_text(encoding="utf-8"))
        design = json.loads(DESIGN.read_text(encoding="utf-8"))
        research = json.loads(RESEARCH.read_text(encoding="utf-8"))
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        file_count = sum(source["file_count"] for source in assimilation["sources"])
        skill_digest = hashlib.sha256((ROOT / "skills" / "biomed-workbench" / "SKILL.md").read_bytes()).hexdigest()

        self.assertTrue(report["passed"])
        self.assertEqual(report["file_count"], file_count)
        self.assertEqual(report["file_count"], design["learned_file_count"])
        self.assertEqual(report["reconciled_count"] + report["pending_count"], report["file_count"])
        self.assertEqual(sum(report["status_counts"].values()), report["file_count"])
        self.assertEqual(sum(report["action_counts"].values()), report["file_count"])
        self.assertEqual(report["action_counts"], design["action_counts"])
        self.assertEqual(report["current_evidence"]["module_count"], len(registry.all()))
        self.assertEqual(report["current_evidence"]["registry_digest"], registry.digest)
        self.assertEqual(report["current_evidence"]["skill_sha256"], skill_digest)
        self.assertEqual(report["current_evidence"]["test_count"], research["test_count"])
        self.assertRegex(report["receipt_root_digest"], r"^[0-9a-f]{64}$")

    def test_pending_receipts_prevent_a_false_completeness_claim(self):
        report = json.loads(RECONCILIATION.read_text(encoding="utf-8"))

        self.assertGreater(report["pending_count"], 0)
        self.assertEqual(report["pending_count"], report["status_counts"]["pending"])
        self.assertTrue(any("prevent" in limitation for limitation in report["limitations"]))

    def test_public_summary_is_path_free_source_neutral_and_secret_free(self):
        serialized = RECONCILIATION.read_text(encoding="utf-8")

        for forbidden in ("/Users/", "/private/", '"path"', '"private_path"', "Biomni", "openscience", "claude"):
            self.assertNotIn(forbidden.lower(), serialized.lower())
        self.assertIsNone(re.search(r"(?:nvapi-|sk-|gh[opsu]_)[A-Za-z0-9_-]{20,}", serialized))


if __name__ == "__main__":
    unittest.main()
