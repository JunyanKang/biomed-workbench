import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed
from tools.verify_single_cell_donor_inference_live import bh_adjust


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / "single-cell-donor-inference"
REPORT = ROOT / "reports" / "single-cell-donor-inference-live-verification.json"


class SingleCellDonorInferenceEvidenceTests(unittest.TestCase):
    def test_live_report_is_bound_to_templates_and_declared_versions(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        manifest = parse_manifest(json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8")))
        row = manifest.compatibility_matrix[0]
        observed_templates = {item["name"]: item["sha256"] for item in report["templates"].values()}
        expected_templates = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (MODULE_ROOT / "templates").iterdir() if path.is_file()
        }

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_id"], manifest.id)
        self.assertEqual(report["module_version"], manifest.version)
        self.assertEqual(report["compatibility_row_id"], row.id)
        self.assertEqual(observed_templates, expected_templates)
        self.assertTrue(all(version_is_allowed(report["tool_versions"][name], rules) for name, rules in row.tool_versions.items()))
        self.assertEqual(set(report["dependency_versions"]), set(row.dependency_versions) - {"python"})
        self.assertTrue(all(version_is_allowed(version, row.dependency_versions[name]) for name, version in report["dependency_versions"].items()))

    def test_live_report_proves_biological_replication_and_three_engines(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        summary = report["scientific_summary"]

        self.assertEqual(report["fixture"]["biological_samples"], 8)
        self.assertEqual(summary["biological_replicates_per_condition"], 4)
        self.assertFalse(summary["cells_used_as_replicates"])
        self.assertTrue(summary["raw_counts_conserved"])
        self.assertTrue(summary["all_designs_full_rank"])
        self.assertTrue(summary["categorical_and_continuous_covariates_validated"])
        self.assertTrue(summary["all_result_files_reloaded"])
        self.assertTrue(summary["global_bh_independently_recomputed"])
        self.assertTrue(summary["edger_deseq2_limma_voom_passed"])
        self.assertEqual(set(report["result_summaries"]), {"edger", "deseq2", "limma-voom"})
        for engine in report["result_summaries"].values():
            self.assertTrue(engine["bh_recomputed"])
            self.assertEqual(engine["rows"], 160)
            self.assertTrue(all(item["significant_planted_genes"] == 8 for item in engine["planted_effects"].values()))

    def test_bh_reference_implementation_is_monotone_in_rank(self):
        p_values = [0.04, 0.001, 0.03, 0.2]
        adjusted = bh_adjust(p_values)
        ranked = [adjusted[index] for index in sorted(range(len(p_values)), key=p_values.__getitem__)]

        self.assertTrue(all(left <= right for left, right in zip(ranked, ranked[1:])))
        self.assertEqual(adjusted[1], 0.004)

    def test_report_contains_no_machine_path_or_credential(self):
        serialized = REPORT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/private/", "file://", "NCBI_API_KEY", "nvapi-", "bf339"):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
