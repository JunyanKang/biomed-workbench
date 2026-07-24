import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry

ROOT = Path(__file__).resolve().parents[2]
MODULE_ID = "single-cell-droplet-decontamination"
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / MODULE_ID
REPORT = ROOT / "reports" / "single-cell-droplet-decontamination-live-verification.json"


class SingleCellDropletDecontaminationEvidenceTests(unittest.TestCase):
    def test_report_is_bound_to_manifest_and_templates(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_id"], manifest.id)
        self.assertEqual(report["module_id"], MODULE_ID)
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["registry_digest"], ModuleRegistry.discover(BUILTIN_ROOT).digest)
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(set(report["dependency_versions"]), set(row.dependency_versions))
        self.assertTrue(all(version_is_allowed(value, row.dependency_versions[name]) for name, value in report["dependency_versions"].items()))
        self.assertTrue(all(version_is_allowed(report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        self.assertEqual(report["templates"]["cellbender"]["sha256"], hashlib.sha256((MODULE_ROOT / "templates" / "run_cellbender.py").read_bytes()).hexdigest())
        self.assertEqual(report["templates"]["r"]["sha256"], hashlib.sha256((MODULE_ROOT / "templates" / "run_emptydrops_soupx.R").read_bytes()).hexdigest())

    def test_droplet_backends_execute_and_reload_outputs(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        execution = report["execution"]
        self.assertTrue(execution["cellbender_completed"])
        self.assertTrue(execution["emptydrops_completed"])
        self.assertTrue(execution["soupx_auto_completed"])
        self.assertTrue(execution["soupx_fixed_completed"])
        self.assertTrue(execution["outputs_reloaded"])
        self.assertTrue(execution["cellbender_output_sha256"])
        self.assertEqual(report["scientific_summary"]["no_environment_or_compute_infrastructure_managed"], True)


if __name__ == "__main__":
    unittest.main()
