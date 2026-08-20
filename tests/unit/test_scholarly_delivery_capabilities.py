import unittest

from biomed_workbench.capabilities.scholarly_delivery import (
    audit_data_availability,
    audit_literature_acquisition_manifest,
    audit_literature_landscape,
    audit_paper_reader_package,
    standardize_experiment_log,
)


class ScholarlyDeliveryCapabilityTests(unittest.TestCase):
    def test_data_availability_requires_repository_identity_and_statement_mapping(self):
        result = audit_data_availability(
            "Nature",
            [{"id": "D1", "title": "Raw sequencing", "claim_support_role": "Figure 1", "access_route": "public-repository"}],
            "Data will be shared.",
        )
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("repository-missing", codes)
        self.assertIn("stable-identifier-missing-or-invalid", codes)
        self.assertFalse(result["ready_for_manuscript"])

    def test_reader_requires_visible_pairs_and_assets(self):
        result = audit_paper_reader_package(
            paper_markdown="S001",
            source_map=[{"id": "S001", "type": "text", "page": 1, "original": "Text", "translation": "文本"}, {"id": "F001", "type": "figure", "page": 1}],
            translation_notes="Complete",
            assets=[],
        )
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("visible-bilingual-pairs-incomplete", codes)
        self.assertIn("figure-or-table-asset-missing", codes)
        self.assertFalse(result["ready_for_reading"])

    def test_experiment_log_preserves_uncertain_observation_as_author_input(self):
        result = standardize_experiment_log(
            "2026-08-20", "RT", "B", 2, "qPCR", "Measure expression",
            [{"sample_batch": "RT-1-B1", "description": "retina"}],
            [{"action": "Run qPCR", "conditions": {}, "sample_batches": ["RT-1-B1"]}],
            [{"text": "Temperature is unclear"}],
            [{"path": "raw/run.csv", "sha256": "a" * 64}],
        )
        self.assertFalse(result["ready_to_write"])
        self.assertIn("author-input-needed", {item["code"] for item in result["issues"]})

    def test_literature_manifest_rejects_session_export(self):
        result = audit_literature_acquisition_manifest([{
            "id": "P1", "title": "Paper", "status": "available_not_downloaded", "source_level": "metadata-only",
            "access_route": "institutional", "access_boundary_violation": True,
        }])
        self.assertFalse(result["manifest_valid"])
        self.assertEqual(result["findings"][0]["code"], "credential-or-session-export")

    def test_literature_landscape_requires_multi_source_coverage_and_citation_context(self):
        scores = {
            "topic_relevance": 5,
            "claim_directness": 4,
            "methodological_fit": 4,
            "evidence_depth": 3,
            "novelty_value": 3,
            "recency_value": 2,
        }
        result = audit_literature_landscape(
            {"objective": "Map a mechanism", "queries": ["candidate mechanism"], "sources": ["PubMed"], "coverage_mode": "comprehensive"},
            [{
                "id": "P1", "title": "Citing study", "source": "PubMed", "source_level": "abstract-only",
                "record_role": "citing-work", "authors": ["A. One"], "affiliations": ["Institute A"],
                "citation_contexts": [], "scores": scores,
            }],
            focal_authors=["A. One"],
            focal_affiliations=["Institute A"],
        )
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("multi-source-coverage-not-declared", codes)
        self.assertIn("citation-context-missing", codes)
        self.assertEqual(result["independent_citing_work_ids"], [])
        self.assertFalse(result["ready_for_synthesis"])


if __name__ == "__main__":
    unittest.main()
