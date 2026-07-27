import unittest

from biomed_workbench.capabilities.publication import (
    citation_audit,
    figure_specification,
    manuscript_audit,
    patent_disclosure_audit,
    patent_claim_support_audit,
    patent_claim_structure_audit,
    patent_draft_readiness_audit,
    render_patent_flowchart_svg,
    presentation_delivery_plan,
    response_matrix,
)


class PublicationCapabilityTests(unittest.TestCase):
    def test_manuscript_audit_checks_structure_claims_and_reproducibility(self):
        result = manuscript_audit(
            sections={"abstract": "A", "introduction": "I", "results": "R", "discussion": "D", "methods": "M"},
            claims=[{"claim": "TP53 changes fate", "citation_count": 0, "evidence": "observational"}],
            figure_count=2,
            data_availability=False,
            code_availability=False,
        )
        codes = {finding["code"] for finding in result["findings"]}
        self.assertIn("UNGROUNDED_CLAIM", codes)
        self.assertIn("DATA_AVAILABILITY_MISSING", codes)
        self.assertIn("CODE_AVAILABILITY_MISSING", codes)
        self.assertEqual(result["structure"]["missing"], [])

    def test_citation_audit_detects_missing_fields_and_duplicate_doi(self):
        result = citation_audit(
            [
                {"authors": "A", "title": "Paper", "year": 2020, "journal": "J", "doi": "10.1000/xyz"},
                {"authors": "B", "title": "Other", "year": 2021, "journal": "K", "doi": "https://doi.org/10.1000/XYZ"},
                {"authors": "", "title": "Incomplete", "year": None, "journal": ""},
            ]
        )
        self.assertEqual(result["duplicate_dois"], ["10.1000/xyz"])
        self.assertEqual(result["references"][2]["missing_fields"], ["authors", "year", "journal"])

    def test_response_matrix_preserves_every_comment_and_action(self):
        result = response_matrix(
            [
                {"reviewer": "1", "comment": "Add validation", "response": "Added experiment", "action": "New Fig. 3", "status": "completed"},
                {"reviewer": "2", "comment": "Clarify statistics", "response": "Pending", "action": "Revise methods", "status": "planned"},
            ]
        )
        self.assertEqual(result["comment_count"], 2)
        self.assertEqual(result["status_counts"], {"completed": 1, "planned": 1})
        self.assertEqual(result["unresolved_indices"], [2])

    def test_figure_specification_requires_panel_claim_and_source(self):
        result = figure_specification(
            title="Regulatory failure",
            panels=[
                {"label": "a", "claim": "Cell-state shift", "data_source": "single-cell matrix", "plot": "UMAP"},
                {"label": "b", "claim": "", "data_source": "", "plot": "bar"},
            ],
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["panel_findings"][0]["label"], "b")

    def test_patent_disclosure_audit_separates_enablement_and_prior_art(self):
        result = patent_disclosure_audit(
            problem="Improve retinal differentiation",
            solution="Controlled perturbation",
            essential_features=["timing", "dose"],
            examples=[],
            alternatives=["small molecule"],
            prior_art=[] ,
        )
        codes = {finding["code"] for finding in result["findings"]}
        self.assertIn("ENABLEMENT_EXAMPLES_MISSING", codes)
        self.assertIn("PRIOR_ART_SEARCH_MISSING", codes)

    def test_patent_claim_support_blocks_confirmation_pending_features(self):
        result = patent_claim_support_audit(
            [{"id": "P001", "text": "A disclosed method step."}, {"id": "E001", "text": "A supporting equation."}],
            [{"id": "T001", "text": "Declared step", "support_state": "explicit", "source_ids": ["P001"]}, {"id": "T002", "text": "Unverified extension", "support_state": "needs-confirmation", "source_ids": ["E001"]}],
            [{"id": "CL001", "text": "A method comprising the declared step.", "feature_ids": ["T001"]}, {"id": "CL002", "text": "A method comprising the extension.", "feature_ids": ["T002"]}],
        )
        self.assertTrue(result["claims"][0]["status"] == "admissible")
        self.assertFalse(result["ready_for_formal_claims"])
        self.assertEqual(result["findings"][0]["claim_id"], "CL002")

    def test_patent_claim_structure_audit_blocks_forward_references_and_placeholders(self):
        result = patent_claim_structure_audit(
            "1. 一种方法，其特征在于，包括步骤A。\n"
            "2. 根据权利要求3所述的方法，其特征在于，步骤B[待确认：条件]。\n"
            "3. 根据权利要求1所述的方法，其特征在于，获得更优结果。"
        )
        codes = {finding["code"] for finding in result["findings"]}
        self.assertIn("FORWARD_CLAIM_REFERENCE", codes)
        self.assertIn("FORMAL_CLAIM_PLACEHOLDER", codes)
        self.assertIn("RESULT_LANGUAGE", codes)
        self.assertFalse(result["ready_for_formal_review"])

    def test_patent_claim_structure_audit_warns_on_transition_length_and_antecedent_basis(self):
        result = patent_claim_structure_audit("1. 所述光学器件。")

        codes = {finding["code"] for finding in result["findings"]}
        self.assertIn("TRANSITION_MISSING", codes)
        self.assertIn("CLAIM_TOO_SHORT", codes)
        self.assertIn("POSSIBLE_ANTECEDENT_BASIS_MISSING", codes)
        self.assertTrue(result["ready_for_formal_review"])

    def test_patent_draft_readiness_audit_requires_cross_field_traceability(self):
        draft = {
            "title": "一种样品处理方法", "metadata": {}, "source_analysis": {"contains_core_formulas": False, "formula_count_in_source": 0},
            "source_map": [{"id": "P001", "locator": "page 1", "summary": "Method disclosure"}], "terminology_ledger": [],
            "formula_inventory": [], "figure_inventory": [],
            "evidence_ledger": [{"id": "F1", "support_status": "explicit", "source_ids": ["P001"]}],
            "claims": [{"number": 1, "text": "一种样品处理方法，其特征在于，包括S1：获取样品并记录处理输出。"}],
            "claim_feature_map": [{"claim_number": 1, "feature": "获取样品并记录处理输出", "evidence_ids": ["F1"]}],
            "figures": [{"number": 1, "type": "flowchart", "orientation": "vertical", "claim_number": 1, "complete_claim_flow": True, "source_ids": ["P001"], "nodes": [{"id": "S1", "claim_step": "S1", "label": "记录样品处理输出"}], "edges": []}],
            "abstract_figure_number": 1,
            "specification": {"technical_field": ["样品处理"], "background": ["现有技术"], "embodiments": [{"heading": "实施例1"}], "figure_descriptions": ["图1为方法流程图"], "equations": [], "invention_content": {"problem": ["提高可追溯性"], "solution": ["记录处理输出"], "beneficial_effects": ["保留过程信息"]}},
            "abstract": "本发明涉及一种样品处理方法。",
            "quality_assessment": {"status": "review-draft", "scores": {
                "evidence_support": {"score": 4, "evidence": "Feature maps to source."}, "claim_architecture": {"score": 4, "evidence": "One closed method claim."},
                "terminology_consistency": {"score": 4, "evidence": "No aliases are declared."}, "enablement_detail": {"score": 3, "evidence": "Embodiment is declared."},
                "technical_effect_reasoning": {"score": 3, "evidence": "Effect follows recorded output."}, "figure_alignment": {"score": 4, "evidence": "Figure presents the claim output."}
            }},
        }
        accepted = patent_draft_readiness_audit(draft)
        rejected = patent_draft_readiness_audit({})
        self.assertTrue(accepted["ready_for_professional_review"])
        self.assertEqual(accepted["error_count"], 0)
        self.assertFalse(rejected["ready_for_professional_review"])
        self.assertGreater(rejected["error_count"], 0)

    def test_patent_draft_readiness_audit_checks_figure_inventory_source_and_disposition(self):
        result = patent_draft_readiness_audit({"figure_inventory": [{"source_id": "F001"}]})
        codes = {finding["code"] for finding in result["findings"]}
        self.assertIn("UNKNOWN_FIGURE_INVENTORY_SOURCE", codes)
        self.assertIn("FIGURE_DISPOSITION_MISSING", codes)

    def test_patent_flowchart_renderer_returns_parseable_nonblank_svg(self):
        result = render_patent_flowchart_svg({"number": 1, "type": "flowchart", "orientation": "vertical", "title": "样品处理流程", "nodes": [{"id": "S1", "label": "获取样品"}, {"id": "S2", "label": "记录处理输出"}], "edges": [{"from": "S1", "to": "S2"}]})
        self.assertGreater(len(result["svg"]), 500)
        self.assertTrue(result["quality_gates"]["svg_nonblank_and_parseable"])

    def test_presentation_delivery_plan_builds_slide_sequence_and_module_chain(self):
        result = presentation_delivery_plan(
            project_goal="Show that treatment improves hematopoietic differentiation quality.",
            target_audience="Developmental biology principal investigators",
            storyline="From lineage evidence to translational insight.",
            key_findings=[
                {"claim": "Treatment shifted HSC fate toward myeloid lineage.", "evidence": "Cell counts and DE genes in independent donors."},
                {"claim": "Trajectory velocity supports state transition timing shift.", "evidence": "scVelo-based pseudotime and driver gene ranking."},
            ],
            figures=[{"title": "Figure 1", "type": "UMAP"}, {"title": "Figure 2", "type": "trajectory"}],
            reviewer_feedback=[{"status": "completed", "action": "add donor info", "comment": "Add donor table."}],
            manuscript_inputs={"evidence_map": {"claim_to_evidence": True}},
            available_modules=["figure-specification", "manuscript-audit", "citation-audit", "claim-evidence-integrity-audit", "manuscript-revision-base", "response-matrix", "manuscript-revision-lineage"],
        )
        self.assertEqual(result["delivery_mode"], "single-presentation")
        self.assertEqual(len(result["slide_plan"]), 2)
        self.assertTrue(result["findings"][0]["status"] == "valid")
        self.assertTrue(result["readiness"]["ready_for_delivery"])

    def test_presentation_delivery_plan_flags_missing_evidence_and_blocks(self):
        result = presentation_delivery_plan(
            project_goal="Summarize a draft phenotype model.",
            target_audience="Cross-module bench scientists",
            storyline="Phenotype first, mechanism second.",
            key_findings=[{"claim": "", "evidence": ""}, {"claim": "Cell cycle reprogrammed", "evidence": ""}],
            manuscript_inputs={},
            available_modules=["figure-specification", "manuscript-audit", "citation-audit", "claim-evidence-integrity-audit", "manuscript-revision-base", "response-matrix", "manuscript-revision-lineage"],
        )
        self.assertFalse(result["readiness"]["ready_for_delivery"])
        self.assertGreaterEqual(result["readiness"]["critical_gap_count"], 2)
        claim_row = next(row for row in result["module_sequence"] if row["module_id"] == "claim-evidence-integrity-audit")
        self.assertEqual(claim_row["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
