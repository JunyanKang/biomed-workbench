import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "local-update-verification.json"
IMPLEMENTATION = ROOT / "tools" / "prepare_local_update.py"


class LocalUpdateEvidenceTests(unittest.TestCase):
    def test_report_binds_current_implementation_and_behavior(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))

        self.assertTrue(report["passed"])
        self.assertEqual(report["evidence_id"], "codex-local-update-cachebuster-v1")
        self.assertEqual(report["implementation"]["sha256"], hashlib.sha256(IMPLEMENTATION.read_bytes()).hexdigest())
        self.assertTrue(all(report["verified_behaviors"].values()))
        self.assertFalse(report["scientific_runtime_capability"])

    def test_report_is_path_and_secret_free(self):
        text = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "/Volumes/", "file://", "API_KEY", "nvapi-"):
            self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
