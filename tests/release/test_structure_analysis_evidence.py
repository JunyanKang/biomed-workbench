import hashlib
import json
import re
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import version_is_allowed
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
MODULE_IDS = {
    "structure-quality-assessment",
    "structure-chain-comparison",
    "docking-pose-review",
    "chemical-substructure-filter",
    "protein-secondary-structure",
    "structure-interactive-visualization",
}


class StructureAnalysisEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ModuleRegistry.discover(BUILTIN_ROOT)
        cls.reports = {
            module_id: json.loads((ROOT / "reports" / f"{module_id}-live-verification.json").read_text(encoding="utf-8"))
            for module_id in MODULE_IDS
        }

    def test_reports_bind_current_modules_templates_and_cases(self):
        for module_id, report in self.reports.items():
            manifest = self.registry.get(module_id)
            row = manifest.compatibility_matrix[0]
            package = report["module_package_validation"]
            observed_templates = {item["name"]: item["sha256"] for item in report["templates"].values()}
            expected_templates = {
                (BUILTIN_ROOT / module_id / item.path).name: hashlib.sha256((BUILTIN_ROOT / module_id / item.path).read_bytes()).hexdigest()
                for item in manifest.code_templates
            }

            self.assertTrue(report["passed"], module_id)
            self.assertEqual(report["module_version"], manifest.version)
            self.assertEqual(report["compatibility_row_id"], row.id)
            self.assertEqual(report["registry_digest"], self.registry.digest)
            self.assertEqual(observed_templates, expected_templates)
            self.assertTrue(package["valid"])
            self.assertEqual(package["executed_test_cases"], 1)
            self.assertEqual(package["module_version"], manifest.version)

    def test_observed_versions_satisfy_compatibility_rows(self):
        for module_id, report in self.reports.items():
            row = self.registry.get(module_id).compatibility_matrix[0]
            for name, rules in row.tool_versions.items():
                self.assertTrue(version_is_allowed(report["tool_versions"][name], rules), f"{module_id}:{name}")
            self.assertTrue(version_is_allowed(report["dependency_versions"]["python"], row.dependency_versions["python"]))

        self.assertEqual(self.reports["structure-quality-assessment"]["tool_versions"], {"biopython": "1.87"})
        self.assertEqual(self.reports["docking-pose-review"]["tool_versions"], {"biopython": "1.87", "rdkit": "2025.9.6"})
        self.assertEqual(
            self.reports["protein-secondary-structure"]["tool_versions"],
            {"biopython": "1.87", "matplotlib": "3.11.0", "mkdssp": "4.6.1"},
        )
        self.assertEqual(
            self.reports["structure-interactive-visualization"]["tool_versions"],
            {"biopython": "1.87", "py3dmol": "2.5.3"},
        )

    def test_scientific_assertions_and_outputs_all_pass(self):
        for module_id, report in self.reports.items():
            self.assertEqual(set(report["scientific_summary"].values()), {True}, module_id)
            self.assertTrue(report["execution"]["template_completed"])
            self.assertTrue(report["execution"]["outputs_reloaded"])
            self.assertTrue(report["no_environment_or_compute_infrastructure_managed"])
            for artifact in report["execution"]["output_artifacts"].values():
                self.assertRegex(artifact["sha256"], r"^[0-9a-f]{64}$")
                self.assertGreater(artifact["bytes"], 0)

        self.assertTrue(self.reports["structure-chain-comparison"]["scientific_summary"]["tm_score_not_fabricated"])
        self.assertTrue(self.reports["docking-pose-review"]["scientific_summary"]["invalid_sdf_retained"])
        self.assertTrue(self.reports["protein-secondary-structure"]["scientific_summary"]["dssp_resources_digested"])

    def test_fixture_identity_is_consistent_and_public_reports_are_portable(self):
        experimental = {report["fixtures"]["experimental_structure"]["sha256"] for report in self.reports.values()}
        predicted = {report["fixtures"]["predicted_structure"]["sha256"] for report in self.reports.values()}
        self.assertEqual(len(experimental), 1)
        self.assertEqual(len(predicted), 1)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", value) for value in experimental | predicted))

        serialized = "\n".join(
            (ROOT / "reports" / f"{module_id}-live-verification.json").read_text(encoding="utf-8")
            for module_id in MODULE_IDS
        )
        for marker in ("/Users/", "/private/", "/Volumes/", "file://", "API_KEY", "nvapi-", "NGC_API_KEY"):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
