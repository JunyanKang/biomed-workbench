import unittest

from biomed_workbench.capabilities.research_quality import (
    assess_manuscript,
    audit_source_freshness,
    calculate_tumor_mutation_burden,
    summarize_adverse_events,
)


class ResearchQualityTests(unittest.TestCase):
    def test_source_freshness_separates_review_window_from_upstream_drift(self):
        result = audit_source_freshness(
            records=[
                {
                    "id": "reporting-guideline",
                    "snapshot_date": "2026-01-20",
                    "upstream_source": "https://example.org/reporting-guideline",
                    "upstream_version": "2026-01 snapshot",
                    "review_interval_days": 180,
                    "intended_use": "Current reporting guidance",
                    "currentness_required": True,
                },
                {
                    "id": "archival-taxonomy",
                    "snapshot_date": "2025-01-01",
                    "upstream_source": "https://example.org/archival-taxonomy",
                    "upstream_version": "1.0",
                    "review_interval_days": 365,
                    "intended_use": "Historical coding reproduction",
                    "currentness_required": False,
                },
            ],
            as_of_date="2026-07-13",
        )

        self.assertEqual(result["overall_status"], "blocked")
        self.assertEqual(result["records"][0]["temporal_status"], "within_review_window")
        self.assertFalse(result["records"][0]["upstream_drift_assessed"])
        self.assertFalse(result["records"][0]["currentness_claim_allowed"])
        self.assertEqual(result["records"][1]["temporal_status"], "review_due")
        self.assertEqual(result["blocked_record_ids"], ["archival-taxonomy"])

    def test_source_freshness_warn_policy_allows_limited_use_but_not_currentness_claim(self):
        result = audit_source_freshness(
            records=[
                {
                    "id": "archival-protocol",
                    "snapshot_date": "2024-01-01",
                    "upstream_source": "https://example.org/protocol",
                    "upstream_version": "2.1",
                    "review_interval_days": 180,
                    "intended_use": "Reproduce a historical analysis",
                    "currentness_required": False,
                }
            ],
            as_of_date="2026-07-13",
            due_policy="warn_when_due",
        )

        self.assertEqual(result["overall_status"], "review_required")
        self.assertTrue(result["records"][0]["use_allowed"])
        self.assertFalse(result["records"][0]["currentness_claim_allowed"])

    def test_source_freshness_rejects_future_dates_credentials_and_unknown_fields(self):
        base = {
            "id": "source",
            "snapshot_date": "2026-07-14",
            "upstream_source": "https://example.org/source",
            "upstream_version": "1",
            "review_interval_days": 30,
            "intended_use": "Guidance",
            "currentness_required": True,
        }
        result = audit_source_freshness([base], "2026-07-13")
        self.assertEqual(result["overall_status"], "invalid")
        self.assertFalse(result["records"][0]["use_allowed"])

        with self.assertRaises(ValueError):
            audit_source_freshness([{**base, "snapshot_date": "2026-01-01", "upstream_source": "https://user:secret@example.org/source"}], "2026-07-13")
        with self.assertRaises(ValueError):
            audit_source_freshness([{**base, "snapshot_date": "2026-01-01", "upstream_source": "https://example.org/source?token=secret"}], "2026-07-13")
        with self.assertRaises(ValueError):
            audit_source_freshness([{**base, "unexpected": "field"}], "2026-07-13")
        with self.assertRaises(ValueError):
            audit_source_freshness([base, {**base, "id": " source "}], "2026-07-13")

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
