import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class CodexPackagingReleaseTests(unittest.TestCase):
    def test_manifest_uses_codex_interface_conventions(self):
        plugin = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        interface = plugin["interface"]

        self.assertEqual(set(interface["capabilities"]), {"Interactive", "Read"})
        self.assertLessEqual(len(interface["defaultPrompt"]), 3)
        self.assertTrue(all(len(prompt) <= 128 for prompt in interface["defaultPrompt"]))
        for field in ("websiteURL", "privacyPolicyURL", "termsOfServiceURL"):
            self.assertTrue(interface[field].startswith("https://"))

    def test_skill_has_codex_ui_metadata_and_implicit_invocation(self):
        metadata = (ROOT / "skills" / "biomed-workbench" / "agents" / "openai.yaml").read_text(encoding="utf-8")

        self.assertIn('display_name: "Biomed Workbench"', metadata)
        self.assertIn("$biomed-workbench", metadata)
        self.assertNotIn("allow_implicit_invocation: false", metadata)

    def test_marketplace_identity_and_category_match_plugin(self):
        plugin = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        marketplace = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
        entry = marketplace["plugins"][0]

        self.assertEqual(marketplace["name"], "biomed-workbench")
        self.assertEqual(entry["name"], plugin["name"])
        self.assertEqual(entry["category"], plugin["interface"]["category"])
        self.assertEqual(entry["policy"], {"installation": "AVAILABLE", "authentication": "ON_INSTALL"})


if __name__ == "__main__":
    unittest.main()
