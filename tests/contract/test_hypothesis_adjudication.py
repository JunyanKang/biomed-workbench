import unittest

from biomed_workbench.orchestration.interpretation import assess_hypothesis
from tests.unit.kernel.test_evidence import evidence_record
from tests.unit.kernel.test_hypotheses import hypothesis


class HypothesisAdjudicationContractTests(unittest.TestCase):
    def test_observational_evidence_cannot_support_causal_claim_scope(self):
        causal = hypothesis(permitted_claim_strength="causal")
        evidence = (
            evidence_record(id="causal-one", evidence_type="cell-state-association", independent_group="cohort-one", study_design="observational-cohort"),
            evidence_record(id="causal-two", artifact_id="artifact-two", evidence_type="regulatory-association", independent_group="cohort-two", study_design="observational-cohort"),
        )

        assessment = assess_hypothesis(causal, evidence, ())

        self.assertEqual(assessment.new_status, "inconclusive")
        self.assertIn("causal", assessment.rationale.lower())

    def test_low_quality_support_does_not_satisfy_evidence_requirements(self):
        records = (
            evidence_record(id="low-one", evidence_type="cell-state-association", independent_group="one", quality_status="major"),
            evidence_record(id="low-two", artifact_id="artifact-two", evidence_type="regulatory-association", independent_group="two", quality_status="fatal"),
        )

        assessment = assess_hypothesis(hypothesis(), records, ())

        self.assertEqual(assessment.new_status, "inconclusive")
        self.assertEqual(set(assessment.missing_evidence_types), set(hypothesis().required_evidence_types))


if __name__ == "__main__":
    unittest.main()
