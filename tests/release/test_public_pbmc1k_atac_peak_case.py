import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-pbmc1k-atac-macs3.json"
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-atac-regulatory"
)


class PublicPBMC1kATACPeakCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_case_is_bound_to_sources_module_and_template(self):
        report = self.report
        self.assertTrue(report["passed"])
        self.assertEqual(report["case_type"], "public-data-end-to-end")
        self.assertEqual(report["module"]["version"], "1.1.0")
        self.assertEqual(
            report["module"]["manifest_sha256"],
            hashlib.sha256((MODULE_ROOT / "module.json").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            report["module"]["template_sha256"],
            hashlib.sha256(
                (MODULE_ROOT / "templates" / "call_macs3_fragments.py").read_bytes()
            ).hexdigest(),
        )
        files = report["source"]["files"]
        self.assertEqual(
            files["fragments"]["sha256"],
            "391176fa39181a96822ade86468d58a8e058f52751866048669d77a988c38bb7",
        )
        self.assertEqual(
            files["peak_matrix"]["sha256"],
            "40a1a361760c8072143d1e3678a5ef807a1a15bcd240fdbea08be857a19ec380",
        )

    def test_fragment_accounting_and_peak_reload_are_preserved(self):
        accounting = self.report["execution"]["accounting"]
        outputs = self.report["execution"]["outputs"]
        self.assertEqual(accounting["allowlist_barcodes"], 300)
        self.assertEqual(accounting["selected_barcodes"], 300)
        self.assertEqual(accounting["allowlist_barcodes_absent_from_fragments"], [])
        self.assertEqual(
            accounting["selected_records"] + accounting["excluded_records"],
            accounting["total_records"],
        )
        self.assertEqual(
            accounting["selected_fragment_count"]
            + accounting["excluded_fragment_count"],
            accounting["total_fragment_count"],
        )
        self.assertGreater(outputs["narrow_peak"]["rows"], 10000)
        self.assertEqual(
            outputs["narrow_peak"]["rows"],
            outputs["summits"]["rows"],
        )
        self.assertTrue(self.report["execution"]["outputs_reloaded"])
        self.assertTrue(self.report["execution"]["source_artifacts_immutable"])
        self.assertTrue(
            all(value == "pass" for value in self.report["quality_gates"].values())
        )

    def test_case_records_limits_and_contains_no_private_material(self):
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()
        for phrase in (
            "atac-only",
            "remain covered by the complete executable fixture",
            "not donor-level differential accessibility",
            "do not establish direct binding",
        ):
            self.assertIn(phrase, boundaries)
        serialized = REPORT.read_text(encoding="utf-8")
        for forbidden in (
            "/Users/",
            "/private/",
            "/var/folders/",
            "ACCESS_TOKEN=",
            "SECRET=",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertIsNone(
            re.search(
                r"(?:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_-]{16,}",
                serialized,
                re.IGNORECASE,
            )
        )


if __name__ == "__main__":
    unittest.main()
