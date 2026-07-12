import unittest

from biomed_workbench.orchestration.interpretation import assess_hypothesis
from biomed_workbench.orchestration.quality import QualityFinding
from tests.unit.kernel.test_evidence import evidence_record
from tests.unit.kernel.test_hypotheses import hypothesis


def support_pair(*, same_group=False):
    return (
        evidence_record(id="evidence-cell", evidence_type="cell-state-association", independent_group="rna-cohort"),
        evidence_record(
            id="evidence-regulatory",
            artifact_id="artifact-regulatory",
            evidence_type="regulatory-association",
            independent_group="rna-cohort" if same_group else "atac-cohort",
        ),
    )


class HypothesisInterpretationTests(unittest.TestCase):
    def test_orthogonal_required_evidence_supports_hypothesis(self):
        assessment = assess_hypothesis(hypothesis(), support_pair(), ())

        self.assertEqual(assessment.previous_status, "active")
        self.assertEqual(assessment.new_status, "supported")
        self.assertEqual(assessment.independent_support_groups, ("atac-cohort", "rna-cohort"))
        self.assertEqual(assessment.missing_evidence_types, ())

    def test_refuting_evidence_overrides_concurrent_support(self):
        records = (
            *support_pair(),
            evidence_record(id="evidence-refute", artifact_id="artifact-refute", relation="refutes", independent_group="validation-cohort"),
        )

        assessment = assess_hypothesis(hypothesis(), records, ())

        self.assertEqual(assessment.new_status, "refuted")
        self.assertEqual(assessment.conflicting_ids, ("evidence-refute",))
        self.assertTrue(assessment.alternative_explanations_to_test)

    def test_weakening_conflict_insufficient_orthogonality_and_absence_do_not_become_support(self):
        cases = (
            ((*support_pair(), evidence_record(id="weak", artifact_id="artifact-weak", relation="weakens")), "weakened"),
            (support_pair(same_group=True), "inconclusive"),
            ((), "inconclusive"),
        )
        for records, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(assess_hypothesis(hypothesis(), tuple(records), ()).new_status, expected)

    def test_blocking_finding_prevents_supported_status(self):
        finding = QualityFinding(
            id="finding-confounding-0001",
            code="COMPLETE_CONFOUNDING",
            severity="fatal",
            subject_ids=(hypothesis().id,),
            message="The comparison is completely confounded and cannot support interpretation.",
            blocks_execution=True,
            blocks_interpretation=True,
            remediation_artifact_types=("experimental_design",),
        )

        assessment = assess_hypothesis(hypothesis(), support_pair(), (finding,))

        self.assertEqual(assessment.new_status, "inconclusive")


if __name__ == "__main__":
    unittest.main()
