import re
import unittest
from pathlib import Path

from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
BUILTIN_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin"
CAPABILITY_MAP = ROOT / "docs" / "capabilities" / "README.md"


class PublicCapabilityDocumentationTests(unittest.TestCase):
    def test_capability_map_module_count_matches_dynamic_registry(self):
        text = CAPABILITY_MAP.read_text(encoding="utf-8")
        match = re.search(
            r"The registry currently contains \*\*(\d+)\*\* independently discoverable modules\.",
            text,
        )

        self.assertIsNotNone(match)
        self.assertEqual(int(match.group(1)), len(ModuleRegistry.discover(BUILTIN_ROOT).all()))


if __name__ == "__main__":
    unittest.main()
