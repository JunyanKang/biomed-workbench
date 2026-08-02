import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.evidence_scope import evidence_scope_is_current
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-ttseq-gse75792.json"


class PublicTTSeqCaseTests(unittest.TestCase):
    def test_case_is_current_observed_and_reloaded(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        implementation = ROOT / report["implementation"]["path"]
        registry = ModuleRegistry.discover(BUILTIN_ROOT)

        self.assertTrue(report["passed"])
        self.assertEqual(report["case_type"], "public-data-end-to-end")
        self.assertEqual(report["module"]["id"], "bulk-nascent-transcription")
        self.assertTrue(evidence_scope_is_current(report, registry))
        self.assertEqual(
            hashlib.sha256(implementation.read_bytes()).hexdigest(),
            report["implementation"]["sha256"],
        )
        self.assertTrue(report["execution"]["external_workflow_executed"])
        self.assertTrue(report["execution"]["outputs_reloaded"])
        self.assertEqual(report["execution"]["features"], 21874)
        self.assertEqual(report["outputs"]["feature_estimates"]["rows"], 43748)
        self.assertEqual(sum(report["status_counts"].values()), 43748)
        self.assertEqual(report["execution"]["analysis_mode"], "relative-profile")


if __name__ == "__main__":
    unittest.main()
