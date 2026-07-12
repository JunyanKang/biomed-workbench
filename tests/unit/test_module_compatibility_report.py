import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.registry import ModuleRegistry
from tests.unit.test_module_compatibility import external_manifest_payload
from tests.unit.test_module_registry import FIXTURE_ROOT, write_manifest
from tools.build_tool_compatibility_matrix import build_compatibility_report


class ModuleCompatibilityReportTests(unittest.TestCase):
    def test_standard_library_module_has_explicit_no_external_tool_evidence(self):
        report = build_compatibility_report(ModuleRegistry.discover(FIXTURE_ROOT))

        self.assertEqual(report["module_count"], 1)
        self.assertEqual(report["compatibility_complete"], 1)
        self.assertFalse(report["modules"][0]["external_tool_required"])
        self.assertEqual(report["modules"][0]["dependencies"][0]["tested_versions"], ["3.14.3"])

    def test_external_tool_versions_sources_formats_and_rows_are_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_manifest(root, external_manifest_payload())
            report = build_compatibility_report(ModuleRegistry.discover(root))
        module = report["modules"][0]

        self.assertTrue(module["external_tool_required"])
        self.assertEqual(module["tools"][0]["name"], "scanpy")
        self.assertEqual(module["tools"][0]["tested_versions"], ["1.11.5"])
        self.assertTrue(module["tools"][0]["version_source"].startswith("https://"))
        self.assertEqual(module["input_formats"][0]["formats"][0]["versions"], ["0.11"])
        self.assertEqual(module["compatibility_rows"], ["scanpy-1.11.5-h5ad-0.11"])

    def test_report_is_path_and_credential_free(self):
        report = build_compatibility_report(ModuleRegistry.discover(FIXTURE_ROOT))
        serialized = json.dumps(report)

        self.assertNotIn("/Users/", serialized)
        self.assertNotIn("NCBI_API_KEY", serialized)
        self.assertNotIn('"entrypoint":', serialized)


if __name__ == "__main__":
    unittest.main()
