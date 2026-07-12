import json
import re
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
        self.assertIn('$WORKBENCH_ROOT/tools/route_task.py', text)
        self.assertNotIn("From the plugin root", text)

    def test_public_release_has_license_and_consistent_versions(self):
        plugin = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
        catalog = json.loads((ROOT / "tools" / "catalog.json").read_text())

        self.assertTrue((ROOT / "LICENSE").exists())
        self.assertEqual(plugin["license"], "Apache-2.0")
        self.assertEqual(plugin["version"], catalog["version"])

    def test_workflow_map_uses_internal_route_names(self):
        text = (ROOT / "references" / "workflow_map.md").read_text()

        self.assertNotIn("biomed-evidence", text)
        self.assertNotIn("biomed-omics", text)
        for workflow in ("evidence", "omics", "molecular_design", "imaging", "clinical", "wetlab", "publication", "runtime"):
            self.assertIn(f"`{workflow}`", text)

    def test_readme_documents_verified_install_and_test_commands(self):
        text = (ROOT / "README.md").read_text()

        self.assertIn("codex plugin marketplace add JunyanKang/biomed-workbench --ref main", text)
        self.assertIn("codex plugin add biomed-workbench@biomed-workbench", text)
        self.assertIn("python3 -m unittest discover -s tests -v", text)
        self.assertIn("new Codex task", text)


if __name__ == "__main__":
    unittest.main()
