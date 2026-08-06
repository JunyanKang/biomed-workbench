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

    def test_reference_host_and_external_host_responsibilities_are_explicit(self):
        self.assertIn("codex is the primary reference host", self.lower)
        self.assertIn("the host reasoning layer remains responsible", self.lower)
        self.assertIn("reading this skill alone is not equivalent product certification", self.lower)
        self.assertIn("`access: codex_native` operations remain codex-owned", self.lower)
        self.assertIn("single", self.lower)
        self.assertIn("serial", self.lower)
        self.assertIn("parallel", self.lower)
        self.assertIn("mixed", self.lower)

    def test_commands_use_the_source_neutral_json_contract(self):
        self.assertIn('$WORKBENCH_ROOT/tools/workbench" doctor --strict', self.text)
        self.assertIn('$WORKBENCH_ROOT/tools/workbench" plan', self.text)
        self.assertIn('$WORKBENCH_ROOT/tools/workbench" search', self.text)
        self.assertRegex(self.text, re.compile(r'tools/workbench"\s+run\s+CAPABILITY_ID\s+--input'))
        self.assertNotIn("-- ARGUMENTS", self.text)
        self.assertIn("execution_handoff", self.text)
        self.assertIn("access: codex_native", self.text)
        self.assertIn("tool: image_gen", self.text)
        self.assertIn("The handoff is not proof that a bitmap exists", self.text)
        self.assertIn('project prepare-revision --state PROJECT_STATE.json --input REVISION_REQUEST.json', self.text)
        self.assertIn('project migrate-state-v1 --legacy-state LEGACY_STATE.json', self.text)
        self.assertIn('"target_input_bindings": {}', self.text)
        self.assertIn('"migration_status": "awaiting-scientific-dependency-recovery"', self.text)

    def test_entrypoint_does_not_claim_compute_infrastructure_ownership(self):
        for term in ("local scientific reasoning model", "runtime-status"):
            self.assertNotIn(term, self.lower)
        self.assertIn("do not manage dependency environments", self.lower)
        self.assertIn("model-hosting infrastructure", self.lower)

    def test_missing_scientific_dependency_triggers_bounded_recovery_before_blocking(self):
        self.assertIn("a missing package is not evidence that the scientific capability can be skipped", self.lower)
        self.assertIn("project-local or temporary environment", self.lower)
        self.assertIn("compatibility and representative execution checks", self.lower)
        self.assertIn("templates must never install packages while analyzing data", self.lower)
        self.assertIn("only block the branch after installation or compatible-environment discovery has failed", self.lower)

    def test_operational_skill_contains_no_source_project_bridge(self):
        forbidden = (
            "bio" + "mni",
            "open" + "science",
            "clau" + "de science",
            "nature" + " skills",
            "references/internal_workflows",
            "references/tool_catalog.md",
            "non-direct entries",
            "nvi" + "dia",
            "ng" + "c",
        )
        for phrase in forbidden:
            self.assertNotIn(phrase, self.lower)


if __name__ == "__main__":
    unittest.main()
