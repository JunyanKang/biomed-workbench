import unittest

from tools.audit_execution_readiness import build


class ExecutionReadinessTests(unittest.TestCase):
    def test_statuses_distinguish_contract_executor_and_public_validation(self):
        report = build()
        self.assertEqual(report["schema_version"], 2)
        self.assertNotIn("manual-adaptation", report["counts"])
        by_id = {record["module_id"]: record for record in report["records"]}
        self.assertTrue(by_id["bulk-ribosome-profiling"]["executor_ready"])
        self.assertTrue(by_id["bulk-r-loop-mapping"]["executor_ready"])
        self.assertEqual(by_id["bulk-r-loop-mapping"]["level"], "executable")
        cuttag = next(
            row for row in by_id["bulk-r-loop-mapping"]["assay_readiness"]
            if row["assay"] == "cuttag"
        )
        self.assertEqual(cuttag["executor_module_id"], "bulk-chromatin-peak-calling")
        self.assertEqual(len(cuttag["executor_paths"]), 2)


if __name__ == "__main__":
    unittest.main()
