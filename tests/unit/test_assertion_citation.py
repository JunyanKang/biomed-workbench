import unittest

from biomed_workbench.capabilities.assertion_citation import audit_assertion_citation_coverage


def sentence(sentence_id="sentence-1", **overrides):
    value = {
        "id": sentence_id,
        "text": "External studies showed that 67% of cells responded.",
        "section_path": "Results",
        "adjacent_text": None,
        "origin": "external_evidence",
        "claim_kind": "empirical",
        "citation_ids": [],
        "adjacent_citation_ids": [],
        "artifact_ids": [],
        "manifest_claim_id": None,
    }
    value.update(overrides)
    return value


def provenance(**overrides):
    value = {
        "audit_id": "citation-coverage-1",
        "audit_version": "1.0.0",
        "reviewed_at": "2026-07-13",
        "segmentation_complete": True,
        "citation_extraction_complete": True,
        "rules_independent_from_writer": True,
    }
    value.update(overrides)
    return value


class AssertionCitationCoverageTests(unittest.TestCase):
    def run_audit(self, *, sentences=None, citations=None, artifacts=None, policy="strict", audit_provenance=None):
        return audit_assertion_citation_coverage(
            sentences=[sentence()] if sentences is None else sentences,
            citation_inventory=[] if citations is None else citations,
            artifact_inventory=[] if artifacts is None else artifacts,
            terminal_policy=policy,
            audit_provenance=provenance() if audit_provenance is None else audit_provenance,
        )

    def test_uncited_external_empirical_assertion_blocks(self):
        result = self.run_audit()
        row = result["sentence_results"][0]
        self.assertEqual(row["issues"][0]["code"], "UNCITED_EXTERNAL_ASSERTION")
        self.assertIn("showed", row["trigger_terms"])
        self.assertIn("67%", row["trigger_terms"])
        self.assertEqual(row["gate"], "blocked")

    def test_resolved_sentence_citation_covers_external_claim(self):
        item = sentence(citation_ids=["citation-1"])
        result = self.run_audit(sentences=[item], citations=["citation-1"])
        row = result["sentence_results"][0]
        self.assertTrue(row["covered"])
        self.assertEqual(row["coverage_kind"], "sentence_citation")
        self.assertEqual(result["overall_status"], "passed")

    def test_adjacent_citation_requires_structured_binding(self):
        item = sentence(adjacent_text="Prior work supports this. <!--ref:study-1-->")
        result = self.run_audit(sentences=[item], citations=["citation-1"])
        codes = [issue["code"] for issue in result["sentence_results"][0]["issues"]]
        self.assertIn("CITATION_INTENT_NOT_STRUCTURED", codes)
        self.assertIn("UNCITED_EXTERNAL_ASSERTION", codes)

        bound = sentence(adjacent_text="Prior work supports this.", adjacent_citation_ids=["citation-1"])
        covered = self.run_audit(sentences=[bound], citations=["citation-1"])
        self.assertEqual(covered["sentence_results"][0]["coverage_kind"], "adjacent_citation")

    def test_current_study_result_uses_artifact_not_external_citation(self):
        item = sentence(origin="current_study", artifact_ids=["result-1"], citation_ids=[])
        result = self.run_audit(sentences=[item], artifacts=["result-1"])
        row = result["sentence_results"][0]
        self.assertTrue(row["covered"])
        self.assertEqual(row["coverage_kind"], "current_study_artifact")

    def test_current_study_result_without_artifact_blocks(self):
        result = self.run_audit(sentences=[sentence(origin="current_study")])
        self.assertEqual(result["sentence_results"][0]["issues"][0]["code"], "CURRENT_STUDY_ASSERTION_UNBOUND")

    def test_manifest_membership_does_not_exempt_assertion(self):
        result = self.run_audit(sentences=[sentence(manifest_claim_id="claim-7")])
        row = result["sentence_results"][0]
        self.assertFalse(row["covered"])
        self.assertEqual(row["manifest_claim_id"], "claim-7")

    def test_definition_is_not_an_empirical_candidate(self):
        item = sentence(text="Cell fate refers to a stable developmental identity.", origin="definition", claim_kind="definitional")
        result = self.run_audit(sentences=[item])
        row = result["sentence_results"][0]
        self.assertFalse(row["candidate"])
        self.assertEqual(row["gate"], "passed")

    def test_definition_origin_and_claim_kind_must_agree(self):
        with self.assertRaisesRegex(ValueError, "must agree"):
            self.run_audit(sentences=[sentence(origin="definition", claim_kind="causal")])

    def test_year_version_and_section_numbers_do_not_trigger(self):
        items = [
            sentence("s-1", text="The protocol version was v3.7.3 in 2026.", origin="method_description", claim_kind="procedural"),
            sentence("s-2", text="See Figure 3 and Section 2.1.", origin="method_description", claim_kind="procedural"),
        ]
        result = self.run_audit(sentences=items)
        self.assertEqual([row["candidate"] for row in result["sentence_results"]], [False, False])

    def test_bare_biomedical_quantity_is_detected(self):
        item = sentence(text="The sample contained 42 cells.", claim_kind="interpretive")
        result = self.run_audit(sentences=[item])
        self.assertEqual(result["sentence_results"][0]["trigger_terms"], ["42 cells"])

    def test_unresolved_inventory_binding_is_not_coverage(self):
        item = sentence(citation_ids=["missing-citation"])
        result = self.run_audit(sentences=[item])
        row = result["sentence_results"][0]
        self.assertFalse(row["covered"])
        self.assertEqual(row["issues"][0]["code"], "CITATION_BINDING_UNRESOLVED")

    def test_incomplete_extraction_cannot_masquerade_as_clean(self):
        item = sentence(text="A neutral sentence.", origin="method_description", claim_kind="procedural")
        result = self.run_audit(sentences=[item], audit_provenance=provenance(citation_extraction_complete=False))
        self.assertEqual(result["overall_status"], "blocked")
        self.assertIn("citation_extraction_incomplete", result["provenance_gate_ids"])

    def test_review_date_must_be_a_real_calendar_date(self):
        with self.assertRaisesRegex(ValueError, "valid ISO calendar date"):
            self.run_audit(audit_provenance=provenance(reviewed_at="2026-99-99"))

    def test_advisory_policy_preserves_unsafe_release_signal(self):
        result = self.run_audit(policy="advisory")
        self.assertEqual(result["overall_status"], "review_required")
        self.assertFalse(result["release_safe"])

    def test_digest_is_deterministic(self):
        self.assertEqual(self.run_audit(), self.run_audit())


if __name__ == "__main__":
    unittest.main()
