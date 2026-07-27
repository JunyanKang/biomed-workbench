import unittest

from biomed_workbench.research_plan import compile_research_plan


class ResearchPlanTests(unittest.TestCase):
    def test_plan_exposes_contracts_without_claiming_execution(self):
        plan = compile_research_plan("Import FCS flow cytometry data and apply a gating plan")

        self.assertEqual(plan["selected_module_ids"], ["fcs-event-import", "flow-cytometry-summary"])
        self.assertIn("not an execution record", plan["execution_boundary"])
        importer = next(item for item in plan["modules"] if item["id"] == "fcs-event-import")
        downstream = next(item for item in plan["modules"] if item["id"] == "flow-cytometry-summary")
        self.assertEqual(importer["project_inputs"][0]["artifact_type"], "flow_cytometry_acquisition")
        self.assertEqual(importer["execution"]["kind"], "python")
        self.assertIn("fcs_path", importer["input_schema"]["properties"])
        self.assertEqual(importer["execution_templates"][0]["path"], "templates/run_fcs_event_import.py")
        self.assertEqual(downstream["upstream_inputs"][0]["artifact_type"], "cytometry_event_table")
        self.assertEqual(downstream["depends_on"], ["fcs-event-import"])
        self.assertNotIn("NCBI_API_KEY", str(plan))

    def test_selected_producer_satisfies_a_project_or_upstream_interval_port(self):
        plan = compile_research_plan("将一组 hg19 BED 峰坐标转换到 hg38，保留无法映射的区域并检查后续 ATAC 区间重叠")

        overlap = next(item for item in plan["modules"] if item["id"] == "interval-overlap-bedtools")
        query = next(item for item in overlap["upstream_inputs"] if item["name"] == "query_intervals")
        self.assertEqual(query["selected_upstream_module_id"], "genome-coordinate-liftover")
        self.assertNotIn("query_intervals", {item["name"] for item in plan["unresolved_project_inputs"] if item["module_id"] == "interval-overlap-bedtools"})
        self.assertNotIn("query_intervals", {item["name"] for item in plan["unresolved_required_inputs"] if item["module_id"] == "interval-overlap-bedtools"})

    def test_immunophenotype_plan_binds_event_and_gate_producers(self):
        plan = compile_research_plan("quantify flow cytometry immunophenotype")

        module = next(item for item in plan["modules"] if item["id"] == "flow-immunophenotype-summary")
        bindings = {item["name"]: item["selected_upstream_module_id"] for item in module["upstream_inputs"]}
        self.assertEqual(bindings, {"events": "fcs-event-import", "gates": "flow-cytometry-summary"})


if __name__ == "__main__":
    unittest.main()
