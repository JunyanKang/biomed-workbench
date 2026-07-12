import unittest

from biomed_workbench.kernel.evidence import EvidenceRecord, add_evidence, evidence_partition, independent_evidence_groups


def evidence_record(**overrides):
    values = {
        "id": "evidence-cell-state-01",
        "hypothesis_id": "hypothesis-lineage-shift-v1",
        "artifact_id": "artifact-contrast-01",
        "relation": "supports",
        "evidence_type": "cell-state-association",
        "independent_group": "rna-lines-cohort-1",
        "study_design": "paired-perturbation",
        "experimental_unit": "independent-organoid-line",
        "effect": {"measure": "log2-fold-change", "estimate": -0.8, "direction": "decrease"},
        "uncertainty": {"interval": [-1.2, -0.4], "level": 0.95, "adjusted_p_value": 0.01},
        "quality_status": "passed",
        "limitations": ("The association does not by itself establish a fate-transition mechanism.",),
        "rationale": "The observed direction matches the prespecified expected neuronal-state decrease.",
    }
    values.update(overrides)
    return EvidenceRecord(**values)


class EvidenceLedgerTests(unittest.TestCase):
    def test_evidence_records_relation_design_unit_effect_uncertainty_and_quality(self):
        value = evidence_record()
        payload = value.to_dict()

        self.assertEqual(value.relation, "supports")
        self.assertEqual(value.experimental_unit, "independent-organoid-line")
        self.assertEqual(payload["effect"]["estimate"], -0.8)
        self.assertEqual(payload["uncertainty"]["level"], 0.95)

    def test_incomplete_or_unlinked_evidence_is_rejected(self):
        invalid = (
            {"hypothesis_id": ""},
            {"artifact_id": ""},
            {"relation": "agrees"},
            {"evidence_type": ""},
            {"independent_group": ""},
            {"experimental_unit": ""},
            {"effect": {}},
            {"uncertainty": {}},
            {"quality_status": "excellent"},
            {"rationale": "short"},
            {"effect": {"path": "/Users/researcher/result.tsv"}},
            {"uncertainty": {"API_KEY": "private"}},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                evidence_record(**overrides)

    def test_duplicate_or_contradictory_artifact_evidence_is_rejected(self):
        first = evidence_record()
        ledger = add_evidence((), first)

        with self.assertRaisesRegex(ValueError, "duplicate evidence id"):
            add_evidence(ledger, evidence_record())
        with self.assertRaisesRegex(ValueError, "contradictory duplicate"):
            add_evidence(ledger, evidence_record(id="evidence-conflict", relation="refutes"))

    def test_relations_are_partitioned_and_independence_is_not_inflated(self):
        records = (
            evidence_record(id="support-1", relation="supports", independent_group="rna-cohort"),
            evidence_record(id="support-2", relation="supports", artifact_id="artifact-contrast-02", independent_group="rna-cohort"),
            evidence_record(id="weak-1", relation="weakens", artifact_id="artifact-qc-01", independent_group="quality-audit"),
            evidence_record(id="refute-1", relation="refutes", artifact_id="artifact-validation-01", independent_group="imaging-cohort"),
            evidence_record(id="unclear-1", relation="inconclusive", artifact_id="artifact-validation-02", independent_group="pilot-cohort"),
        )

        partitioned = evidence_partition(records)

        self.assertEqual(tuple(partitioned), ("supports", "weakens", "refutes", "inconclusive"))
        self.assertEqual(len(partitioned["supports"]), 2)
        self.assertEqual(independent_evidence_groups(partitioned["supports"]), ("rna-cohort",))

    def test_evidence_mappings_are_deeply_immutable(self):
        effect = {"estimate": -0.8, "details": {"unit": "log2-fold-change"}}
        value = evidence_record(effect=effect)
        effect["details"]["unit"] = "changed"

        self.assertEqual(value.effect["details"]["unit"], "log2-fold-change")
        with self.assertRaises(TypeError):
            value.effect["details"]["unit"] = "changed"


if __name__ == "__main__":
    unittest.main()
