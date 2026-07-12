import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ProvenanceReleaseTests(unittest.TestCase):
    def test_provenance_is_attribution_only_and_matches_learning_total(self):
        provenance = json.loads((ROOT / "provenance.json").read_text(encoding="utf-8"))
        design = json.loads((ROOT / "reports" / "rewrite-design-summary.json").read_text(encoding="utf-8"))

        self.assertEqual(provenance["learned_file_count"], design["learned_file_count"])
        self.assertEqual(len(provenance["sources"]), 5)
        self.assertEqual(provenance["integration_policy"]["method"], "independent_clean_room_rewrite")
        self.assertFalse(provenance["integration_policy"]["operational_coupling"])
        self.assertFalse(provenance["integration_policy"]["source_code_vendored"])
        self.assertFalse(provenance["integration_policy"]["source_paths_used_at_runtime"])
        self.assertTrue(all(source["reuse"] == "concept_only" for source in provenance["sources"]))

    def test_provenance_contains_no_machine_local_path(self):
        text = (ROOT / "provenance.json").read_text(encoding="utf-8")
        self.assertNotIn("/Users/", text)
        self.assertNotIn("source_root", text)


if __name__ == "__main__":
    unittest.main()
