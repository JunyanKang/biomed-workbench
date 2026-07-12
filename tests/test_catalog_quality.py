import json
import re
import unittest
from pathlib import Path

from biomed_workbench.catalog import all_capabilities, resolve_entrypoint


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

    def test_generated_catalog_matches_resolvable_registry(self):
        payload = json.loads((ROOT / "tools" / "catalog.json").read_text())
        capabilities = all_capabilities()
        self.assertEqual(payload["entry_count"], len(capabilities))
        self.assertEqual([row["id"] for row in payload["entries"]], [item.id for item in capabilities])
        for capability in capabilities:
            self.assertTrue(callable(resolve_entrypoint(capability)))
        forbidden = {"source", "source_path", "run_policy", "adapter"}
        self.assertTrue(all(not (forbidden & set(row)) for row in payload["entries"]))


if __name__ == "__main__":
    unittest.main()
