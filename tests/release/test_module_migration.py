import json
import unittest
from pathlib import Path

from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
BUILTIN_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin"
LEGACY_CATALOG = ROOT / "tools" / "catalog.json"
MIGRATION_REPORT = ROOT / "reports" / "module-registry-migration.json"
COMPATIBILITY_REPORT = ROOT / "reports" / "tool-compatibility-matrix.json"


class ModuleMigrationReleaseTests(unittest.TestCase):
    def test_every_legacy_capability_has_one_behavior_preserving_module(self):
        catalog = {row["id"]: row for row in json.loads(LEGACY_CATALOG.read_text(encoding="utf-8"))["entries"]}
        migration = json.loads(MIGRATION_REPORT.read_text(encoding="utf-8"))
        expanded = set(migration["expanded_module_ids"])
        legacy = {module_id: row for module_id, row in catalog.items() if module_id not in expanded}
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        current = {module.id: module for module in registry.all()}

        self.assertEqual(len(legacy), 48)
        self.assertEqual(set(current), set(catalog))
        self.assertEqual(set(current) - set(legacy), expanded)
        for module_id, row in legacy.items():
            module = current[module_id]
            self.assertEqual(module.entrypoint, row["entrypoint"])
            self.assertEqual(module.input_schema, row["input_schema"])
            self.assertEqual(module.access, row["access"])
            self.assertEqual(module.mutability, row["mutability"])
            self.assertEqual(module.execution.kind, row["kind"])

    def test_all_modules_have_complete_distinct_scientific_metadata(self):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        questions = set()
        gates = set()
        for module in registry.all():
            self.assertTrue(module.intents)
            self.assertTrue(module.questions)
            self.assertTrue(module.preconditions)
            self.assertTrue(module.assumptions)
            self.assertTrue(module.quality_gates)
            self.assertTrue(module.limitations)
            self.assertTrue(module.evidence_effects)
            self.assertTrue(module.input_artifacts)
            self.assertTrue(module.output_artifacts)
            self.assertTrue(module.compatibility_matrix)
            self.assertEqual(module.output_schema["additionalProperties"], False)
            questions.update(module.questions)
            gates.update(gate.id for gate in module.quality_gates)

        self.assertGreaterEqual(len(questions), 48)
        self.assertGreaterEqual(len(gates), 40)

    def test_migration_and_compatibility_reports_prove_parity(self):
        migration = json.loads(MIGRATION_REPORT.read_text(encoding="utf-8"))
        compatibility = json.loads(COMPATIBILITY_REPORT.read_text(encoding="utf-8"))

        self.assertEqual(migration["legacy_capability_count"], 48)
        self.assertEqual(migration["module_count"], 50)
        self.assertEqual(migration["entrypoint_parity_count"], 48)
        self.assertEqual(migration["input_schema_parity_count"], 48)
        self.assertEqual(migration["scientific_contract_complete_count"], 50)
        self.assertEqual(migration["compatibility_contract_complete_count"], 50)
        self.assertEqual(compatibility["module_count"], 50)
        self.assertEqual(compatibility["compatibility_complete"], 50)
        self.assertEqual(migration["registry_digest"], compatibility["registry_digest"])

    def test_public_reports_and_manifests_have_no_machine_or_source_paths(self):
        texts = [MIGRATION_REPORT.read_text(encoding="utf-8"), COMPATIBILITY_REPORT.read_text(encoding="utf-8")]
        texts.extend(path.read_text(encoding="utf-8") for path in BUILTIN_ROOT.rglob("module.json"))
        serialized = "\n".join(texts)

        self.assertNotIn("/Users/", serialized)
        self.assertNotIn("biomedical-agent-sources", serialized)
        self.assertNotIn(".claude-science", serialized)
        self.assertNotIn("source_path", serialized)


if __name__ == "__main__":
    unittest.main()
