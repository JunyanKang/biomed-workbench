import unittest

from biomed_workbench.capabilities.research_quality import (
    assess_manuscript,
    calculate_tumor_mutation_burden,
    summarize_adverse_events,
)


class ResearchQualityTests(unittest.TestCase):
    def test_tmb_exposes_rule_level_exclusions_and_callable_denominator(self):
        result = calculate_tumor_mutation_burden(
            variants=[
                {"id": "v1", "effect": "missense", "filter": "PASS", "allele_fraction": 0.25, "somatic": True},
                {"id": "v2", "effect": "synonymous", "filter": "PASS", "allele_fraction": 0.30, "somatic": True},
                {"id": "v3", "effect": "nonsense", "filter": "q10", "allele_fraction": 0.40, "somatic": True},
                {"id": "v4", "effect": "frameshift", "filter": "PASS", "allele_fraction": 0.01, "somatic": True},
            ],
            callable_megabases=2.0,
            minimum_allele_fraction=0.05,
            include_effects=["missense", "nonsense", "frameshift"],
        )

        self.assertEqual(result["eligible_variant_ids"], ["v1"])
        self.assertEqual(result["tmb_mutations_per_mb"], 0.5)
        self.assertEqual(result["exclusion_counts"], {"allele_fraction": 1, "effect": 1, "filter": 1})

    def test_adverse_events_distinguish_events_from_participants(self):
        result = summarize_adverse_events(
            events=[
                {"participant": "p1", "term": "Nausea", "grade": 1, "serious": False, "relatedness": "possible"},
                {"participant": "p1", "term": "Nausea", "grade": 3, "serious": False, "relatedness": "probable"},
                {"participant": "p2", "term": "Fever", "grade": 2, "serious": True, "relatedness": "unlikely"},
            ],
            enrolled_participants=4,
        )

        self.assertEqual(result["event_count"], 3)
        self.assertEqual(result["participants_with_events"], 2)
        self.assertEqual(result["by_term"]["Nausea"]["participant_count"], 1)
        self.assertEqual(result["by_term"]["Nausea"]["maximum_grade"], 3)

    def test_manuscript_assessment_links_concerns_to_claims_and_review_domains(self):
        result = assess_manuscript(
            claims=[
                {"id": "c1", "claim": "The marker causally drives fate", "evidence_design": "observational", "replicated": False},
                {"id": "c2", "claim": "Treatment improves outcome", "evidence_design": "randomized", "replicated": True},
            ],
            review_domains={"methods_reproducible": False, "statistics_adequate": True, "data_available": False, "ethics_resolved": True},
            novelty="high",
        )

        self.assertEqual(result["recommendation"], "major_revision")
        codes = {finding["code"] for finding in result["findings"]}
        self.assertIn("CAUSALITY_OVERCLAIM", codes)
        self.assertIn("METHODS_NOT_REPRODUCIBLE", codes)
        self.assertEqual(result["claim_assessments"][0]["claim_id"], "c1")


if __name__ == "__main__":
    unittest.main()
