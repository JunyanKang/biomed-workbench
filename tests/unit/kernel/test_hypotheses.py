import unittest

from biomed_workbench.kernel.hypotheses import Hypothesis, add_hypothesis, attach_evidence, revise_hypothesis
from tests.unit.kernel.test_evidence import evidence_record


def hypothesis(**overrides):
    values = {
        "id": "hypothesis-lineage-shift-v1",
        "statement": "The perturbation reduces the transition from progenitor to neuronal states.",
        "biological_scope": {"species": "human", "tissue": "retina"},
        "experimental_unit": "independent-organoid-line",
        "comparison_id": "perturbed-vs-control",
        "expected_direction": "decrease",
        "expected_observations": ("Lower neuronal-state abundance across independent lines.", "Reduced neuronal regulatory activity."),
        "disconfirming_observations": ("No reproducible lineage difference after batch-aware analysis.", "An increase in neuronal-state abundance."),
        "alternative_explanations": ("Differential survival changes apparent composition.", "Batch-dependent maturation creates the association."),
        "required_evidence_types": ("cell-state-association", "regulatory-association"),
        "minimum_independent_evidence_groups": 2,
        "permitted_claim_strength": "associational",
        "status": "active",
        "supporting_evidence_ids": (),
        "conflicting_evidence_ids": (),
        "missing_evidence_types": ("cell-state-association", "regulatory-association"),
        "parent_hypothesis_id": None,
        "revision": 1,
    }
    values.update(overrides)
    return Hypothesis(**values)


class HypothesisLedgerTests(unittest.TestCase):
    def test_hypothesis_requires_falsification_alternatives_and_orthogonal_evidence(self):
        value = hypothesis()

        self.assertEqual(value.status, "active")
        self.assertEqual(value.minimum_independent_evidence_groups, 2)
        self.assertEqual(value.missing_evidence_types, value.required_evidence_types)
        self.assertEqual(value.to_dict()["biological_scope"]["tissue"], "retina")

    def test_nonfalsifiable_or_underspecified_hypotheses_are_rejected(self):
        invalid = (
            {"statement": "too short"},
            {"expected_observations": ()},
            {"disconfirming_observations": ()},
            {"alternative_explanations": ()},
            {"required_evidence_types": ()},
            {"minimum_independent_evidence_groups": 0},
            {"permitted_claim_strength": "proof"},
            {"status": "confirmed"},
            {"supporting_evidence_ids": ("evidence-1",), "conflicting_evidence_ids": ("evidence-1",)},
            {"missing_evidence_types": ("unrequested-evidence",)},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                hypothesis(**overrides)

    def test_revision_creates_new_lineage_entry_and_preserves_refuted_parent(self):
        original = hypothesis(status="refuted")

        revised = revise_hypothesis(
            original,
            new_id="hypothesis-survival-shift-v2",
            statement="The perturbation changes apparent neuronal abundance by selective survival rather than fate transition.",
            expected_direction="change",
            status="active",
            supporting_evidence_ids=(),
            conflicting_evidence_ids=(),
        )

        self.assertEqual(original.status, "refuted")
        self.assertEqual(revised.parent_hypothesis_id, original.id)
        self.assertEqual(revised.revision, 2)
        self.assertEqual(revised.status, "active")

    def test_ledger_rejects_duplicate_hypothesis_ids(self):
        ledger = add_hypothesis((), hypothesis())

        with self.assertRaisesRegex(ValueError, "duplicate"):
            add_hypothesis(ledger, hypothesis())

    def test_evidence_links_remain_partitioned_by_direction(self):
        value = hypothesis()
        supporting = evidence_record(id="evidence-support", relation="supports")
        refuting = evidence_record(id="evidence-refute", relation="refutes", artifact_id="artifact-validation-02")

        linked = attach_evidence(attach_evidence(value, supporting), refuting)

        self.assertEqual(linked.supporting_evidence_ids, ("evidence-support",))
        self.assertEqual(linked.conflicting_evidence_ids, ("evidence-refute",))


if __name__ == "__main__":
    unittest.main()
