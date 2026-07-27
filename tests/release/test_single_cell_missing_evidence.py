import hashlib
import json
import re
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin"
REPORTS = ROOT / "reports"


class SingleCellMissingEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ModuleRegistry.discover(BUILTIN_ROOT)

    def _manifest_and_report(self, module_id: str):
        module_root = MODULE_ROOT / module_id
        manifest = parse_manifest(json.loads((module_root / "module.json").read_text(encoding="utf-8")))
        report = json.loads((REPORTS / f"{module_id}-live-verification.json").read_text(encoding="utf-8"))
        return manifest, module_root, report

    def _assert_binding(self, module_id: str, template_map: dict[str, str], *, compatibility_row_id_field: str = "compatibility_row_id"):
        manifest, module_root, report = self._manifest_and_report(module_id)
        row = manifest.compatibility_matrix[0]
        self.assertTrue(report["passed"], report.get("compatibility_row_id", "missing"))
        self.assertEqual(report["module_id"], module_id)
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["registry_digest"], self.registry.digest)
        self.assertEqual(report[compatibility_row_id_field], row.id)
        for key, filename in template_map.items():
            expected = (module_root / "templates" / filename).read_bytes()
            self.assertEqual(
                report["templates"][key]["sha256"],
                hashlib.sha256(expected).hexdigest(),
                msg=f"{module_id} template mismatch: {key}",
            )
        self.assertTrue(all(version_is_allowed(report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        if report.get("dependency_versions") is not None:
            self.assertEqual(set(report["dependency_versions"]), set(row.dependency_versions))
            self.assertTrue(
                all(version_is_allowed(value, row.dependency_versions[name]) for name, value in report["dependency_versions"].items())
            )
        return manifest, report

    def _assert_no_paths_or_credentials(self, report_text: str):
        self.assertNotIn("/Users/", report_text)
        self.assertNotIn("/private/", report_text)
        self.assertNotIn("file://", report_text)
        self.assertNotRegex(report_text, r"(?:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_-]{16,}", re.IGNORECASE)

    def _row_rules_for_name(self, compatibility_matrix, name: str):
        normalized = name.lower()
        rules = []
        for row in compatibility_matrix:
            for key, values in row.tool_versions.items():
                if key.lower() == normalized:
                    rules.append(values)
        return rules

    def test_single_cell_qc_evidence_binding_and_runtime_constraints(self):
        manifest, module_root, report = self._manifest_and_report("single-cell-qc")
        self.assertTrue(report["passed"])
        self.assertEqual(report["compatibility_row_id"], manifest.compatibility_matrix[0].id)
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["registry_digest"], self.registry.digest)
        expected_template = (module_root / "templates" / "run_single_cell_qc.py").read_bytes()
        self.assertEqual(
            report["templates"]["single_cell_qc"]["sha256"],
            hashlib.sha256(expected_template).hexdigest(),
        )
        self.assertEqual(set(report["dependency_versions"]), set(manifest.compatibility_matrix[0].dependency_versions))
        self.assertTrue(
            all(
                version_is_allowed(value, manifest.compatibility_matrix[0].dependency_versions[name])
                for name, value in report["dependency_versions"].items()
            )
        )
        self.assertTrue(report["scientific_summary"]["qc_thresholds_applied"])
        self.assertTrue(report["scientific_summary"]["cell_level_qc_flags_retained"])
        self.assertTrue(report["execution"]["template_completed"])
        self.assertEqual(report["execution"]["result_cells_returned"], report["fixture"]["cells"])
        self._assert_no_paths_or_credentials((REPORTS / "single-cell-qc-live-verification.json").read_text(encoding="utf-8"))

    def test_single_cell_droplet_decontamination_evidence_binding_and_versions(self):
        manifest, module_root, report = self._manifest_and_report("single-cell-droplet-decontamination")
        row = manifest.compatibility_matrix[0]
        self.assertTrue(report["passed"])
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["module_id"], manifest.id)
        self.assertEqual(report["registry_digest"], self.registry.digest)
        self.assertEqual(
            report["templates"]["cellbender"]["sha256"],
            hashlib.sha256((module_root / "templates" / "run_cellbender.py").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            report["templates"]["r"]["sha256"],
            hashlib.sha256((module_root / "templates" / "run_emptydrops_soupx.R").read_bytes()).hexdigest(),
        )
        self.assertTrue(
            all(version_is_allowed(report["tool_versions"][name], rules) for name, rules in row.tool_versions.items())
        )
        self.assertTrue(
            all(version_is_allowed(value, row.dependency_versions[name]) for name, value in report["dependency_versions"].items())
        )
        scientific = report["scientific_summary"]
        self.assertTrue(scientific["nonnegative_counts"])
        self.assertTrue(scientific["raw_counts_preserved"])
        self.assertTrue(scientific["methods_separated"])
        self.assertTrue(scientific["no_environment_or_compute_infrastructure_managed"])
        self._assert_no_paths_or_credentials((REPORTS / "single-cell-droplet-decontamination-live-verification.json").read_text(encoding="utf-8"))

    def test_single_cell_foundation_workflow_binding_and_scanpy_or_seurat_backends(self):
        manifest, module_root, report = self._manifest_and_report("single-cell-foundation-workflow")
        row = manifest.compatibility_matrix[0]
        self.assertTrue(report["passed"])
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["module_id"], manifest.id)
        self.assertEqual(report["registry_digest"], self.registry.digest)
        self.assertEqual(
            report["templates"]["scanpy_foundation.py"]["sha256"],
            hashlib.sha256((module_root / "templates" / "scanpy_foundation.py").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            report["templates"]["seurat_foundation.R"]["sha256"],
            hashlib.sha256((module_root / "templates" / "seurat_foundation.R").read_bytes()).hexdigest(),
        )
        self.assertTrue(
            all(version_is_allowed(report["tool_versions"][name], rules) for name, rules in row.tool_versions.items())
        )
        self.assertEqual(
            report["scientific_summary"]["scanpy_and_seurat_backends_passed"],
            True,
        )
        self.assertTrue(report["scientific_summary"]["raw_counts_preserved"])
        self._assert_no_paths_or_credentials((REPORTS / "single-cell-foundation-workflow-live-verification.json").read_text(encoding="utf-8"))

    def test_single_cell_communication_evidence_covers_python_and_r_protocols(self):
        manifest, module_root, report = self._manifest_and_report("single-cell-communication")
        self.assertTrue(report["passed"])
        self.assertEqual(report["module_id"], manifest.id)
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["registry_digest"], self.registry.digest)
        self.assertEqual(
            report["templates"]["run_liana_cellphonedb"]["sha256"],
            hashlib.sha256((module_root / "templates" / "run_liana_cellphonedb.py").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            report["templates"]["run_cellchat_nichenet"]["sha256"],
            hashlib.sha256((module_root / "templates" / "run_cellchat_nichenet.R").read_bytes()).hexdigest(),
        )
        reported_row_ids = {item["id"] for item in report["compatibility_rows"]}
        manifest_row_ids = {row.id for row in manifest.compatibility_matrix}
        self.assertTrue(reported_row_ids <= manifest_row_ids)
        for version_name, version in report["versions"].items():
            allowed_rules = self._row_rules_for_name(manifest.compatibility_matrix, version_name)
            if not allowed_rules:
                continue
            self.assertTrue(any(version_is_allowed(version, rules) for rules in allowed_rules), version_name)
        python_backends = set(report["python_backends"]["methods"])
        r_backends = set(report["r_backends"]["methods"])
        self.assertEqual(python_backends, {"liana-cellphonedb", "cellphonedb-statistical"})
        self.assertEqual(r_backends, {"cellchat", "nichenet"})
        self.assertTrue(report["scientific_summary"]["all_four_backends_executed"])
        self.assertTrue(report["scientific_summary"]["outputs_reloaded"])
        self._assert_no_paths_or_credentials((REPORTS / "single-cell-communication-live-verification.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
