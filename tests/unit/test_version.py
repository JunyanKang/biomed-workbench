import json
import tempfile
import unittest
from pathlib import Path

import biomed_workbench
from biomed_workbench.version import VERSION, read_version


class VersionTests(unittest.TestCase):
    def test_package_version_comes_from_plugin_manifest(self):
        self.assertEqual(biomed_workbench.__version__, VERSION)

    def test_invalid_manifest_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "plugin.json"
            manifest.write_text(json.dumps({"version": "latest"}), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                read_version(manifest)

    def test_codex_cachebuster_is_valid_semver_build_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "plugin.json"
            manifest.write_text(json.dumps({"version": "0.2.0+codex.local-20260712-120000"}), encoding="utf-8")
            self.assertEqual(read_version(manifest), "0.2.0+codex.local-20260712-120000")


if __name__ == "__main__":
    unittest.main()
