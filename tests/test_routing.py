import unittest

from biomed_workbench.router import route


def ids_for(plan, workflow):
    step = next(item for item in plan["steps"] if item["workflow"] == workflow)
    return [candidate["id"] for candidate in step["candidates"]]


class RoutingTests(unittest.TestCase):
    def test_evidence_crispr_publication_request_is_serial_and_specific(self):
        plan = route("分析TP53基因证据并设计CRISPR验证，最后审计Nature论文", per_workflow=3)
        self.assertEqual(plan["matched_workflows"], ["evidence", "molecular_design", "publication"])
        self.assertEqual(plan["plan_type"], "serial")
        self.assertEqual(ids_for(plan, "evidence")[0], "gene-evidence")
        self.assertEqual(ids_for(plan, "molecular_design")[0], "crispr-design")
        self.assertEqual(ids_for(plan, "publication")[0], "manuscript-audit")

    def test_parallel_analysis_with_publication_is_mixed(self):
        plan = route("并行做单细胞和图像分割，最后写论文", per_workflow=2)
        self.assertEqual(plan["plan_type"], "mixed")
        modes = {step["workflow"]: step["mode"] for step in plan["steps"]}
        self.assertEqual(modes["omics"], "parallel")
        self.assertEqual(modes["imaging"], "parallel")
        self.assertEqual(modes["publication"], "serial")
        self.assertEqual(ids_for(plan, "omics")[0], "single-cell-qc")
        self.assertEqual(ids_for(plan, "imaging")[0], "image-segment")

    def test_single_survival_request_selects_clinical_capability(self):
        plan = route("对这个队列做生存分析")
        self.assertEqual(plan["plan_type"], "single")
        self.assertEqual(ids_for(plan, "clinical")[0], "survival-analysis")

    def test_route_output_has_no_source_or_adapter_fields(self):
        plan = route("search TP53 gene evidence")
        serialized = repr(plan).lower()
        self.assertNotIn("source_path", serialized)
        self.assertNotIn("run_policy", serialized)
        self.assertNotIn("adapter", serialized)


if __name__ == "__main__":
    unittest.main()
