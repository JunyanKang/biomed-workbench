import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "legacy-script-retirement.json"


class LegacyRetirementReleaseTests(unittest.TestCase):
    def test_every_legacy_script_has_a_verified_final_disposition(self):
        payload = json.loads(REPORT.read_text(encoding="utf-8"))
        total = payload["legacy_script_count"]

        self.assertEqual(total, 144)
        self.assertEqual(sum(payload["source_match"].values()), total)
        self.assertEqual(payload["source_match"]["unmatched"], 0)
        self.assertEqual(sum(payload["learned_source_counts"].values()), total)
        self.assertEqual(sum(payload["final_disposition"].values()), total)
        self.assertEqual(sum(payload["design_action_counts"].values()), total)
        self.assertEqual(sum(payload["rewritten_target_counts"].values()), payload["final_disposition"]["mapped_to_rewritten_architecture"])
        self.assertRegex(payload["content_digest"], r"^[0-9a-f]{64}$")

    def test_retirement_report_contains_no_source_paths(self):
        text = REPORT.read_text(encoding="utf-8")
        self.assertNotIn("/Users/", text)
        self.assertNotIn('"path"', text)


if __name__ == "__main__":
    unittest.main()
