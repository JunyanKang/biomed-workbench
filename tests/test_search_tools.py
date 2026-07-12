import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def search(*args):
    result = subprocess.run([sys.executable, "tools/search_tools.py", *args], cwd=ROOT, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


class SearchToolTests(unittest.TestCase):
    def test_publication_search_uses_new_registry(self):
        payload = search("--workflow", "publication", "citation", "--limit", "3")
        ids = [item["id"] for item in payload["capabilities"]]
        self.assertEqual(ids[0], "citation-audit")

    def test_exact_capability_has_only_source_neutral_contract_fields(self):
        payload = search("--id", "gene-evidence")
        row = payload["capabilities"][0]
        self.assertEqual(row["entrypoint"], "biomed_workbench.capabilities.evidence:gene_evidence")
        self.assertNotIn("source", row)
        self.assertNotIn("source_path", row)
        self.assertNotIn("run_policy", row)


if __name__ == "__main__":
    unittest.main()
