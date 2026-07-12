import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "codex-native-handoff-verification.json"


class CodexNativeHandoffEvidenceTests(unittest.TestCase):
    def test_image_handoff_is_bound_to_current_module_skill_and_compatibility_evidence(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        manifest = registry.get("scientific-illustration-generation")

        self.assertTrue(report["passed"])
        self.assertEqual(report["evidence_id"], "codex-native-image-generation-handoff-v1")
        self.assertEqual(report["module"]["version"], manifest.version)
        self.assertEqual(report["module"]["manifest_sha256"], hashlib.sha256((BUILTIN_ROOT / manifest.id / "module.json").read_bytes()).hexdigest())
        self.assertEqual(report["module"]["access"], "codex_native")
        self.assertEqual(report["module"]["credentials"], [])
        self.assertEqual(report["skill"]["sha256"], hashlib.sha256((ROOT / "skills" / "biomed-workbench" / "SKILL.md").read_bytes()).hexdigest())
        self.assertTrue(report["handoff"]["deterministic_handoff_executed"])
        self.assertFalse(report["handoff"]["native_bitmap_invocation_tested"])
        self.assertFalse(report["handoff"]["provider_sdk_or_cli"])
        self.assertFalse(report["handoff"]["provider_credential_requested"])
        self.assertEqual(report["source_behavior_disposition"]["provider_auth_model_endpoint_and_retry_client"], "retired-codex-managed")

    def test_handoff_evidence_is_path_source_and_secret_free(self):
        serialized = REPORT.read_text(encoding="utf-8")

        for marker in ("/Users/", "/private/", "/Volumes/", "file://", "OPENAI_API_KEY", "nvapi-", "bf339", "image_gen.py"):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
