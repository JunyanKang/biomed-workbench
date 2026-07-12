import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUMMARY = ROOT / "reports" / "source-assimilation-summary.json"


class AssimilationSummaryReleaseTests(unittest.TestCase):
    def test_original_sources_have_complete_public_evidence(self):
        payload = json.loads(SUMMARY.read_text(encoding="utf-8"))
        sources = {source["source"]: source for source in payload["sources"]}

        self.assertEqual(set(sources), {"primary-a", "primary-b", "primary-c"})
        for source in sources.values():
            self.assertGreater(source["file_count"], 0)
            self.assertGreater(source["total_bytes"], 0)
            self.assertEqual(source["unreadable_count"], 0)
            self.assertRegex(source["root_digest"], r"^[0-9a-f]{64}$")
            self.assertEqual(sum(source["format_counts"].values()), source["file_count"])
            self.assertEqual(sum(source["disposition_counts"].values()), source["file_count"])
            self.assertEqual(sum(source["capability_counts"].values()), source["file_count"])
            self.assertNotIn("unclassified", source["capability_counts"])

        self.assertTrue(
            all(source["capability_counts"].get("codex_native_orchestration", 0) > 0 for source in sources.values())
        )

    def test_public_summary_contains_no_machine_paths_or_file_names(self):
        payload = json.loads(SUMMARY.read_text(encoding="utf-8"))
        serialized = json.dumps(payload)

        self.assertNotIn("/Users/", serialized)
        self.assertNotIn("/private/", serialized)
        self.assertNotIn('"path"', serialized)
        self.assertNotIn('"roots"', serialized)


if __name__ == "__main__":
    unittest.main()
