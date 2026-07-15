import json
import unittest
from pathlib import Path

from tools.build_rewrite_design_summary import build_summary


ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "reports" / "rewrite-design-summary.json"
ASSIMILATION = ROOT / "reports" / "source-assimilation-summary.json"


class RewriteDesignSummaryTests(unittest.TestCase):
    def test_every_learned_file_has_exactly_one_design_decision(self):
        design = json.loads(DESIGN.read_text(encoding="utf-8"))
        assimilation = json.loads(ASSIMILATION.read_text(encoding="utf-8"))
        assimilated_count = sum(source["file_count"] for source in assimilation["sources"])

        self.assertEqual(design["learned_file_count"], assimilated_count)
        self.assertEqual(sum(design["source_counts"].values()), assimilated_count)
        self.assertEqual(sum(design["action_counts"].values()), assimilated_count)
        self.assertEqual(sum(design["reuse_mode_counts"].values()), assimilated_count)
        self.assertRegex(design["design_digest"], r"^[0-9a-f]{64}$")
        private_ledger = ROOT / ".source-audit" / "rewrite-ledger.jsonl"
        if private_ledger.is_file():
            self.assertEqual(design, build_summary(private_ledger))

    def test_reuse_policy_is_clean_room_only(self):
        design = json.loads(DESIGN.read_text(encoding="utf-8"))
        serialized = DESIGN.read_text(encoding="utf-8")

        self.assertEqual(set(design["reuse_mode_counts"]), {"concept_only", "attribution_only", "none"})
        self.assertGreater(design["action_counts"]["rewrite_capability"], 0)
        self.assertGreater(design["action_counts"]["rewrite_workflow"], 0)
        self.assertNotIn("/Users/", serialized)
        self.assertNotIn('"path"', serialized)


if __name__ == "__main__":
    unittest.main()
