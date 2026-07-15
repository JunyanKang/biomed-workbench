import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.audit import SourcePolicyError, apply_scope_policy, refine_ledger, refine_rows


class SourcePolicyTests(unittest.TestCase):
    def compute_row(self):
        return {
            "source": "primary-b",
            "path": "skills/cluster/run.py",
            "source_sha256": "a" * 64,
            "action": "rewrite_capability",
            "capability_cluster": "runtime_orchestration",
            "target": "biomed_workbench/services/compute.py",
            "rationale": "old heuristic",
            "reuse_mode": "concept_only",
        }

    def test_compute_target_becomes_explicit_retirement(self):
        updated, rule = apply_scope_policy(self.compute_row())
        self.assertEqual(rule, "compute-infrastructure-explicitly-excluded")
        self.assertEqual(updated["action"], "retire")
        self.assertEqual(updated["reuse_mode"], "none")
        self.assertEqual(updated["target"], "excluded/product-boundary/compute-infrastructure")
        self.assertIn("Slurm", updated["rationale"])

    def test_scientific_pending_record_is_unchanged(self):
        row = self.compute_row()
        row.update(target="biomed_workbench/capabilities/omics.py", capability_cluster="omics")
        updated, rule = apply_scope_policy(row)
        self.assertIsNone(rule)
        self.assertEqual(updated, row)

    def test_misclassified_compute_target_fails(self):
        row = self.compute_row()
        row["capability_cluster"] = "omics"
        with self.assertRaises(SourcePolicyError):
            apply_scope_policy(row)

    def test_refinement_is_atomic_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.jsonl"
            path.write_text(json.dumps(self.compute_row()) + "\n", encoding="utf-8")
            first = refine_ledger(path)
            second = refine_ledger(path)
            row = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(first["changed_count"], 1)
        self.assertEqual(second["changed_count"], 1)
        self.assertEqual(first["transitions"], second["transitions"])
        self.assertEqual(row["action"], "retire")

    def test_private_scope_rule_retires_only_the_reviewed_receipt(self):
        rule = {
            "id": "materials-science-explicitly-excluded",
            "target": "excluded/product-boundary/materials-science",
            "rationale": "Explicit reviewed product boundary for a non-biomedical operation; related biomedical structure analysis remains independently implemented and tested.",
            "criteria": {"source": "primary-b", "capability_cluster": "structural_biology", "path_exact": ["family/material.py"]},
        }
        row = self.compute_row()
        row.update(path="family/material.py", capability_cluster="structural_biology", target="biomed_workbench/capabilities/structure.py")
        updated, matched = apply_scope_policy(row, [rule])
        self.assertEqual(matched, rule["id"])
        self.assertEqual(updated["action"], "retire")
        self.assertEqual(updated["reuse_mode"], "none")
        self.assertEqual(updated["target"], rule["target"])

    def test_duplicate_identity_fails(self):
        row = self.compute_row()
        with self.assertRaises(SourcePolicyError):
            refine_rows([row, row])


if __name__ == "__main__":
    unittest.main()
