import re
import unittest
from pathlib import Path

from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
BUILTIN_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin"
CAPABILITY_MAP = ROOT / "docs" / "capabilities" / "README.md"
CAPABILITY_MAP_ZH = ROOT / "docs" / "capabilities" / "README.zh-CN.md"


class PublicCapabilityDocumentationTests(unittest.TestCase):
    def assert_documented_count_matches_registry(self, path: Path, pattern: str):
        text = path.read_text(encoding="utf-8")
        style_neutral_text = re.sub(r"[*_`]", "", text)
        match = re.search(pattern, style_neutral_text)

        self.assertIsNotNone(match, f"module count is missing from {path.relative_to(ROOT)}")
        self.assertEqual(int(match.group(1)), len(ModuleRegistry.discover(BUILTIN_ROOT).all()))

    def test_english_capability_map_module_count_matches_dynamic_registry(self):
        self.assert_documented_count_matches_registry(
            CAPABILITY_MAP,
            r"The registry currently contains\s+(\d+)\s+independently discoverable modules\.",
        )

    def test_chinese_capability_map_module_count_matches_dynamic_registry(self):
        self.assert_documented_count_matches_registry(
            CAPABILITY_MAP_ZH,
            r"当前注册表包含\s*(\d+)\s*个可独立识别的模块。",
        )


if __name__ == "__main__":
    unittest.main()
