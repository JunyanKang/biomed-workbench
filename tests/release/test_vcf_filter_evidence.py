import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "vcf-filter-live-verification.json"
FIXTURE = ROOT / "tests" / "fixtures" / "variants" / "region-query.vcf"
IMPLEMENTATION = ROOT / "biomed_workbench" / "implementations" / "vcf_filter.py"


class VCFFilterEvidenceTests(unittest.TestCase):
    def test_live_report_binds_module_interpreter_implementation_fixture_and_accounting(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = ModuleRegistry.discover(BUILTIN_ROOT).get("variant-filter-vcf")
        row = manifest.compatibility_matrix[0]

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["regression_evidence_id"], row.regression_evidence_ids[0])
        self.assertEqual(report["end_to_end_evidence_id"], row.end_to_end_evidence_ids[0])
        self.assertEqual(report["tool_versions"], {"python3": "3.14.3"})
        self.assertEqual(report["dependency_versions"], {"python-stdlib": "3.14.3"})
        self.assertEqual(report["fixture"]["vcf_sha256"], hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
        self.assertEqual(report["implementation"]["sha256"], hashlib.sha256(IMPLEMENTATION.read_bytes()).hexdigest())
        self.assertEqual(report["scientific_summary"]["accepted_record_keys"], ["chr1:100:A:G:v1"])
        self.assertEqual(sum(report["scientific_summary"]["exclusion_counts"].values()), 6)

    def test_public_evidence_has_no_machine_path_or_credential(self):
        serialized = REPORT.read_text(encoding="utf-8")

        for marker in ("/Users/", "/private/", "/Volumes/", "file://", "API_KEY", "ACCESS_TOKEN="):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
