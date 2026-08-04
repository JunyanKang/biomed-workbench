import json
import shutil
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from tools.validate_module import _validated_output_projection, validate_module


class ServiceModuleFixtureTests(unittest.TestCase):
    def test_receipt_projection_excludes_uncontracted_platform_metadata(self):
        expected = {"result": {"count": 2}}
        linux = {"result": {"count": 2, "runtime": "linux"}, "temporary_path": "/tmp/a"}
        macos = {"result": {"count": 2, "runtime": "macos"}, "temporary_path": "/private/a"}

        self.assertEqual(
            _validated_output_projection(expected, linux),
            _validated_output_projection(expected, macos),
        )

    def test_service_fixture_accepts_json_array_response(self):
        source = BUILTIN_ROOT / "alphafold-structure-evidence"
        report = validate_module(source, require_tests=True, execute_tests=True)
        self.assertTrue(report["valid"], report["errors"])

    def copied_module(self, module_id):
        temporary = tempfile.TemporaryDirectory()
        module_path = Path(temporary.name) / module_id
        shutil.copytree(BUILTIN_ROOT / module_id, module_path)
        self.addCleanup(temporary.cleanup)
        return module_path

    def cases(self, module_path):
        path = module_path / "tests" / "cases.json"
        return path, json.loads(path.read_text(encoding="utf-8"))

    def test_public_database_module_executes_with_declared_https_fixtures(self):
        report = validate_module(BUILTIN_ROOT / "citation-record-resolution")

        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["executed_test_cases"], 1)

    def test_undeclared_service_url_fails_closed_without_network_fallback(self):
        module_path = self.copied_module("citation-record-resolution")
        path, payload = self.cases(module_path)
        payload["cases"][0]["http_fixtures"][0]["url"] += "-wrong"
        path.write_text(json.dumps(payload), encoding="utf-8")

        report = validate_module(module_path)

        self.assertFalse(report["valid"])
        self.assertTrue(any("undeclared URL" in error for error in report["errors"]))

    def test_fixture_schema_rejects_non_https_and_duplicate_urls(self):
        module_path = self.copied_module("preprint-evidence")
        path, payload = self.cases(module_path)
        fixture = payload["cases"][0]["http_fixtures"][0]
        fixture["url"] = fixture["url"].replace("https://", "http://")
        payload["cases"][0]["http_fixtures"].append(dict(fixture))
        path.write_text(json.dumps(payload), encoding="utf-8")

        report = validate_module(module_path)

        self.assertFalse(report["valid"])
        self.assertTrue(any("unique HTTPS targets" in error for error in report["errors"]))

    def test_http_fixtures_are_rejected_for_non_service_modules(self):
        module_path = self.copied_module("source-freshness-audit")
        path, payload = self.cases(module_path)
        payload["cases"][0]["http_fixtures"] = [
            {"url": "https://example.org/fixture", "status": 200, "headers": {}, "json": {}}
        ]
        path.write_text(json.dumps(payload), encoding="utf-8")

        report = validate_module(module_path)

        self.assertFalse(report["valid"])
        self.assertTrue(any("only for service modules" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
