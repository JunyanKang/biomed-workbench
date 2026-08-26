import base64
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from biomed_workbench.capabilities.academic_writing import audit_academic_prose_revision, audit_research_proposal
from biomed_workbench.capabilities.proposal_writing import (
    audit_biomedical_terminology,
    audit_docx_proposal_delivery,
    audit_mechanism_claim_promotion,
    audit_nsfc_proposal,
    prepare_nsfc_proposal_drafting,
    prepare_nsfc_proposal_figure,
)
from biomed_workbench.router import route


def nsfc_input(program_type="general"):
    if program_type in {"general", "young-c"}:
        roles = ["rationale", "research_content", "preliminary"]
    elif program_type in {"young-a", "young-b"}:
        roles = ["academic_achievements", "future_research"]
    else:
        roles = ["rationale", "research_content", "preliminary"]
    sections = []
    for index, role in enumerate(roles, start=1):
        text = "本课题组前期研究支持该科学命题。" if role == "preliminary" else f"{role}科学命题成立。"
        sections.append({
            "id": f"s{index}", "role": role, "heading": f"第{index}部分", "text": text,
            "heading_claim": text.rstrip("。"), "knowledge_change": "区分现有认识与待检验解释",
        })
    payload = {
        "guideline_year": 2026,
        "program_type": program_type,
        "application_code_1": "C1201",
        "research_attribute": "自由探索类基础研究",
        "title_cn": "基质调控视网膜内界膜形成的机制研究",
        "abstract_cn": "本项目研究视网膜内界膜形成及其基质调控机制。",
        "abstract_en": "This project studies retinal inner limiting membrane formation and matrix regulation.",
        "sections": sections,
        "aims": [{
            "id": "A1", "phenotypes": ["ilm"], "mechanisms": ["matrix"], "readouts": ["continuity"],
            "discriminates_alternatives": ["direct", "indirect"], "feasibility_evidence": ["pilot"], "fallback": "orthogonal assay",
        }],
        "core_phenotypes": ["ilm"],
        "central_mechanisms": ["matrix"],
        "official_template": {
            "source": "NSFC Grants System", "sha256": "a" * 64, "guideline_year": 2026,
            "program_type": program_type, "required_semantic_roles": roles,
        },
    }
    return payload


def proposal_evidence_foundation():
    digest = "b" * 64
    return {
        "search_plan": {
            "objective": "界定界面基质形成的直接证据、冲突结果和研究空白",
            "queries": ["retinal interface matrix development", "inner limiting membrane mechanism"],
            "sources": ["PubMed", "Crossref"],
            "date_window": "database inception to 2026-08-26",
            "inclusion_criteria": ["直接研究组织界面形成或相关基质机制"],
            "exclusion_criteria": ["无原始实验或与研究对象无直接关系"],
        },
        "literature_records": [{
            "id": "L1", "stable_id": "doi:10.1000/example", "title": "Interface matrix development",
            "source": "PubMed", "study_design": "controlled-perturbation", "source_level": "full-text",
            "evidence_role": "direct-support", "evidence_relation": "supports", "claim_ids": ["C1"],
            "citation_identity_status": "verified_match", "content_review_status": "full-text-reviewed",
            "retraction_status": "not-retracted",
        }],
        "database_records": [{
            "module_id": "hpo-term-evidence", "record_id": "HP:0000001", "source_version": "ols4-current",
            "accessed_at": "2026-08-26", "claim_ids": ["C2"], "evidence_relation": "context",
        }],
        "research_gap": {
            "statement": "候选调控过程如何影响界面基质装配尚未被直接检验。",
            "coverage_basis": "两来源检索及核心原文审阅",
            "conflicting_evidence": ["细胞命运改变与基质装配异常均可解释表型"],
            "why_existing_work_is_insufficient": "既有工作没有用判别性干预区分两种解释。",
            "testable_consequence": "若中心假说成立，装配异常应先于细胞命运改变出现。",
        },
        "upstream_receipts": [
            {"module_id": module_id, "status": "passed", "output_digest": digest}
            for module_id in (
                "literature-evidence", "literature-landscape-audit", "citation-record-resolution",
                "citation-resolution-adjudication", "claim-evidence-integrity-audit", "hpo-term-evidence",
            )
        ],
    }


class NsfcProposalWritingTests(unittest.TestCase):
    @staticmethod
    def _proposal_figure_input():
        path = Path(__file__).resolve().parents[1] / "biomed_workbench" / "modules" / "builtin" / "nsfc-proposal-figure-development" / "tests" / "cases.json"
        return json.loads(path.read_text(encoding="utf-8"))["cases"][0]["input"]

    def test_drafting_package_requires_actual_prose_delivery(self):
        result = prepare_nsfc_proposal_drafting(
            guideline_year=2026, program_type="general", mode="compose",
            scope={"deliverable":"申请书","target_reader":"生命科学同行评议专家","language":"Chinese","version_target":"draft"},
            research_canon=[{"id":"F1","statement":"直接研究支持界面基质参与发育。"},{"id":"F2","statement":"数据库记录相关表型。"},{"id":"F3","statement":"前期观察支持可行性。"}],
            evidence_table=[
                {"claim_id":"C1","claim":"界面基质参与发育。","status":"direct-study","source_ids":["F1"]},
                {"claim_id":"C2","claim":"数据库表型提供研究线索。","status":"database-phenotype","source_ids":["F2"]},
                {"claim_id":"C3","claim":"前期观察支持项目可行。","status":"preliminary-data","source_ids":["F3"]},
            ],
            argument_map={"scientific_tension":"表型明确但机制未知","central_question":"界面基质如何形成？","central_hypothesis":"候选分子影响基质装配","knowledge_advance":"建立分子调控与组织界面形成的联系","alternative_explanations":["细胞命运改变","基质装配异常"],"core_phenotypes":["ilm"],"central_mechanisms":["matrix"]},
            section_contracts=[
                {"id":"S1","role":"rationale","purpose":"提出问题","scientific_question":"为何形成异常？","claim_ids":["C1","C2"],"evidence_ids":["F1","F2"]},
                {"id":"S2","role":"research_content","purpose":"检验假说","scientific_question":"如何影响装配？","claim_ids":["C2","C3"],"evidence_ids":["F2","F3"]},
                {"id":"S3","role":"preliminary","purpose":"证明可行性","scientific_question":"哪些步骤可行？","claim_ids":["C3"],"evidence_ids":["F3"]},
            ],
            aims=[{"id":"A1","objective":"检验基质装配","hypothesis":"候选分子影响装配","phenotypes":["ilm"],"mechanisms":["matrix"],"approach":"遗传与生化互证","readouts":["连续性"],"alternative_models":["直接","间接"],"feasibility_evidence":["F3"],"fallback":"正交读出"}],
            evidence_foundation=proposal_evidence_foundation(),
            official_template={"source":"NSFC Grants System","sha256":"a"*64,"guideline_year":2026,"program_type":"general","required_semantic_roles":["rationale","research_content","preliminary"]},
        )
        self.assertTrue(result["ready_for_section_drafting"])
        self.assertTrue(result["agent_delivery_contract"]["audit_only_delivery_forbidden"])
        self.assertIn("drafted_or_revised_prose", result["agent_delivery_contract"]["final_response_must_include"])
        self.assertIn("assertion-citation-coverage-audit", result["agent_delivery_contract"]["post_draft_review_modules"])
        self.assertEqual(result["evidence_foundation_summary"]["literature_record_count"], 1)

    def test_drafting_blocks_an_unexecuted_evidence_workflow(self):
        foundation = proposal_evidence_foundation()
        foundation["upstream_receipts"] = []
        result = prepare_nsfc_proposal_drafting(
            guideline_year=2026, program_type="general", mode="compose",
            scope={"deliverable":"申请书","target_reader":"同行评议专家","language":"Chinese","version_target":"draft"},
            research_canon=[{"id":"F1","statement":"直接研究支持界面形成。"}],
            evidence_table=[{"claim_id":"C1","claim":"界面基质参与发育。","status":"direct-study","source_ids":["F1"]}],
            argument_map={"scientific_tension":"表型明确但机制未知","central_question":"界面如何形成？","central_hypothesis":"候选过程影响装配","knowledge_advance":"建立调控联系","alternative_explanations":["直接","间接"]},
            section_contracts=[
                {"id":"S1","role":"rationale","purpose":"提出问题","scientific_question":"为何异常？","claim_ids":["C1"],"evidence_ids":["F1"]},
                {"id":"S2","role":"research_content","purpose":"检验假说","scientific_question":"如何装配？","claim_ids":["C1"],"evidence_ids":["F1"]},
                {"id":"S3","role":"preliminary","purpose":"证明可行","scientific_question":"是否可行？","claim_ids":["C1"],"evidence_ids":["F1"]},
            ],
            aims=[{"id":"A1","objective":"检验装配","hypothesis":"候选过程影响装配","approach":"遗传干预","readouts":["连续性"],"alternative_models":["直接","间接"],"feasibility_evidence":["F1"],"fallback":"正交读出"}],
            evidence_foundation=foundation,
            official_template={"source":"NSFC Grants System","sha256":"a"*64,"guideline_year":2026,"program_type":"general","required_semantic_roles":["rationale","research_content","preliminary"]},
        )
        self.assertFalse(result["ready_for_section_drafting"])
        self.assertIn("proposal-evidence-workflow-incomplete", {item["code"] for item in result["findings"]})

    def test_proposal_figure_prompt_is_programme_specific_visual_and_editable(self):
        payload = self._proposal_figure_input()
        result = prepare_nsfc_proposal_figure(**payload)
        self.assertTrue(result["ready_for_proposal_insertion"])
        self.assertIn("青年 C", result["programme_figure_emphasis"]["story"])
        self.assertIn("do not reduce the composition to generic boxes", result["prompt_package"]["imagegen_reference_prompt"])
        self.assertIn("declared z-order", result["prompt_package"]["editable_reconstruction_prompt"])
        self.assertIn("regional density and whitespace", result["prompt_package"]["editable_reconstruction_prompt"])
        self.assertEqual(result["prompt_package"]["required_reconstruction_runtime"], "image-to-editable-ppt")
        self.assertEqual(result["renderer_plan"]["quantitative_panels"], "publication-figure-package or analysis-specific renderer")

    def test_text_box_only_proposal_figure_is_blocked(self):
        payload = self._proposal_figure_input()
        payload["visual_plan"]["biological_assets"] = []
        payload["visual_plan"]["visual_balance"] = {"non_text_visual_fraction": 0.2, "scale_layers": ["text"]}
        payload["qa_rounds"] = []
        result = prepare_nsfc_proposal_figure(**payload)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("proposal-figure-visual-elements-insufficient", codes)
        self.assertIn("proposal-figure-text-dominant", codes)
        self.assertFalse(result["ready_for_generation"])

    def test_proposal_figure_blocks_unsafe_layers_redundancy_and_unbalanced_space(self):
        payload = self._proposal_figure_input()
        assets = payload["visual_plan"]["biological_assets"]
        assets[1]["distinct_information"] = assets[0]["distinct_information"]
        assets[1].pop("label")
        balance = payload["visual_plan"]["visual_balance"]
        balance["typography"] = {
            "font_families": ["Arial", "Times New Roman", "Calibri"],
            "font_size_levels_pt": {"a": 11, "b": 9, "c": 7},
            "font_colors": ["#111111", "#222222", "#333333", "#444444"],
        }
        balance["layer_order"] = ["background", "labels", "biological-assets", "connectors", "legend"]
        balance["correspondence_groups"] = []
        balance["region_densities"] = [
            {"region": "left", "information_density": 0.92},
            {"region": "center", "information_density": 0.50},
            {"region": "right", "information_density": 0.08},
        ]
        balance["whitespace_fraction"] = 0.65
        result = prepare_nsfc_proposal_figure(**payload)
        codes = {item["code"] for item in result["findings"]}
        for code in (
            "proposal-figure-redundant-elements", "proposal-figure-element-label-missing",
            "proposal-figure-typography-inconsistent", "proposal-figure-layer-order-unsafe",
            "proposal-figure-correspondence-unmapped", "proposal-figure-spatial-balance-invalid",
        ):
            self.assertIn(code, codes)
        self.assertFalse(result["ready_for_generation"])

    def test_proposal_figure_requires_complete_final_visual_qa(self):
        payload = self._proposal_figure_input()
        payload["qa_rounds"][-1]["z_order_checked"] = False
        result = prepare_nsfc_proposal_figure(**payload)
        self.assertTrue(result["ready_for_generation"])
        self.assertFalse(result["ready_for_proposal_insertion"])

    def test_proposal_figure_blocks_width_overflow_and_offset_paragraph(self):
        payload = self._proposal_figure_input()
        payload["output_contract"]["final_width_mm"] = 170
        payload["output_contract"]["text_area_width_mm"] = 165
        payload["output_contract"]["figure_paragraph_alignment"] = "left"
        payload["output_contract"]["figure_paragraph_prefix"] = "\t"
        result = prepare_nsfc_proposal_figure(**payload)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("proposal-figure-exceeds-text-area", codes)
        self.assertIn("proposal-figure-paragraph-placement-invalid", codes)
        self.assertFalse(result["ready_for_generation"])

    def test_complex_proposal_request_routes_complete_evidence_chain(self):
        result = route(
            "为生命医学项目撰写国家自然科学基金面上项目申请书，需要系统检索文献、核验引用、判断研究空白、整合前期数据和公共数据库证据并形成科学假说。",
            per_workflow=10,
        )
        selected = result["selected_module_ids"]
        self.assertEqual(result["matched_workflows"], ["evidence", "publication"])
        self.assertNotIn("comparative-sequence-phylogeny", selected)
        for module_id in (
            "literature-evidence", "citation-record-resolution", "literature-landscape-audit",
            "citation-resolution-adjudication", "claim-evidence-integrity-audit",
            "nsfc-proposal-development", "nsfc-proposal-figure-development",
        ):
            self.assertIn(module_id, selected)

    def test_nsfc_does_not_inherit_us_nsf_review_criteria(self):
        result = audit_research_proposal(
            mode="compose", agency="NSFC",
            scope={"deliverable":"申请书","target_reader":"同行评议专家","language":"Chinese","constraints":"2026 template","version_target":"v1"},
            research_canon=[{"id":"F1","fact":"前期实验可行。"}],
            evidence_table=[{"claim_id":"C1","claim":"实验可行。","status":"evidence-backed","source_ids":["F1"]}],
            argument_map={"scientific_tension":"机制未知","central_question":"机制是什么？","central_thesis":"检验候选机制。","limitations":["单一模型"]},
            section_contracts=[{"id":"S1","purpose":"立项依据","inputs":["F1"],"allowed_claims":["C1"],"forbidden_claims":["因果"],"required_evidence":["F1"],"validation":["核对"]}],
            aims=[{"id":"A1","objective":"确定机制","rationale":"机制未知","approach":"扰动与正交读出","expected_outcome":"区分模型","feasibility_evidence":["F1"],"independence":"可独立解释","fallback":"替代读出"}],
            review_criteria=["科学问题", "创新性", "可行性"],
        )
        codes = {item["code"] for item in result["findings"]}
        self.assertNotIn("nsf-review-criteria-missing", codes)

    def test_all_seven_nsfc_program_profiles_are_distinct(self):
        expected = {
            "young-c":"青年科学基金项目（C类）", "young-b":"青年科学基金项目（B类）",
            "young-a":"青年科学基金项目（A类）", "general":"面上项目", "regional":"地区科学基金项目",
            "key":"重点项目", "major":"重大项目",
        }
        for program_type, name in expected.items():
            result = audit_nsfc_proposal(**nsfc_input(program_type))
            self.assertEqual(result["agency_profile"]["program_profile"]["name_zh"], name)
        self.assertEqual(
            audit_nsfc_proposal(**nsfc_input("general"))["agency_profile"]["program_profile"]["publicly_confirmed_page_limit"]["value"],
            30,
        )
        self.assertIsNone(audit_nsfc_proposal(**nsfc_input("young-b"))["agency_profile"]["program_profile"]["publicly_confirmed_page_limit"])

    def test_unbound_template_is_blocked(self):
        payload = nsfc_input("young-c")
        payload["official_template"] = {}
        result = audit_nsfc_proposal(**payload)
        codes = {item["code"] for item in result["official_rule_findings"]}
        self.assertIn("current-official-template-not-bound", codes)

    def test_human_disease_relevance_requires_genetic_bridge_fields(self):
        payload = nsfc_input()
        payload["human_genetics_context"] = {"human_relevance_claimed": True, "evidence_rows": []}
        result = audit_nsfc_proposal(**payload)
        self.assertIn("human-genetics-evidence-missing", {item["code"] for item in result["semantic_findings"]})
        self.assertEqual(result["human_genetics_summary"]["recommended_source_modules"], ["variant-evidence", "hpo-term-evidence", "gene-evidence"])

    def test_abstract_citations_and_section_contamination_are_blocked(self):
        payload = nsfc_input()
        payload["abstract_cn"] += "[1]"
        payload["sections"][0]["text"] += "本项目将检测三个指标。"
        result = audit_nsfc_proposal(**payload)
        codes = {item["code"] for item in result["semantic_findings"]}
        self.assertIn("abstract-numeric-citation", codes)
        self.assertIn("method-contamination-in-rationale", codes)

    def test_col2a1_and_col9a1_stay_candidate_without_direct_substrate_evidence(self):
        result = audit_mechanism_claim_promotion(claims=[
            {"claim_id":"C2","entity":"COL2A1","section":"title","requested_level":"substrate","evidence_types":["coexpression","spatial_colocalization"]},
            {"claim_id":"C9","entity":"COL9A1","section":"hypothesis","requested_level":"mechanism","evidence_types":["physical_interaction"]},
        ])
        self.assertFalse(result["all_claims_within_evidence"])
        self.assertTrue(all(not row["promotion_allowed"] for row in result["decisions"]))

    def test_nomenclature_allows_scientific_relation_dash_but_blocks_internal_jargon(self):
        clean = audit_biomedical_terminology(
            text="视网膜内界膜（ILM）位于玻璃体—视网膜界面。", terminology=[{"concept_id":"ilm","preferred":"视网膜内界膜","abbreviation":"ILM","entity_type":"structure"}], document_section="rationale",
        )
        self.assertNotIn("rhetorical-em-dash", {item["code"] for item in clean["findings"]})
        blocked = audit_biomedical_terminology(
            text="本段通过证据链和 promotion gate 完成门控。", terminology=[{"concept_id":"x","preferred":"本段"}], document_section="rationale",
        )
        self.assertIn("internal-workflow-language", {item["code"] for item in blocked["findings"]})
        unnatural = audit_biomedical_terminology(
            text="这些信息仍属于候选形成依据，并采用递进判定。", terminology=[{"concept_id":"x","preferred":"候选"}], document_section="rationale",
        )
        self.assertIn("unnatural-governance-phrase", {item["code"] for item in unnatural["findings"]})

    def test_section_role_scope_and_model_order_are_checked(self):
        payload = nsfc_input()
        payload["sections"][0]["paragraphs"] = [{"id":"p1","role":"quality_control","text":"同步检测质量指标。"}]
        payload["aims"] = [
            {"id":"A0","phenotypes":["ilm"],"mechanisms":[],"readouts":["thickness"],"discriminates_alternatives":["direct","indirect"],"feasibility_evidence":["pilot"],"fallback":"histology","scope_role":"broad-survey"},
            {"id":"A1","phenotypes":["ilm"],"mechanisms":["matrix"],"readouts":["continuity"],"discriminates_alternatives":["direct","indirect"],"feasibility_evidence":["pilot"],"fallback":"orthogonal","model_type":"conditional-knockout","requires_prior_global_phenotype":True,"depends_on_aim_ids":[]},
        ]
        codes = {item["code"] for item in audit_nsfc_proposal(**payload)["semantic_findings"]}
        self.assertIn("paragraph-section-role-mismatch", codes)
        self.assertIn("aim-scope-expansion", codes)
        self.assertIn("conditional-model-order-unresolved", codes)

    def test_academic_prose_does_not_flag_biochemical_relation_dash(self):
        result = audit_academic_prose_revision(
            original_text="YAP/TAZ—TEAD activity was measured.",
            document_type="grant-proposal", section_kind="rationale", target_venue="NSFC",
        )
        self.assertNotIn("em-dash", {item["code"] for item in result["findings"]})

    def test_summary_spreadsheet_proposal_does_not_route_to_patent_or_single_cell_execution(self):
        result = route("根据整理后的单细胞结果汇总表 results.xlsx 审查国自然申请书", per_workflow=10)
        self.assertTrue(result["artifact_context"]["interpretation_only"])
        self.assertFalse(any(module_id.startswith("single-cell-") for module_id in result["selected_module_ids"]))
        self.assertFalse(any("patent" in module_id for module_id in result["selected_module_ids"]))

    def test_native_docx_citation_reciprocity_and_render_gate(self):
        document_xml = """<?xml version='1.0' encoding='UTF-8' standalone='yes'?>
        <w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body>
        <w:p><w:r><w:t>摘要</w:t></w:r></w:p><w:p><w:r><w:t>本项目研究明确问题。</w:t></w:r></w:p>
        <w:p><w:r><w:t>立项依据</w:t></w:r></w:p><w:p><w:r><w:t>既往研究支持该观察[1]。</w:t></w:r></w:p>
        <w:p><w:r><w:t>参考文献</w:t></w:r></w:p><w:p><w:r><w:t>[1] Author. Title. 2025.</w:t></w:r></w:p>
        </w:body></w:document>"""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "proposal.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'/>")
                archive.writestr("word/document.xml", document_xml)
            result = audit_docx_proposal_delivery(docx_path=str(path), rendered_pages=[{
                "page_number":1,"image_sha256":"b"*64,"reviewed":True,"clipping_free":True,
                "overlap_free":True,"legible":True,"figure_final_size_checked":True,"page_breaks_reviewed":True,"caption_figure_same_page":True,
                "figures_within_text_width":True,"figure_paragraphs_centered":True,"figure_paragraphs_placeholder_free":True,
            }], style_policy={"allowed_fonts":["宋体","Times New Roman"],"minimum_size_half_points":18,"allowed_colors":["000000"]})
        self.assertTrue(result["ready_for_submission_delivery"])
        self.assertEqual(result["citation_sequence"], [1])

    def test_docx_blocks_missing_final_size_figure_review(self):
        result = audit_docx_proposal_delivery(
            document_model=[{"text":"立项依据"},{"text":"证据[1]。"},{"text":"参考文献"},{"text":"[1] Ref."}],
            rendered_pages=[{"page_number":1,"image_sha256":"c"*64,"reviewed":True,"clipping_free":True,"overlap_free":True,"legible":True,"figure_final_size_checked":False,"page_breaks_reviewed":True,"caption_figure_same_page":True,"figures_within_text_width":True,"figure_paragraphs_centered":True,"figure_paragraphs_placeholder_free":True}],
            style_policy={"allowed_fonts":["宋体"],"minimum_size_half_points":18,"allowed_colors":["000000"]},
        )
        self.assertFalse(result["ready_for_submission_delivery"])
        self.assertIn("rendered-page-quality-failed", {item["code"] for item in result["findings"]})

    def test_docx_blocks_figure_overflow_offset_and_placeholder_content(self):
        result = audit_docx_proposal_delivery(
            document_model=[
                {"text":"立项依据"},
                {"text":"证据[1]。"},
                {
                    "text":"", "raw_text":" ", "drawing_count":1,
                    "paragraph_alignment":"left", "tab_count":1,
                    "paragraph_indentation_twips":{"left":120},
                    "text_area_width_mm":160,
                    "drawing_extents":[{"width_mm":170,"height_mm":90}],
                },
                {"text":"图1 科学假说图", "style_id":"Caption"},
                {"text":"参考文献"},
                {"text":"[1] Ref."},
            ],
            rendered_pages=[{
                "page_number":1,"image_sha256":"e"*64,"reviewed":True,"clipping_free":True,
                "overlap_free":True,"legible":True,"figure_final_size_checked":True,
                "page_breaks_reviewed":True,"caption_figure_same_page":True,
                "figures_within_text_width":False,"figure_paragraphs_centered":False,
                "figure_paragraphs_placeholder_free":False,
            }],
            style_policy={"allowed_fonts":["宋体"],"minimum_size_half_points":18,"allowed_colors":["000000"]},
        )
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("figure-paragraph-not-centered", codes)
        self.assertIn("figure-paragraph-placeholder-present", codes)
        self.assertIn("figure-exceeds-text-boundary", codes)
        self.assertIn("rendered-page-quality-failed", codes)
        self.assertFalse(result["ready_for_submission_delivery"])

    def test_docx_can_create_a_separate_renumbered_copy(self):
        document_xml = """<?xml version='1.0' encoding='UTF-8' standalone='yes'?>
        <w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body>
        <w:p><w:r><w:t>立项依据</w:t></w:r></w:p><w:p><w:r><w:t>甲[4]，乙[2]。</w:t></w:r></w:p>
        <w:p><w:r><w:t>参考文献</w:t></w:r></w:p><w:p><w:r><w:t>[2] Ref B.</w:t></w:r></w:p><w:p><w:r><w:t>[4] Ref A.</w:t></w:r></w:p>
        </w:body></w:document>"""
        package = io.BytesIO()
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'/>")
            archive.writestr("word/document.xml", document_xml)
        result = audit_docx_proposal_delivery(
            docx_payload_base64=base64.b64encode(package.getvalue()).decode("ascii"),
            renumber_citations=True,
            rendered_pages=[{"page_number":1,"image_sha256":"d"*64,"reviewed":True,"clipping_free":True,"overlap_free":True,"legible":True,"figure_final_size_checked":True,"page_breaks_reviewed":True,"caption_figure_same_page":True,"figures_within_text_width":True,"figure_paragraphs_centered":True,"figure_paragraphs_placeholder_free":True}],
            style_policy={"allowed_fonts":["宋体"],"minimum_size_half_points":18,"allowed_colors":["000000"]},
        )
        self.assertTrue(result["renumbered_docx_base64"])
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(result["renumbered_docx_base64"]))) as archive:
            rewritten = archive.read("word/document.xml").decode("utf-8")
        self.assertIn("甲[1]，乙[2]", rewritten)
        self.assertIn("[1] Ref A", rewritten)
        self.assertLess(rewritten.index("[1] Ref A"), rewritten.index("[2] Ref B"))


if __name__ == "__main__":
    unittest.main()
