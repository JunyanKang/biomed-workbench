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

    def test_assay_and_construct_intents_select_mature_capabilities(self):
        qpcr = route("分析qPCR相对表达和技术重复")
        assembly = route("检查Golden Gate克隆组装设计")

        self.assertEqual(ids_for(qpcr, "wetlab")[0], "qpcr-relative-expression")
        self.assertEqual(ids_for(assembly, "molecular_design")[0], "golden-gate-plan")

    def test_safety_and_peer_review_intents_select_quality_capabilities(self):
        safety = route("汇总临床试验不良事件和严重性")
        review = route("以Nature审稿人标准评审论文主张与证据")

        self.assertEqual(ids_for(safety, "clinical")[0], "adverse-event-summary")
        self.assertEqual(ids_for(review, "publication")[0], "reviewer-assessment")

    def test_source_review_window_request_selects_freshness_audit(self):
        plan = route("审计科研来源快照日期和复核期限")

        routed = [candidate["id"] for step in plan["steps"] for candidate in step["candidates"]]
        self.assertEqual(routed[0], "source-freshness-audit")

    def test_citation_resolution_and_gold_set_requests_route_to_new_quality_modules(self):
        citation = route("判断文献解析结果是匹配、标识符未找到还是无法判定")
        evaluation = route("评估分类 gold set 的阈值、逐类指标和回归")

        citation_ids = [candidate["id"] for step in citation["steps"] for candidate in step["candidates"]]
        evaluation_ids = [candidate["id"] for step in evaluation["steps"] for candidate in step["candidates"]]
        self.assertEqual(citation_ids[0], "citation-resolution-adjudication")
        self.assertEqual(evaluation_ids[0], "classification-gold-set-evaluation")
        self.assertEqual(evaluation["matched_workflows"], ["evidence"])
        self.assertEqual(evaluation["plan_type"], "single")

    def test_cross_artifact_contract_request_routes_to_consistency_audit(self):
        plan = route("检查科研项目多份产物之间的字段、版本、规则和镜像一致性")

        routed = [candidate["id"] for step in plan["steps"] for candidate in step["candidates"]]
        self.assertEqual(routed[0], "research-contract-consistency-audit")
        self.assertEqual(plan["matched_workflows"], ["evidence"])
        self.assertEqual(plan["plan_type"], "single")

    def test_claim_provenance_request_routes_to_claim_integrity_audit(self):
        plan = route("核查论文主张与原文证据、实验结果和预设约束的一致性")

        routed = [candidate["id"] for step in plan["steps"] for candidate in step["candidates"]]
        self.assertEqual(routed[0], "claim-evidence-integrity-audit")
        self.assertEqual(plan["matched_workflows"], ["publication"])
        self.assertEqual(plan["plan_type"], "single")

    def test_temporal_integrity_request_routes_to_temporal_audit(self):
        plan = route("审计论文日期、事件顺序、来源版本、适用期和因果时间逻辑")

        self.assertEqual(plan["selected_module_ids"], ["temporal-integrity-audit"])
        self.assertEqual(plan["plan_type"], "single")

    def test_uncited_assertion_request_routes_to_citation_coverage_audit(self):
        plan = route("筛查论文中未引证的经验性、定量、比较和因果主张")

        self.assertEqual(plan["selected_module_ids"], ["assertion-citation-coverage-audit"])
        self.assertEqual(plan["plan_type"], "single")

    def test_reviewer_patch_request_routes_to_revision_lineage(self):
        plan = route("根据审稿意见应用稿件修订补丁并检查修订谱系")

        self.assertEqual(plan["selected_module_ids"], ["manuscript-revision-lineage"])
        self.assertEqual(plan["matched_workflows"], ["publication"])
        self.assertEqual(plan["plan_type"], "single")

    def test_revision_from_raw_blocks_selects_base_and_apply_modules_serially(self):
        plan = route("先为稿件建立修订基稿，再根据审稿意见应用修订补丁", per_workflow=5)

        self.assertEqual(plan["selected_module_ids"], ["manuscript-revision-base", "manuscript-revision-lineage"])
        self.assertEqual(plan["matched_workflows"], ["publication"])
        self.assertEqual(plan["plan_type"], "serial")

    def test_composite_review_selects_independent_audits_in_parallel(self):
        plan = route("同时审查论文时间逻辑和未引证的经验性主张", per_workflow=5)

        self.assertEqual(
            plan["selected_module_ids"],
            ["assertion-citation-coverage-audit", "temporal-integrity-audit"],
        )
        self.assertEqual(plan["plan_type"], "parallel")
        self.assertEqual(plan["steps"][0]["mode"], "parallel")

    def test_route_output_has_no_source_or_adapter_fields(self):
        plan = route("search TP53 gene evidence")
        serialized = repr(plan).lower()
        self.assertNotIn("source_path", serialized)
        self.assertNotIn("run_policy", serialized)
        self.assertNotIn("adapter", serialized)
        self.assertTrue(all(candidate["selection_reasons"] for step in plan["steps"] for candidate in step["candidates"]))


if __name__ == "__main__":
    unittest.main()
