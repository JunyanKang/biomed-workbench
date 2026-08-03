import hashlib
import json
import re
import unittest
from pathlib import Path
from tests.release.evidence_scope_assertions import assert_evidence_scope_current


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-gse96583-donor-inference.json"
MODULE_ROOT = (
    ROOT / "biomed_workbench" / "modules" / "builtin" / "single-cell-donor-inference"
)


class PublicGSE96583DonorCaseReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_case_is_bound_to_source_module_and_both_templates(self):
        report = self.report
        self.assertTrue(report["passed"])
        self.assertEqual(report["case_type"], "public-data-end-to-end")
        self.assertEqual(report["source"]["accession"], "GSE96583")
        self.assertEqual(report["source"]["source_validation"]["paired_donors"], 8)
        assert_evidence_scope_current(self, report)
        for filename in ("pseudobulk_aggregate.py", "donor_differential.R"):
            self.assertEqual(
                report["module"]["template_sha256"][filename],
                hashlib.sha256((MODULE_ROOT / "templates" / filename).read_bytes()).hexdigest(),
            )

    def test_case_uses_biological_replicates_and_reloads_results(self):
        execution = self.report["execution"]
        self.assertEqual(execution["pseudobulks"], 128)
        self.assertTrue(execution["all_cells_accounted"])
        self.assertTrue(execution["raw_counts_conserved"])
        self.assertTrue(execution["paired_designs_full_rank"])
        self.assertTrue(execution["result_reload_validated"])
        self.assertGreaterEqual(execution["completed_cell_types"], 6)
        self.assertGreaterEqual(len(execution["ifn_response_genes_recovered"]), 8)
        self.assertGreaterEqual(len(execution["ifn_response_cell_types"]), 5)
        self.assertTrue(all(value == "pass" for value in self.report["quality_gates"].values()))

    def test_case_records_limits_and_contains_no_private_material(self):
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()
        for phrase in (
            "publisher-provided annotations",
            "does not claim cross-engine sensitivity",
            "eight sampled donors",
            "not universal defaults",
        ):
            self.assertIn(phrase, boundaries)
        serialized = REPORT.read_text(encoding="utf-8")
        for forbidden in ("/Users/", "/private/", "/var/folders/", "ACCESS_TOKEN=", "SECRET="):
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
