import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SYNTHESIS = ROOT / "reports" / "source-learning-synthesis.json"
ASSIMILATION = ROOT / "reports" / "source-assimilation-summary.json"


class LearningSynthesisReleaseTests(unittest.TestCase):
    def test_synthesis_accounts_for_every_assimilated_file(self):
        synthesis = json.loads(SYNTHESIS.read_text(encoding="utf-8"))
        assimilation = json.loads(ASSIMILATION.read_text(encoding="utf-8"))
        expected = sum(source["file_count"] for source in assimilation["sources"])

        self.assertEqual(synthesis["learned_file_count"], expected)
        self.assertEqual(sum(synthesis["source_counts"].values()), expected)
        self.assertEqual(sum(cluster["file_count"] for cluster in synthesis["clusters"].values()), expected)

    def test_synthesis_contains_architecture_signals_without_private_paths(self):
        payload = json.loads(SYNTHESIS.read_text(encoding="utf-8"))
        serialized = SYNTHESIS.read_text(encoding="utf-8")

        def keys(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    yield key
                    yield from keys(item)
            elif isinstance(value, list):
                for item in value:
                    yield from keys(item)

        for cluster in ("evidence_discovery", "omics", "molecular_design", "structural_biology", "publication", "runtime_orchestration"):
            self.assertGreater(payload["clusters"][cluster]["file_count"], 0)
            self.assertTrue(payload["clusters"][cluster]["design_implications"])
        self.assertNotIn("/Users/", serialized)
        self.assertNotIn("path", set(keys(payload)))


if __name__ == "__main__":
    unittest.main()
