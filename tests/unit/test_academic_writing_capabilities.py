import unittest

from biomed_workbench.capabilities.academic_writing import (
    audit_academic_prose_revision,
    audit_research_proposal,
    audit_statistical_reporting,
)


class AcademicWritingCapabilityTests(unittest.TestCase):
    def test_revision_contract_distinguishes_manuscripts_and_proposals(self):
        manuscript = audit_academic_prose_revision(
            original_text="The data suggest an association [1].",
            document_type="research-article",
            section_kind="results",
            target_venue="Nature Communications",
        )
        proposal = audit_academic_prose_revision(
            original_text="Our preliminary data support the feasibility of the proposed study [1].",
            document_type="grant-proposal",
            section_kind="rationale",
            target_venue="NSFC",
        )
        self.assertEqual(manuscript["revision_contract"]["mode"], "manuscript")
        self.assertIn("results-forward", manuscript["revision_contract"]["mode_specific_focus"])
        self.assertEqual(proposal["revision_contract"]["mode"], "funding-proposal")
        self.assertIn("vision and ambition", proposal["revision_contract"]["mode_specific_focus"])
        self.assertTrue(proposal["revision_contract"]["delivery_requires_post_revision_pass"])

    def test_revision_blocks_changed_number_citation_and_removed_hedging(self):
        result = audit_academic_prose_revision(
            original_text="The data suggest a 3% association [1].",
            document_type="research-article",
            section_kind="results",
            target_venue="Nature Communications",
            revised_text="The data prove a 5% association [2].",
            claim_bindings=[{
                "claim_id": "C1", "claim": "The data prove an association.",
                "claim_level": "causal", "evidence_level": "associational",
                "evidence_ids": ["E1"], "hedging_required": True, "hedging_preserved": False,
            }],
        )
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("numbers-changed", codes)
        self.assertIn("citations-changed", codes)
        self.assertIn("claim-exceeds-evidence", codes)
        self.assertIn("required-hedging-removed", codes)
        self.assertFalse(result["ready_for_delivery"])

    def test_proposal_blocks_unsupported_claim_and_incomplete_aim(self):
        result = audit_research_proposal(
            mode="compose",
            agency="NIH",
            scope={"deliverable": "R01", "target_reader": "study section", "language": "English", "constraints": "12 pages", "version_target": "v1"},
            research_canon=[{"id": "F1", "fact": "Pilot assay completed."}],
            evidence_table=[{"claim_id": "C1", "claim": "The mechanism is established.", "status": "unsupported", "source_ids": []}],
            argument_map={"scientific_tension": "Unknown regulator", "central_question": "What regulates the system?", "central_thesis": "Perturbation will test candidates.", "limitations": ["one tissue"]},
            section_contracts=[{"id": "S1", "purpose": "Rationale", "inputs": ["F1"], "allowed_claims": ["C1"], "forbidden_claims": ["causality"], "required_evidence": ["F1"], "validation": ["mapped"]}],
            aims=[{"id": "A1", "objective": "Apply sequencing", "rationale": "Gap", "approach": "Sequence"}],
            review_criteria=["significance"],
        )
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("unsupported-proposal-claim", codes)
        self.assertIn("aim-incomplete", codes)
        self.assertIn("nih-central-hypothesis-missing", codes)
        self.assertTrue(result["stop_iteration"])

    def test_statistics_blocks_pseudoreplication_and_unqualified_significance(self):
        result = audit_statistical_reporting(
            design={"experimental_unit": "cells"},
            analyses=[{"id": "A1", "comparison_or_model": "treated vs control"}],
            result_statements=[{"analysis_id": "A1", "text": "The result was significantly increased."}],
        )
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("possible-pseudoreplication", codes)
        self.assertIn("significance-without-statistic", codes)
        self.assertFalse(result["ready_for_manuscript_reporting"])


if __name__ == "__main__":
    unittest.main()
