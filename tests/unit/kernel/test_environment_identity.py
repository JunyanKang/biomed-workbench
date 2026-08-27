import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.kernel.environment_identity import (
    capture_analysis_environment,
    environment_reuse_status,
    persist_analysis_environment_record,
    validate_analysis_environment,
)


class AnalysisEnvironmentIdentityTests(unittest.TestCase):
    def test_capture_is_secret_free_valid_and_persisted_by_content_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "environment.yml").write_text("name: test\n", encoding="utf-8")
            value = capture_analysis_environment(project_root=root)
            normalized = validate_analysis_environment(value)
            path = persist_analysis_environment_record(root, value)

            self.assertEqual(normalized["lock_files"][0]["path"], "environment.yml")
            self.assertFalse(normalized["location"].startswith("/"))
            self.assertEqual(path.name, f"{normalized['content_digest']}.json")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), normalized)
            self.assertEqual(persist_analysis_environment_record(root, value), path)

    def test_reuse_classifies_exact_and_drifted_content(self):
        current = capture_analysis_environment()
        drifted = capture_analysis_environment(container_image_digest="b" * 64)

        self.assertEqual(environment_reuse_status(current, ()), "first-observed")
        self.assertEqual(environment_reuse_status(current, (current,)), "reused-exact")
        self.assertEqual(environment_reuse_status(drifted, (current,)), "drift-blocked")

    def test_digest_tampering_is_rejected(self):
        value = capture_analysis_environment()
        value["package_inventory_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "content digest"):
            validate_analysis_environment(value)


if __name__ == "__main__":
    unittest.main()
