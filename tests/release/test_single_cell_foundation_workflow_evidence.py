import hashlib
import json
import re
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry

ROOT = Path(__file__).resolve().parents[2]
MODULE_ID = "single-cell-foundation-workflow"
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / MODULE_ID
REPORT = ROOT / "reports" / "single-cell-foundation-workflow-live-verification.json"


class SingleCellFoundationWorkflowEvidenceTests(unittest.TestCase):
    def test_report_is_bound_to_manifest_and_template_contracts(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_id"], manifest.id)
        self.assertEqual(report["module_id"], MODULE_ID)
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["registry_digest"], ModuleRegistry.discover(BUILTIN_ROOT).digest)
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["templates"]["scanpy"]["sha256"], hashlib.sha256((MODULE_ROOT / "templates" / "scanpy_foundation.py").read_bytes()).hexdigest())
        self.assertEqual(report["templates"]["seurat"]["sha256"], hashlib.sha256((MODULE_ROOT / "templates" / "seurat_foundation.R").read_bytes()).hexdigest())
        self.assertTrue(version_is_allowed(report["tool_versions"]["scanpy"], row.tool_versions["scanpy"]))
        self.assertTrue(version_is_allowed(report["scientific_runtime"]["scanpy"]["scanpy"], row.tool_versions["scanpy"]))
        self.assertTrue(version_is_allowed(report["tool_versions"]["seurat"], row.tool_versions["seurat"]))
        self.assertEqual(set(report["scientific_runtime"].keys()), {"scanpy", "seurat"})

    def test_foundation_evidence_coverage_and_roundtrip(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertTrue(report["execution"]["scanpy_completed"])
        self.assertTrue(report["execution"]["seurat_completed"])
        self.assertTrue(report["execution"]["scanpy_qc_report_sha256"])
        self.assertTrue(report["execution"]["seurat_qc_report_sha256"])
        self.assertTrue(report["execution"]["output_h5ad_sha256"])
        self.assertTrue(report["execution"]["output_seurat_rds_sha256"])
        self.assertTrue(report["execution"]["scanpy_cluster_report_sha256"])
        self.assertTrue(report["execution"]["seurat_cluster_report_sha256"])
        self.assertEqual(report["fixtures"]["scanpy"]["cells"], report["fixtures"]["seurat"]["cells"])
        self.assertEqual(report["fixtures"]["scanpy"]["features"], report["fixtures"]["seurat"]["features"])
        self.assertGreater(report["fixtures"]["scanpy"]["cells"], 10)
        self.assertEqual(report["scientific_summary"]["scanpy_and_seurat_backends_passed"], True)
        self.assertEqual(report["scientific_summary"]["reload_validation_passed"], True)

    def test_report_has_no_machine_paths_or_credentials(self):
        text = REPORT.read_text(encoding="utf-8")
        self.assertNotIn("/Users/", text)
        self.assertNotIn("/private/", text)
        self.assertNotIn("file://", text)
        self.assertIsNone(re.search(r"(?:api[_-]?key|access[_-]?token|secret)\\s*[:=]", text, re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
