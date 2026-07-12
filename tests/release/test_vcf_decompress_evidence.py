import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "vcf-decompress-live-verification.json"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "variants"


class VCFDecompressEvidenceTests(unittest.TestCase):
    def test_live_report_binds_module_bundle_and_byte_exact_roundtrip(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = ModuleRegistry.discover(BUILTIN_ROOT).get("variant-decompress-bgzip")
        row = manifest.compatibility_matrix[0]

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(report["tool_versions"], {"bgzip": "1.23"})
        self.assertEqual(report["dependency_versions"], {"htslib": "1.23"})
        self.assertEqual(report["fixture"]["source_sha256"], hashlib.sha256((FIXTURE_ROOT / "region-query.vcf").read_bytes()).hexdigest())
        self.assertEqual(report["fixture"]["vcf_bgzf_sha256"], hashlib.sha256((FIXTURE_ROOT / "region-query.vcf.gz").read_bytes()).hexdigest())
        self.assertEqual(report["fixture"]["index_sha256"], hashlib.sha256((FIXTURE_ROOT / "region-query.vcf.gz.tbi").read_bytes()).hexdigest())
        self.assertTrue(all(report["bundle_integrity"].values()))
        self.assertEqual(report["scientific_summary"]["record_count"], 7)

    def test_public_evidence_has_no_machine_path_or_credential(self):
        serialized = REPORT.read_text(encoding="utf-8")

        for marker in ("/Users/", "/private/", "/Volumes/", "file://", "API_KEY", "nvapi-"):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
