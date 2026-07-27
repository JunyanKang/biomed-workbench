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

    def test_explicit_public_source_lookup_does_not_expand_to_incidental_analysis(self):
        plan = route("retrieve ARCHS4 expression for ACE2")

        self.assertEqual(plan["matched_workflows"], ["evidence"])
        self.assertEqual(plan["selected_module_ids"], ["archs4-expression-evidence"])

    def test_gnomad_constraint_request_routes_to_fixed_gene_constraint_module(self):
        plan = route("查询基因LOEUF")

        self.assertEqual(plan["selected_module_ids"], ["gnomad-gene-constraint-evidence"])
        self.assertEqual(plan["plan_type"], "single")

    def test_restriction_digest_request_routes_to_the_restriction_plan_module(self):
        plan = route("模拟 EcoRI 对环状质粒的限制性酶切片段")

        self.assertEqual(plan["selected_module_ids"], ["restriction-plan"])
        self.assertEqual(plan["plan_type"], "single")

    def test_annotated_genbank_cds_request_routes_to_coding_sequence_extraction(self):
        plan = route("从 GenBank 注释记录提取指定 locus_tag 的 CDS 并核对翻译")

        self.assertEqual(plan["selected_module_ids"], ["genbank-coding-sequence-extraction"])
        self.assertEqual(plan["plan_type"], "single")

    def test_itc_binding_request_routes_to_single_site_fit(self):
        plan = route("对积分 ITC 注射热做单点结合热力学拟合并检查残差")

        self.assertEqual(plan["selected_module_ids"], ["itc-single-site-binding"])
        self.assertEqual(plan["plan_type"], "single")

    def test_fixed_period_cosinor_request_does_not_expand_to_image_tracking(self):
        plan = route("对 24 小时生理时间序列做 cosinor 节律分析")

        self.assertEqual(plan["matched_workflows"], ["clinical"])
        self.assertEqual(plan["selected_module_ids"], ["fixed-period-cosinor"])
        self.assertEqual(plan["plan_type"], "single")

    def test_western_blot_request_routes_to_reviewed_roi_quantification(self):
        plan = route("对已审核 ROI 的 Western blot 条带做内参归一化定量")

        self.assertEqual(plan["selected_module_ids"], ["western-blot-densitometry"])
        self.assertEqual(plan["plan_type"], "single")

    def test_radiotracer_biodistribution_request_routes_to_measurement_summary(self):
        plan = route("计算放射性示踪肿瘤和血液的百分注射剂量每克及肿瘤血液比")

        self.assertEqual(plan["selected_module_ids"], ["radiotracer-biodistribution"])
        self.assertEqual(plan["plan_type"], "single")

    def test_xenograft_tgi_request_routes_to_animal_level_summary(self):
        plan = route("分析异种移植肿瘤生长抑制率 TGI 并保留每只动物数据")

        self.assertEqual(plan["selected_module_ids"], ["xenograft-tumor-growth"])
        self.assertEqual(plan["plan_type"], "single")

    def test_accelerated_stability_request_routes_to_bounded_arrhenius_module(self):
        plan = route("对多温度效价数据做加速稳定性 Arrhenius 外推")

        self.assertEqual(plan["selected_module_ids"], ["accelerated-stability"])
        self.assertEqual(plan["plan_type"], "single")

    def test_cbioportal_study_request_routes_to_exact_study_module(self):
        plan = route("查询 cBioPortal队列信息")

        self.assertEqual(plan["selected_module_ids"], ["cbioportal-study-evidence"])
        self.assertEqual(plan["plan_type"], "single")

    def test_cbioportal_gene_mutation_request_routes_to_bounded_mutation_module(self):
        plan = route("查询 cBioPortal 肿瘤队列中 TP53 的突变")

        self.assertEqual(plan["selected_module_ids"], ["cbioportal-gene-mutation-evidence"])
        self.assertEqual(plan["plan_type"], "single")

    def test_cbioportal_copy_number_request_routes_to_post_filtered_module(self):
        plan = route("查询 cBioPortal 肿瘤队列中 TP53 的拷贝数扩增缺失")

        self.assertEqual(plan["selected_module_ids"], ["cbioportal-gene-copy-number-evidence"])
        self.assertEqual(plan["plan_type"], "single")

    def test_copy_number_coverage_audit_routes_to_quality_summary_module(self):
        plan = route("审计 CNA 队列覆盖度和拷贝数事件构成")

        self.assertEqual(plan["selected_module_ids"], ["copy-number-event-summary"])
        self.assertEqual(plan["plan_type"], "single")

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

    def test_patent_feature_support_request_routes_to_source_support_audit(self):
        plan = route("核对技术特征与专利主张证据映射，并阻断尚未确认的正式主张")

        self.assertEqual(plan["selected_module_ids"], ["patent-claim-support-audit"])
        self.assertEqual(plan["matched_workflows"], ["publication"])
        self.assertEqual(plan["plan_type"], "single")

    def test_chinese_patent_claim_structure_request_routes_to_structure_audit(self):
        plan = route("检查中文专利权利要求编号、引用方向和待确认占位符")

        self.assertEqual(plan["selected_module_ids"], ["patent-claim-structure-audit"])
        self.assertEqual(plan["matched_workflows"], ["publication"])
        self.assertEqual(plan["plan_type"], "single")

    def test_structured_patent_draft_request_routes_to_readiness_audit(self):
        plan = route("审计专利草案完整性和可追溯性")

        self.assertEqual(plan["selected_module_ids"], ["patent-draft-readiness-audit"])
        self.assertEqual(plan["matched_workflows"], ["publication"])
        self.assertEqual(plan["plan_type"], "single")

    def test_patent_flowchart_request_routes_to_svg_delivery(self):
        plan = route("生成专利方法流程图")

        self.assertEqual(plan["selected_module_ids"], ["patent-flowchart-svg"])
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
            ["temporal-integrity-audit", "assertion-citation-coverage-audit"],
        )
        self.assertEqual(plan["plan_type"], "parallel")
        self.assertEqual(plan["steps"][0]["mode"], "parallel")

    def test_broad_research_process_words_do_not_trigger_unrelated_scientific_domains(self):
        plan = route(
            "Validate donor-aware single-cell RNA analysis, revise the hypothesis, "
            "and prepare a publication-grade evidence package.",
            per_workflow=5,
        )

        self.assertEqual(plan["matched_workflows"], ["omics", "publication"])
        self.assertIn("single-cell-donor-inference", plan["selected_module_ids"])
        self.assertNotIn("gene-evidence", plan["selected_module_ids"])
        self.assertNotIn("variant-decompress-bgzip", plan["selected_module_ids"])
        self.assertNotIn("ddr-coexpression-hypothesis-network", plan["selected_module_ids"])
        self.assertNotIn("docking-pose-review", plan["selected_module_ids"])

    def test_prepare_and_evidence_are_not_enough_to_select_docking(self):
        plan = route("Prepare publication evidence from donor-aware single-cell results")

        self.assertNotIn("molecular_design", plan["matched_workflows"])
        self.assertNotIn("docking-pose-review", plan["selected_module_ids"])

    def test_route_output_has_no_source_or_adapter_fields(self):
        plan = route("search TP53 gene evidence")
        serialized = repr(plan).lower()
        self.assertNotIn("source_path", serialized)
        self.assertNotIn("run_policy", serialized)
        self.assertNotIn("adapter", serialized)
        self.assertTrue(all(candidate["selection_reasons"] for step in plan["steps"] for candidate in step["candidates"]))

    def test_compound_coordinate_conversion_and_overlap_stays_on_declared_operations(self):
        plan = route("将一组 hg19 BED 峰坐标转换到 hg38，保留无法映射的区域并检查后续 ATAC 区间重叠")

        self.assertEqual(
            plan["selected_module_ids"],
            ["genome-coordinate-liftover", "interval-overlap-bedtools"],
        )
        self.assertEqual(plan["plan_type"], "serial")
        self.assertNotIn("single-cell-atac-regulatory", plan["selected_module_ids"])
        self.assertNotIn("single-cell-reference-annotation", plan["selected_module_ids"])

    def test_assembly_genome_context_does_not_trigger_construct_or_chemical_modules(self):
        plan = route("用 minimap2 将一个组装基因组与参考基因组比对，检查对齐覆盖并保留未对齐记录")

        self.assertEqual(plan["matched_workflows"], ["omics"])
        self.assertEqual(plan["selected_module_ids"], ["assembly-reference-alignment"])

    def test_pairwise_sequence_alignment_routes_to_its_declared_molecular_operation(self):
        plan = route("pairwise sequence alignment")

        self.assertEqual(plan["matched_workflows"], ["molecular_design"])
        self.assertEqual(plan["selected_module_ids"], ["sequence-pairwise-alignment"])

    def test_open_reading_frame_annotation_routes_to_its_declared_molecular_operation(self):
        plan = route("open reading frame annotation")

        self.assertEqual(plan["matched_workflows"], ["molecular_design"])
        self.assertEqual(plan["selected_module_ids"], ["open-reading-frame-annotation"])

    def test_sequence_variant_localization_routes_to_its_declared_molecular_operation(self):
        plan = route("sequence mutation localization")

        self.assertEqual(plan["matched_workflows"], ["molecular_design"])
        self.assertEqual(plan["selected_module_ids"], ["sequence-variant-localization"])

    def test_pcr_amplicon_simulation_routes_to_its_declared_molecular_operation(self):
        plan = route("PCR amplicon simulation")

        self.assertEqual(plan["matched_workflows"], ["molecular_design"])
        self.assertEqual(plan["selected_module_ids"], ["pcr-amplicon-simulation"])

    def test_rna_secondary_structure_summary_routes_to_its_declared_molecular_operation(self):
        plan = route("RNA secondary structure summary")

        self.assertEqual(plan["matched_workflows"], ["molecular_design"])
        self.assertEqual(plan["selected_module_ids"], ["rna-secondary-structure-summary"])

    def test_aligned_protein_conservation_routes_to_its_declared_molecular_operation(self):
        plan = route("aligned protein conservation")

        self.assertEqual(plan["matched_workflows"], ["molecular_design"])
        self.assertEqual(plan["selected_module_ids"], ["aligned-protein-conservation"])

    def test_cd_thermal_transition_routes_to_its_declared_molecular_operation(self):
        plan = route("circular dichroism thermal transition")

        self.assertEqual(plan["matched_workflows"], ["molecular_design"])
        self.assertEqual(plan["selected_module_ids"], ["cd-thermal-transition-summary"])

    def test_image_translation_registration_routes_to_its_declared_imaging_operation(self):
        plan = route("image translation registration")

        self.assertEqual(plan["matched_workflows"], ["imaging"])
        self.assertEqual(plan["selected_module_ids"], ["image-translation-registration"])


    def test_ortholog_database_request_does_not_imply_a_freshness_audit(self):
        plan = route("将人类 TP53 映射到小鼠同源基因并保留数据库证据")

        self.assertEqual(plan["matched_workflows"], ["evidence"])
        self.assertEqual(
            plan["selected_module_ids"],
            ["gene-identifier-resolution", "gene-ortholog-evidence"],
        )
        self.assertEqual(plan["plan_type"], "serial")



if __name__ == "__main__":
    unittest.main()
