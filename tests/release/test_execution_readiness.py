import unittest

from tools.audit_execution_readiness import build


class ExecutionReadinessTests(unittest.TestCase):
    def test_statuses_distinguish_contract_executor_and_public_validation(self):
        report = build()
        self.assertEqual(report["schema_version"], 4)
        self.assertEqual(report["axis_counts"]["contract_valid"], report["module_count"])
        self.assertLess(report["axis_counts"]["representative_or_public_case_validated"], report["module_count"])
        self.assertEqual(report["axis_counts"]["current_project_reviewed"], 0)
        self.assertFalse(report["single_maturity_count_is_authoritative"])
        self.assertNotIn("manual-adaptation", report["counts"])
        by_id = {record["module_id"]: record for record in report["records"]}
        self.assertTrue(by_id["bulk-ribosome-profiling"]["executor_ready"])
        self.assertTrue(by_id["bulk-r-loop-mapping"]["executor_ready"])
        self.assertTrue(by_id["bulk-r-loop-mapping"]["evidence_axes"]["adapter_static_reachable"])
        cuttag = next(
            row for row in by_id["bulk-r-loop-mapping"]["assay_readiness"]
            if row["assay"] == "cuttag"
        )
        self.assertEqual(cuttag["executor_module_id"], "bulk-chromatin-peak-calling")
        self.assertEqual(len(cuttag["executor_paths"]), 2)
        fastqc = by_id["read-quality-fastqc"]
        self.assertEqual(fastqc["entry_surface_reachability"]["cli"]["mode"], "strict-project-artifact-execution")
        self.assertFalse(fastqc["entry_surface_reachability"]["mcp"]["reachable"])
        handoff = by_id["single-cell-batch-integration"]
        self.assertEqual(handoff["entry_surface_reachability"]["cli"]["mode"], "execution-handoff")
        self.assertFalse(handoff["entry_surface_reachability"]["cli"]["scientific_completion"])


if __name__ == "__main__":
    unittest.main()
