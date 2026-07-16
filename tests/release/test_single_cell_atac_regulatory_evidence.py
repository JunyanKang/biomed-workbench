import hashlib
import json
import re
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = BUILTIN_ROOT / "single-cell-atac-regulatory"
REPORT = ROOT / "reports" / "single-cell-atac-regulatory-live-verification.json"


class SingleCellAtacRegulatoryEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.manifest = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))

    def test_report_is_bound_to_templates_registry_and_versions(self):
        row = self.manifest.compatibility_matrix[0]
        self.assertTrue(self.report["passed"])
        self.assertEqual(self.report["module_id"], self.manifest.id)
        self.assertEqual(self.report["module_version"], self.manifest.version)
        self.assertEqual(self.report["compatibility_row_id"], row.id)
        self.assertEqual(self.report["registry_digest"], ModuleRegistry.discover(BUILTIN_ROOT).digest)
        for key, filename in {"macs3": "call_macs3_fragments.py", "regulatory": "run_atac_regulatory.R"}.items():
            template = MODULE_ROOT / "templates" / filename
            self.assertEqual(self.report["templates"][key]["sha256"], hashlib.sha256(template.read_bytes()).hexdigest())
        self.assertTrue(all(version_is_allowed(self.report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        self.assertEqual(set(self.report["dependency_versions"]), set(row.dependency_versions))
        self.assertTrue(all(version_is_allowed(value, row.dependency_versions[name]) for name, value in self.report["dependency_versions"].items()))

    def test_macs3_recovers_selected_peaks_and_excludes_unselected_barcode_peak(self):
        backend = self.report["backend_summaries"]["macs3"]
        accounting = backend["accounting"]
        evaluation = self.report["independent_evaluation"]
        self.assertEqual(accounting["total_fragment_count"], accounting["selected_fragment_count"] + accounting["excluded_fragment_count"])
        self.assertEqual(accounting["total_records"], accounting["selected_records"] + accounting["excluded_records"])
        self.assertEqual(accounting["selected_barcodes"], 20)
        self.assertEqual(accounting["allowlist_barcodes_absent_from_fragments"], [])
        self.assertEqual(backend["outputs"]["narrow_peak"]["rows"], 2)
        self.assertTrue(evaluation["expected_peak_20k_recovered"])
        self.assertTrue(evaluation["expected_peak_60k_recovered"])
        self.assertTrue(evaluation["excluded_barcode_peak_absent"])

    def test_motif_chromvar_and_peak_gene_signal_are_independently_recovered(self):
        evaluation = self.report["independent_evaluation"]
        regulatory = self.report["backend_summaries"]["regulatory"]["results"]
        self.assertEqual(evaluation["motif_a_planted_matches"], 15)
        self.assertGreater(evaluation["motif_a_group_contrast"], 2)
        self.assertTrue(evaluation["target_gene1_positive_link"])
        self.assertGreater(evaluation["peak_gene_link_rows"], 0)
        self.assertEqual(regulatory["modeled_motifs"], 2)
        self.assertEqual(regulatory["unsupported_motifs"], 1)
        self.assertEqual(regulatory["background_rows"], 120)
        self.assertEqual(regulatory["background_iterations"], 50)

    def test_source_preservation_method_separation_and_reload_are_explicit(self):
        summary = self.report["scientific_summary"]
        for key in (
            "macs3_frag_peak_calling_executed", "barcode_filtering_and_fragment_accounting_reconciled",
            "motifmatchr_sequence_scan_executed", "gc_accessibility_matched_chromvar_executed",
            "signac_linkpeaks_executed", "planted_peaks_motif_activity_and_peak_gene_link_recovered",
            "paired_cells_source_counts_and_fragments_preserved", "method_specific_outputs_retained",
            "outputs_reloaded", "evaluation_truth_posthoc_only", "no_environment_or_compute_infrastructure_managed",
        ):
            self.assertTrue(summary[key], key)

    def test_report_contains_no_machine_paths_or_credentials(self):
        serialized = REPORT.read_text(encoding="utf-8")
        self.assertNotRegex(serialized, r"/(?:Users|private|home)/")
        self.assertNotIn("file://", serialized)
        self.assertIsNone(re.search(r"(?:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_-]{16,}", serialized, re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
