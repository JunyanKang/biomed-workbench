import unittest

from biomed_workbench.capabilities.publication import (
    citation_audit,
    figure_specification,
    manuscript_audit,
    patent_disclosure_audit,
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


if __name__ == "__main__":
    unittest.main()
