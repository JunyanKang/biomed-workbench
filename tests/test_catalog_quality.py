import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_LIKE = re.compile(r"\b(import\s+\w+|from\s+\w+\s+import|def\s+[a-z_]\w*\s*\()")


class CatalogQualityTests(unittest.TestCase):
    def test_catalog_descriptions_are_human_readable(self):
        entries = json.loads((ROOT / "tools" / "catalog.json").read_text())["entries"]
        bad = [
            entry["id"]
            for entry in entries
            if entry.get("description", "").strip() in {">-", "|", "\ufeff---"}
            or CODE_LIKE.search(entry.get("description", ""))
        ]

        self.assertEqual(bad, [])

    def test_nature_reference_has_no_yaml_scalar_markers(self):
        text = (ROOT / "references" / "nature_workflows.md").read_text()

        self.assertNotRegex(text, r":\s+(>-|\||\ufeff---)\s*$")


if __name__ == "__main__":
    unittest.main()
