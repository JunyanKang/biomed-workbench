import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import version_is_allowed


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "tool-compatibility-matrix.json"
REPRODUCIBILITY_GUIDE = ROOT / "docs" / "reproducibility.md"


class VersionGuidancePolicyTests(unittest.TestCase):
    def test_numeric_versions_are_tested_baselines_inside_non_pinning_policies(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        numeric_requirements = []
        for module in report["modules"]:
            numeric_requirements.extend(
                requirement
                for requirement in (*module["tools"], *module["dependencies"])
                if requirement["tested_versions"][0][0].isdigit()
            )
        self.assertGreater(len(numeric_requirements), 50)
        for requirement in numeric_requirements:
            with self.subTest(requirement=requirement["name"]):
                self.assertTrue(all(version_is_allowed(version, tuple(requirement["allowed_versions"])) for version in requirement["tested_versions"]))
                self.assertTrue(any(not rule.startswith("==") for rule in requirement["allowed_versions"]))

    def test_public_guidance_separates_actual_versions_baselines_and_execution_policy(self):
        guide = REPRODUCIBILITY_GUIDE.read_text(encoding="utf-8")
        self.assertIn("reproducibility baselines", guide)
        self.assertIn("not installation pins", guide)
        self.assertIn("actual detected versions", guide)
        self.assertIn("guidance and routing remain available", guide)


if __name__ == "__main__":
    unittest.main()
