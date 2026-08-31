import unittest

from biomed_workbench.capabilities.scientific_review import self_correct_scientific_review


class ScientificReviewSelfCorrectionTests(unittest.TestCase):
    def test_detects_overclaim_missing_magnitude_and_audit_heavy_language(self):
        result = self_correct_scientific_review(
            question="Does BANP regulate a retinal progenitor program?",
            hypothesis="BANP loss changes the progenitor transcriptional state.",
            study_design="observational",
            statistical_unit="embryo",
            observations=[{
                "id": "rna-1", "observation": "Program score was lower", "direction": "decrease",
                "effect_size": None, "uncertainty": "", "replicates": 1, "status": "candidate",
            }],
            draft_review={
                "methods": "Registry, digest, renderer and audit details. " * 30,
                "results": "The score was lower.",
                "conclusion": "BANP causally drives the program.",
                "limitations": "",
                "next_step": "Run more analysis.",
            },
            proposed_action="retain",
            alternative_explanations=["a generalized stress response"],
        )
        codes = {finding["code"] for finding in result["findings"]}
        self.assertIn("METHODS_DOMINATE_RESULTS", codes)
        self.assertIn("CAUSALITY_EXCEEDS_DESIGN", codes)
        self.assertIn("EFFECT_SIZE_MISSING", codes)
        self.assertTrue(result["requires_revision"])
        self.assertEqual(result["corrected_review_brief"]["statistical_unit"], "embryo")
        self.assertNotIn("causally drives", result["corrected_review_brief"]["interpretation"])
        self.assertIn("does not establish causality", result["corrected_review_brief"]["interpretation"])
        self.assertTrue(result["corrected_review_brief"]["limitations"])

    def test_well_bounded_review_passes(self):
        result = self_correct_scientific_review(
            question="Does treatment change retinal thickness?",
            hypothesis="Treatment is associated with increased thickness.",
            study_design="randomized",
            statistical_unit="animal",
            observations=[{
                "id": "oct-1", "observation": "Mean thickness increased by 12 micrometres",
                "direction": "increase", "effect_size": "12 um", "uncertainty": "95% CI 4 to 20 um",
                "replicates": 8, "status": "formal",
            }, {
                "id": "oct-2", "observation": "No increase was detected in the inactive control",
                "direction": "null", "effect_size": "1 um", "uncertainty": "95% CI -5 to 7 um",
                "replicates": 8, "status": "formal",
            }],
            draft_review={
                "methods": "Animals were randomized and analysed at the animal level.",
                "results": "Thickness increased by 12 um with the stated confidence interval; the inactive control was null.",
                "conclusion": "The randomized comparison supports a treatment effect on thickness, while the inactive control was null.",
                "limitations": "The result does not establish the cellular mechanism; the inactive control was null.",
                "next_step": "Test whether cell-type-specific perturbation distinguishes a direct retinal effect from systemic exposure.",
            },
            proposed_action="retain",
            alternative_explanations=["systemic exposure rather than a direct retinal effect"],
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["corrected_review_brief"]["recommended_action"], "retain")


if __name__ == "__main__":
    unittest.main()
