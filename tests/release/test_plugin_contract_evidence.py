import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "plugin-contract-verification.json"


class PluginContractEvidenceTests(unittest.TestCase):
    def test_official_validation_is_bound_to_current_manifest_skill_and_registry(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        snapshot = ROOT / "reports" / "module-registry-verification.json"

        self.assertTrue(report["passed"])
        self.assertEqual(report["evidence_id"], "codex-plugin-manifest-contract-v1")
        self.assertEqual(report["evidence_type"], "codex-plugin-contract")
        self.assertEqual(report["plugin"]["manifest_sha256"], hashlib.sha256((ROOT / ".codex-plugin" / "plugin.json").read_bytes()).hexdigest())
        self.assertEqual(report["plugin"]["skill_sha256"], hashlib.sha256((ROOT / "skills" / "biomed-workbench" / "SKILL.md").read_bytes()).hexdigest())
        self.assertTrue(report["plugin"]["single_skill_entry"])
        self.assertTrue(report["official_validation"]["plugin_validator"]["passed"])
        self.assertTrue(report["official_validation"]["skill_validator"]["passed"])
        self.assertEqual(report["isolated_registry_snapshot"]["report_sha256"], hashlib.sha256(snapshot.read_bytes()).hexdigest())
        self.assertEqual(report["isolated_registry_snapshot"]["module_count"], len(registry.all()))
        self.assertEqual(report["isolated_registry_snapshot"]["registry_digest"], registry.digest)
        self.assertTrue(report["isolated_registry_snapshot"]["source_and_snapshot_indexes_match"])

    def test_public_contract_evidence_is_path_and_secret_free(self):
        serialized = REPORT.read_text(encoding="utf-8")

        for marker in ("/Users/", "/private/", "/Volumes/", "file://", "API_KEY", "nvapi-", "bf339"):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
