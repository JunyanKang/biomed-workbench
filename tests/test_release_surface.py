import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseSurfaceTests(unittest.TestCase):
    def test_skill_description_is_trigger_only(self):
        text = (ROOT / "skills" / "biomed-workbench" / "SKILL.md").read_text()
        frontmatter = text.split("---", 2)[1]
        description = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE).group(1)

        self.assertTrue(description.startswith("Use when"))
        self.assertNotIn("Routes", description)
        self.assertLess(len(description), 500)

    def test_skill_resolves_tools_from_its_own_plugin_root(self):
        text = (ROOT / "skills" / "biomed-workbench" / "SKILL.md").read_text()

        self.assertIn("WORKBENCH_ROOT", text)
        self.assertIn('$WORKBENCH_ROOT/tools/workbench" doctor --strict', text)
        self.assertIn('$WORKBENCH_ROOT/tools/workbench" route', text)
        self.assertNotIn("From the plugin root", text)

    def test_public_release_has_license_and_consistent_versions(self):
        plugin = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
        catalog = json.loads((ROOT / "tools" / "catalog.json").read_text())

        self.assertTrue((ROOT / "LICENSE").exists())
        self.assertEqual(plugin["license"], "Apache-2.0")
        self.assertEqual(plugin["version"], catalog["version"])

    def test_top_level_help_discovers_the_complete_project_command_surface(self):
        completed = subprocess.run(
            [str(ROOT / "tools" / "workbench"), "help"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        for command in (
            "prepare-revision",
            "migrate-state-v1",
            "upgrade-state-migration-1-1",
        ):
            self.assertIn(command, completed.stdout)
        self.assertIn("tools/workbench project --help", completed.stdout)

        project_help = subprocess.run(
            [str(ROOT / "tools" / "workbench"), "project", "--help"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        for command in (
            "prepare-revision",
            "migrate-state-v1",
            "upgrade-state-migration-1-1",
        ):
            self.assertIn(command, project_help.stdout)

    def test_independent_modules_replace_workflow_reference_bridges(self):
        module_files = sorted((ROOT / "biomed_workbench" / "modules" / "builtin").glob("*/module.json"))
        catalog = json.loads((ROOT / "tools" / "catalog.json").read_text())

        self.assertEqual(len(module_files), catalog["entry_count"])
        self.assertFalse((ROOT / "biomed_workbench" / "capability_specs").exists())
        self.assertFalse((ROOT / "tools" / "add_capability.py").exists())
        self.assertFalse((ROOT / "references").exists())

    def test_public_readme_keeps_user_install_separate_from_maintainer_commands(self):
        readme = (ROOT / "README.md").read_text()
        english_readme = (ROOT / "README.en.md").read_text()
        development = (ROOT / "docs" / "development.md").read_text()

        repository_link = "[JunyanKang/biomed-workbench](https://github.com/JunyanKang/biomed-workbench)"
        self.assertIn(f"安装 {repository_link} 这个仓库的当前发布版本", readme)
        self.assertIn(f"Install the current release of {repository_link}", english_readme)
        self.assertIn("其他智能体不要照搬上面的 Codex 插件安装提示", readme)
        self.assertIn("保留但不加载", readme)
        self.assertIn("should not copy the Codex plugin-install request verbatim", english_readme)
        self.assertIn("present but unloaded", english_readme)
        self.assertNotIn("codex plugin marketplace add", readme)
        self.assertNotIn("codex plugin add", readme)
        self.assertIn("开启一个新的研究任务", readme)
        self.assertIn("open a new task", english_readme)
        self.assertNotIn("python3 ", readme)
        self.assertIn("python3 -m unittest discover -s tests -v", development)

    def test_public_documents_do_not_expose_journal_catalog_maintenance_metadata(self):
        public_paths = [ROOT / "README.md", ROOT / "README.en.md"]
        public_paths.extend(sorted((ROOT / "docs").rglob("*.md")))
        public_paths.append(ROOT / "skills" / "biomed-workbench" / "SKILL.md")
        forbidden = (
            "catalog_lifecycle",
            "draft/released",
            "draft and released",
            "数据采用明确的来源层级",
            "actual metric source",
            "每一行都显示实际采用的指标来源",
            "bibliometric fields",
            "期刊指标",
            "catalogue currently covers",
            "catalog currently covers",
            "规范库当前覆盖",
            "期刊规范库",
        )
        forbidden_patterns = (
            r"\b\d+\s+(?:biomedical|life[- ]science)\s+journals?\b",
            r"\d+\s*本[\u4e00-\u9fff]{0,12}期刊",
            r"\bjournal[- ]standards catalog(?:ue)?\b",
            r"\bjournal catalog(?:ue)?\b",
        )

        for path in public_paths:
            text = path.read_text(encoding="utf-8").lower()
            for phrase in forbidden:
                self.assertNotIn(phrase.lower(), text, f"{phrase!r} leaked into {path.relative_to(ROOT)}")
            for pattern in forbidden_patterns:
                self.assertIsNone(
                    re.search(pattern, text, flags=re.IGNORECASE),
                    f"journal catalogue metadata matching {pattern!r} leaked into {path.relative_to(ROOT)}",
                )

        skill_text = (ROOT / "skills" / "biomed-workbench" / "SKILL.md").read_text(encoding="utf-8").lower()
        for phrase in ("versioned catalog", "catalog version"):
            self.assertNotIn(phrase, skill_text)


if __name__ == "__main__":
    unittest.main()
