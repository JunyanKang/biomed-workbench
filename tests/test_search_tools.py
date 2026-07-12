import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def search(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / "search_tools.py"), *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


class SearchToolTests(unittest.TestCase):
    def test_review_and_citation_search_uses_router_intent_priority(self):
        output = search("--workflow", "publication", "review", "citation", "--limit", "5")

        reviewer = output.index("publication_reviewer")
        verifier = output.index("publication_ref_verifier")
        citation = output.index("publication_citation")
        self.assertLess(reviewer, verifier)
        self.assertLess(verifier, citation)

    def test_search_output_hides_source_code_as_descriptions(self):
        output = search("--workflow", "imaging", "morphology", "--limit", "5")

        self.assertNotIn("import argparse", output)
        self.assertNotRegex(output, r"def [a-z_]+\(")


if __name__ == "__main__":
    unittest.main()
