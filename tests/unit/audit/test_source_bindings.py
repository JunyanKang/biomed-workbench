import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.audit import SourceBindingError, apply_binding_rule_files, apply_binding_rules


class SourceBindingTests(unittest.TestCase):
    def row(self, path="family/client.py", action="rewrite_capability"):
        return {
            "source": "primary-c",
            "path": path,
            "source_sha256": ("a" if path.endswith("client.py") else "b") * 64,
            "action": action,
            "capability_cluster": "clinical_translation",
        }

    def rule(self):
        return {
            "id": "clinical-trials-v2",
            "resolution": "superseded",
            "module_ids": ["clinical-trial-evidence"],
            "project_evidence_ids": [],
            "criteria": {
                "source": "primary-c",
                "capability_cluster": "clinical_translation",
                "path_prefixes": ["family/"],
            },
        }

    def test_rule_adds_deterministic_path_free_binding(self):
        bindings, report = apply_binding_rules([self.row()], [], [self.rule()])
        self.assertEqual(report["matched_receipt_count"], 1)
        self.assertEqual(report["bindings_by_rule"], {"clinical-trials-v2": 1})
        self.assertEqual(bindings[0]["module_ids"], ["clinical-trial-evidence"])
        self.assertRegex(bindings[0]["receipt_id"], r"^[0-9a-f]{64}$")
        self.assertNotIn("family/client.py", json.dumps(report))

    def test_existing_identical_binding_is_idempotent(self):
        bindings, first_report = apply_binding_rules([self.row()], [], [self.rule()])
        repeated, report = apply_binding_rules([self.row()], bindings, [self.rule()])
        self.assertEqual(repeated, bindings)
        self.assertEqual(report, first_report)

    def test_overlap_nonpending_and_conflict_fail(self):
        second = self.rule()
        second["id"] = "overlap"
        with self.assertRaises(SourceBindingError):
            apply_binding_rules([self.row()], [], [self.rule(), second])
        with self.assertRaises(SourceBindingError):
            apply_binding_rules([self.row(action="synthesize_guidance")], [], [self.rule()])
        existing, _ = apply_binding_rules([self.row()], [], [self.rule()])
        existing[0]["resolution"] = "implemented"
        with self.assertRaises(SourceBindingError):
            apply_binding_rules([self.row()], existing, [self.rule()])

    def test_file_application_preserves_header_and_is_atomic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            design = root / "design.jsonl"
            bindings = root / "bindings.jsonl"
            rules = root / "rules.json"
            design.write_text(json.dumps(self.row()) + "\n", encoding="utf-8")
            bindings.write_text(json.dumps({"schema_version": 2, "type": "bindings"}) + "\n", encoding="utf-8")
            rules.write_text(json.dumps({"schema_version": 1, "rules": [self.rule()]}), encoding="utf-8")
            report = apply_binding_rule_files(design, bindings, rules)
            lines = bindings.read_text(encoding="utf-8").splitlines()
        self.assertEqual(report["total_binding_count"], 1)
        self.assertEqual(json.loads(lines[0]), {"schema_version": 2, "type": "bindings"})


if __name__ == "__main__":
    unittest.main()
