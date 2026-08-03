import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.evidence_scope import evidence_scope_is_current
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
BUILTIN_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin"
ALLOWED_FIELDS = {
    "agent_protocol.mode",
    "output_schema.properties.handoff_type.enum.0",
}


class ExecutionContractEvidenceMigrationTests(unittest.TestCase):
    def test_metadata_only_migrations_are_narrow_complete_and_current(self):
        checked = 0
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        for path in sorted((ROOT / "reports").glob("public-case-*.json")):
            report = json.loads(path.read_text(encoding="utf-8"))
            migration = report.get("execution_contract_migration")
            if migration is None:
                continue
            checked += 1
            module = report["module"]
            module_root = BUILTIN_ROOT / module["id"]
            current_manifest = hashlib.sha256(
                (module_root / "module.json").read_bytes()
            ).hexdigest()
            current_templates = {
                template.name: hashlib.sha256(template.read_bytes()).hexdigest()
                for template in sorted((module_root / "templates").iterdir())
                if template.is_file()
            }

            self.assertEqual(migration["schema_version"], 1)
            self.assertEqual(
                migration["migration_type"],
                "execution-contract-metadata-only",
            )
            self.assertTrue(evidence_scope_is_current(report, registry))
            self.assertEqual(module["manifest_sha256"], migration["current_manifest_sha256"])
            self.assertRegex(current_manifest, r"^[0-9a-f]{64}$")
            self.assertNotEqual(
                migration["prior_manifest_sha256"],
                migration["current_manifest_sha256"],
            )
            self.assertEqual(
                set(migration["changed_fields"]),
                ALLOWED_FIELDS,
            )
            self.assertEqual(migration["template_sha256"], current_templates)
            self.assertTrue(migration["templates_unchanged"])
            self.assertFalse(migration["scientific_outputs_recomputed"])
            self.assertGreaterEqual(len(migration["reason"]), 40)
        self.assertGreaterEqual(checked, 1)


if __name__ == "__main__":
    unittest.main()
