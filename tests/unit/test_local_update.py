import json
import tempfile
import unittest
from pathlib import Path

from tools.prepare_local_update import cachebusted_version, update_manifest


class LocalUpdateTests(unittest.TestCase):
    def test_cachebuster_replaces_existing_build_metadata(self):
        self.assertEqual(
            cachebusted_version("0.2.0-dev+codex.old", "local-20260712-120000"),
            "0.2.0-dev+codex.local-20260712-120000",
        )

    def test_manifest_update_is_repeatable_without_suffix_accumulation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / ".codex-plugin" / "plugin.json"
            manifest.parent.mkdir()
            manifest.write_text(json.dumps({"version": "0.2.0-dev+codex.first"}), encoding="utf-8")

            first = update_manifest(root, "second")
            second = update_manifest(root, "third")

            self.assertEqual(first, "0.2.0-dev+codex.second")
            self.assertEqual(second, "0.2.0-dev+codex.third")
            self.assertEqual(json.loads(manifest.read_text())["version"], second)


if __name__ == "__main__":
    unittest.main()
