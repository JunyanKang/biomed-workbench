from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from biomed_workbench.modules.evidence_scope import evidence_scope_is_current
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.visualization import ANALYSIS_FIGURE_PROFILES
from tools.audit_execution_readiness import _controlled_fixture_report_receipts


ROOT = Path(__file__).resolve().parents[2]
MODULE_ID = "rna-processing-alternative-splicing"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
REPORT_PATH = ROOT / "reports/rna-processing-alternative-splicing-live-verification.json"


class RNAProcessingAlternativeSplicingEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = ModuleRegistry.discover(BUILTIN_ROOT)
        cls.manifest = cls.registry.get(MODULE_ID)
        cls.report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    def test_report_binds_current_implementation_and_exact_module_slice(self) -> None:
        implementation = self.report["implementation"]
        path = ROOT / implementation["path"]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), implementation["sha256"])
        self.assertTrue(evidence_scope_is_current(self.report, self.registry))
        self.assertEqual(self.report["official_backend_case"]["backend_version"], "4.4.0")
        self.assertEqual(self.report["official_backend_case"]["backend_source_commit"], "015c0305f87cdeec0edd56a99d5ab1689832fa40")

    def test_observed_case_is_reloaded_but_not_promoted_as_biological_validation(self) -> None:
        case = self.report["official_backend_case"]
        self.assertEqual(case["official_test_status"], "passed")
        self.assertEqual(case["observed_event_type"], "SE")
        self.assertEqual(case["observed_event_count"], 1)
        self.assertEqual(case["observed_delta_psi_group1_minus_group2"], 1.0)
        self.assertFalse(case["formal_design_gate"])
        self.assertEqual(
            self.report["maturity"],
            {"engineering_validated": True, "method_validated": False, "project_promoted": False},
        )

    def test_controlled_receipt_is_accepted_by_release_readiness(self) -> None:
        receipts = _controlled_fixture_report_receipts(self.registry)
        self.assertIn(MODULE_ID, receipts)
        self.assertEqual(len(receipts[MODULE_ID]), 64)

    def test_execution_coverage_contains_only_real_packaged_branches(self) -> None:
        coverage = json.loads((MODULE_ROOT / "execution_coverage.json").read_text(encoding="utf-8"))
        self.assertEqual(coverage["input_property"], "analysis_branch")
        self.assertEqual(
            {row["assay"] for row in coverage["assays"]},
            {"design", "bulk-rmats", "single-cell-junction-screen", "evidence-integration"},
        )
        self.assertTrue(all(row["contract_ready"] is True for row in coverage["assays"]))
        self.assertNotIn("DRIMSeq-stageR", {row["backend"] for row in coverage["assays"]})
        self.assertIn("DRIMSeq-stageR differential transcript usage", self.report["unvalidated_execution_slices"])

    def test_publication_figure_profile_is_registered(self) -> None:
        profile = ANALYSIS_FIGURE_PROFILES[MODULE_ID]
        self.assertIn("biological_sample_usage_plot", profile["required"])
        self.assertIn("representative_gene_model_or_splice_graph", profile["required"])
        self.assertIn("sashimi_or_voila_view", profile["optional"])


if __name__ == "__main__":
    unittest.main()
