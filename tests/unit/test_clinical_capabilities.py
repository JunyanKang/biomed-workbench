import unittest

from biomed_workbench.capabilities.clinical import (
    audit_report,
    biomarker_performance,
    clinical_decision_boundary_audit,
    cohort_summary,
    deidentify_record,
    kaplan_meier,
)


class ClinicalCapabilityTests(unittest.TestCase):
    def test_deidentification_redacts_nested_fields_and_free_text(self):
        result = deidentify_record(
            {
                "patient_name": "Jane Doe",
                "age": 42,
                "contact": {"email": "jane@example.org", "note": "Call +1 212-555-0199 or jane@example.org"},
            }
        )
        self.assertEqual(result["record"]["patient_name"], "[REDACTED]")
        self.assertEqual(result["record"]["age"], 42)
        self.assertNotIn("jane@example.org", str(result["record"]))
        self.assertGreaterEqual(result["redaction_count"], 3)
        self.assertTrue(result["limitations"])

    def test_cohort_summary_uses_explicit_variable_roles(self):
        result = cohort_summary(
            records=[
                {"age": 20, "sex": "F"},
                {"age": 30, "sex": "M"},
                {"age": 40, "sex": "F"},
                {"age": None, "sex": None},
            ],
            continuous=["age"],
            categorical=["sex"],
        )
        self.assertEqual(result["continuous"]["age"]["median"], 30.0)
        self.assertEqual(result["continuous"]["age"]["missing"], 1)
        self.assertEqual(result["categorical"]["sex"]["counts"], {"F": 2, "M": 1})

    def test_biomarker_performance_calculates_confusion_auc_and_predictive_values(self):
        result = biomarker_performance(labels=[0, 0, 1, 1], scores=[0.1, 0.4, 0.35, 0.8], threshold=0.3)
        self.assertEqual(result["confusion"], {"true_positive": 2, "false_positive": 1, "true_negative": 1, "false_negative": 0})
        self.assertAlmostEqual(result["roc_auc"], 0.75)
        self.assertAlmostEqual(result["sensitivity"], 1.0)
        self.assertAlmostEqual(result["specificity"], 0.5)

    def test_kaplan_meier_handles_events_and_censoring_at_same_time(self):
        result = kaplan_meier(durations=[1, 2, 2, 3], events=[1, 1, 0, 1])
        self.assertEqual(result["curve"][0]["at_risk"], 4)
        self.assertEqual(result["curve"][1]["events"], 1)
        self.assertEqual(result["curve"][1]["censored"], 1)
        self.assertEqual(result["median_survival"], 2.0)

    def test_report_audit_exposes_present_and_missing_sections(self):
        text = "Title\nAbstract\nIntroduction\nCase presentation\nDiagnostic assessment\nTherapeutic intervention\nFollow-up\nPatient perspective\nInformed consent"
        result = audit_report(text, standard="CARE")
        self.assertGreater(result["completeness_fraction"], 0.5)
        self.assertIn("title", result["present_sections"])
        self.assertIn("timeline", result["missing_sections"])
        self.assertIn("not a substitute", result["limitations"][0].lower())

    def test_clinical_decision_boundary_blocks_patient_specific_treatment(self):
        result = clinical_decision_boundary_audit(
            request_text="Diagnose this patient and prescribe the best treatment dose.",
            intended_use="patient_specific_decision",
            has_qualified_clinician_review=False,
        )
        self.assertEqual(result["risk_level"], "blocked")
        self.assertFalse(result["interpretation_allowed"])
        self.assertFalse(result["clinical_recommendation_allowed"])
        self.assertIn("diagnosis", result["blocker_hits"])
        self.assertIn("treatment", result["blocker_hits"])
        self.assertTrue(result["fatal_reasons"])

    def test_clinical_decision_boundary_allows_limited_research_summary(self):
        result = clinical_decision_boundary_audit(
            request_text="Summarize cohort evidence and limitations for a research report.",
            intended_use="research_support",
            evidence_items=[{"type": "source_records"}],
        )
        self.assertEqual(result["risk_level"], "limited_research_support")
        self.assertTrue(result["interpretation_allowed"])
        self.assertFalse(result["clinical_recommendation_allowed"])
        self.assertIn("cohort_denominator", result["missing_evidence_types"])


if __name__ == "__main__":
    unittest.main()
