import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "ci-quality-verification.json"
WORKFLOW = ROOT / ".github" / "workflows" / "quality.yml"
REQUIREMENTS = ROOT / "requirements-ci.txt"


class CIQualityEvidenceTests(unittest.TestCase):
    def test_report_binds_workflow_requirements_and_all_quality_gates(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))

        self.assertTrue(report["passed"])
        self.assertEqual(report["evidence_id"], "github-quality-and-secret-gates-v1")
        self.assertEqual(report["workflow"]["sha256"], hashlib.sha256(WORKFLOW.read_bytes()).hexdigest())
        self.assertEqual(report["requirements"]["sha256"], hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest())
        self.assertTrue(all(report["quality_gates"].values()))
        self.assertGreaterEqual(len(report["excluded_claims"]), 3)

    def test_report_is_path_and_secret_free(self):
        text = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "/Volumes/", "file://", "API_KEY", "ACCESS_TOKEN="):
            self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
