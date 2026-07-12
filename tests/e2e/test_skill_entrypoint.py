import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "biomed-workbench" / "SKILL.md"


class SkillEntrypointE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SKILL.read_text(encoding="utf-8")
        cls.lower = cls.text.lower()

    def test_plugin_exposes_exactly_one_skill(self):
        self.assertEqual(list((ROOT / "skills").glob("*/SKILL.md")), [SKILL])

    def test_entrypoint_drives_complete_research_lifecycle(self):
        for stage in ("frame", "plan", "investigate", "design", "interpret", "deliver", "audit"):
            self.assertIn(stage, self.lower)
        self.assertIn("scientific result", self.lower)
        self.assertIn("limitations", self.lower)

    def test_codex_routes_and_synthesizes_without_another_general_llm(self):
        self.assertIn("codex is the only general-purpose reasoning layer", self.lower)
        self.assertIn("single", self.lower)
        self.assertIn("serial", self.lower)
        self.assertIn("parallel", self.lower)
        self.assertIn("mixed", self.lower)

    def test_commands_use_the_source_neutral_json_contract(self):
        self.assertIn('$WORKBENCH_ROOT/tools/route_task.py', self.text)
        self.assertIn('$WORKBENCH_ROOT/tools/search_tools.py', self.text)
        self.assertRegex(self.text, re.compile(r'run_tool\.py"\s+CAPABILITY_ID\s+--input'))
        self.assertNotIn("-- ARGUMENTS", self.text)

    def test_entrypoint_does_not_claim_compute_infrastructure_ownership(self):
        for term in ("local scientific model", "gpu", "container", "slurm", "runtime-status"):
            self.assertNotIn(term, self.lower)

    def test_operational_skill_contains_no_source_project_bridge(self):
        forbidden = (
            "biomni",
            "openscience",
            "claude science",
            "nature skills",
            "references/internal_workflows",
            "references/tool_catalog.md",
            "non-direct entries",
            "nvidia",
            "ngc",
        )
        for phrase in forbidden:
            self.assertNotIn(phrase, self.lower)


if __name__ == "__main__":
    unittest.main()
