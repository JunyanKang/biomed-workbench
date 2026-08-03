import hashlib
import json
import re
import unittest
from pathlib import Path
from tests.release.evidence_scope_assertions import assert_evidence_scope_current


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-case-gse96583-marker-discovery.json"
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-marker-discovery"
)


class PublicGSE96583MarkerCaseReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_case_is_bound_to_source_module_and_template(self):
        report = self.report
        self.assertTrue(report["passed"])
        self.assertEqual(report["case_type"], "public-data-end-to-end")
        self.assertEqual(report["source"]["accession"], "GSE96583")
        self.assertEqual(report["module"]["version"], "1.1.0")
        assert_evidence_scope_current(self, report)
        self.assertEqual(
            report["module"]["template_sha256"],
            hashlib.sha256(
                (MODULE_ROOT / "templates" / "discover_markers.py").read_bytes()
            ).hexdigest(),
        )

    def test_case_separates_six_discovery_and_two_validation_donors(self):
        parameters = self.report["parameters"]
        execution = self.report["execution"]
        self.assertTrue(parameters["sample_split_frozen_before_ranking"])
        self.assertEqual(len(parameters["discovery_donors"]), 6)
        self.assertEqual(len(parameters["validation_donors"]), 2)
        self.assertTrue(
            set(parameters["discovery_donors"]).isdisjoint(
                parameters["validation_donors"]
            )
        )
        self.assertEqual(execution["input_control_singlets"], 11990)
        self.assertEqual(execution["retained_features"], 10859)
        self.assertEqual(execution["cell_types"], 6)
        self.assertEqual(execution["tested_marker_rows"], 900)
        self.assertTrue(execution["exact_repeat_marker_tsv"])

    def test_all_cell_types_have_independently_validated_markers(self):
        execution = self.report["execution"]
        self.assertEqual(execution["discovery_admitted_rows"], 612)
        self.assertEqual(execution["independently_validated_rows"], 606)
        self.assertEqual(
            set(execution["recovered_expected_marker_families"]),
            {
                "B cells",
                "CD14+ Monocytes",
                "CD4 T cells",
                "CD8 T cells",
                "FCGR3A+ Monocytes",
                "NK cells",
            },
        )
        self.assertTrue(
            all(
                value >= 5
                for value in execution[
                    "independently_validated_rows_by_cell_type"
                ].values()
            )
        )
        self.assertTrue(
            all(value == "pass" for value in self.report["quality_gates"].values())
        )

    def test_case_records_limits_and_contains_no_private_material(self):
        boundaries = " ".join(self.report["scientific_boundaries"]).lower()
        for phrase in (
            "publisher-provided cell-type labels",
            "held-out donor identities",
            "not interpreted as donor-level",
            "not used to tune",
            "does not establish specificity",
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
