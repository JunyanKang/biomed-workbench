import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.audit import ReconciliationError, reconcile_ledgers


class SourceReconciliationTests(unittest.TestCase):
    def write_ledgers(self, root: Path, *, omit_design=False, duplicate_manifest=False, duplicate_design=False):
        manifest = root / "manifest.jsonl"
        design = root / "design.jsonl"
        rows = [
            {"source": "primary-a", "path": "tool.py", "sha256": "a" * 64, "disposition": "merge"},
            {"source": "primary-a", "path": "cache.bin", "sha256": "b" * 64, "disposition": "generated_runtime"},
        ]
        manifest.write_text(json.dumps({"type": "manifest", "roots": {"primary-a": "/private/source"}}) + "\n" + "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        designs = [
            {"source": "primary-a", "path": "tool.py", "source_sha256": "a" * 64, "action": "rewrite_capability", "capability_cluster": "omics"},
            {"source": "primary-a", "path": "cache.bin", "source_sha256": "b" * 64, "action": "exclude_generated", "capability_cluster": "generated_runtime"},
        ]
        if omit_design:
            designs.pop()
        if duplicate_manifest:
            rows.append(rows[0])
            manifest.write_text(json.dumps({"type": "manifest", "roots": {"primary-a": "/private/source"}}) + "\n" + "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        if duplicate_design:
            designs.append(designs[0])
        design.write_text("".join(json.dumps(row) + "\n" for row in designs), encoding="utf-8")
        return manifest, design

    def test_exact_ledgers_produce_path_free_pending_and_excluded_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, design = self.write_ledgers(root)
            private = root / "reconciled.jsonl"
            report = reconcile_ledgers(manifest, design, module_count=4, registry_digest="c" * 64, skill_sha256="d" * 64, test_count=10, private_output=private)
        self.assertEqual(report["file_count"], 2)
        self.assertEqual(report["status_counts"], {"excluded": 1, "pending": 1})
        self.assertEqual(report["pending_count"], 1)
        self.assertNotIn("tool.py", json.dumps(report))
        self.assertRegex(report["receipt_root_digest"], r"^[0-9a-f]{64}$")

    def test_current_module_evidence_can_resolve_one_pending_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, design = self.write_ledgers(root)
            receipt = hashlib.sha256(f"primary-a\0tool.py\0{'a' * 64}".encode()).hexdigest()
            bindings = root / "bindings.jsonl"
            bindings.write_text(
                json.dumps({"schema_version": 2, "type": "bindings"}) + "\n"
                + json.dumps({"receipt_id": receipt, "resolution": "implemented", "module_ids": ["variant-filter"], "project_evidence_ids": []}) + "\n",
                encoding="utf-8",
            )
            report = reconcile_ledgers(
                manifest,
                design,
                module_count=4,
                registry_digest="c" * 64,
                skill_sha256="d" * 64,
                test_count=10,
                bindings_path=bindings,
                module_evidence={"variant-filter": ("row-v1", "regression-v1", "e2e-v1")},
            )

        self.assertEqual(report["status_counts"], {"excluded": 1, "implemented": 1})
        self.assertEqual(report["pending_count"], 0)
        self.assertEqual(report["binding_count"], 1)
        self.assertEqual(report["bound_module_count"], 1)
        self.assertEqual(report["bound_project_evidence_count"], 0)

    def test_current_project_contract_evidence_can_resolve_a_schema_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, design = self.write_ledgers(root)
            receipt = hashlib.sha256(f"primary-a\0tool.py\0{'a' * 64}".encode()).hexdigest()
            bindings = root / "bindings.jsonl"
            bindings.write_text(
                json.dumps({"schema_version": 2, "type": "bindings"}) + "\n"
                + json.dumps({"receipt_id": receipt, "resolution": "superseded", "module_ids": [], "project_evidence_ids": ["plugin-contract-v1"]}) + "\n",
                encoding="utf-8",
            )
            report = reconcile_ledgers(
                manifest,
                design,
                module_count=4,
                registry_digest="c" * 64,
                skill_sha256="d" * 64,
                test_count=10,
                bindings_path=bindings,
                project_evidence={
                    "plugin-contract-v1": {
                        "evidence_type": "codex-plugin-contract",
                        "artifact_sha256": "e" * 64,
                        "verification_sha256": "f" * 64,
                    }
                },
            )

        self.assertEqual(report["status_counts"], {"excluded": 1, "superseded": 1})
        self.assertEqual(report["bound_module_count"], 0)
        self.assertEqual(report["bound_project_evidence_count"], 1)

    def test_unknown_module_or_unknown_receipt_binding_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, design = self.write_ledgers(root)
            bindings = root / "bindings.jsonl"
            for receipt in ("f" * 64, hashlib.sha256(f"primary-a\0tool.py\0{'a' * 64}".encode()).hexdigest()):
                with self.subTest(receipt=receipt):
                    bindings.write_text(
                        json.dumps({"schema_version": 2, "type": "bindings"}) + "\n"
                        + json.dumps({"receipt_id": receipt, "resolution": "implemented", "module_ids": ["missing"], "project_evidence_ids": []}) + "\n",
                        encoding="utf-8",
                    )
                    with self.assertRaises(ReconciliationError):
                        reconcile_ledgers(
                            manifest,
                            design,
                            module_count=4,
                            registry_digest="c" * 64,
                            skill_sha256="d" * 64,
                            test_count=10,
                            bindings_path=bindings,
                            module_evidence={},
                        )

    def test_unknown_or_malformed_project_evidence_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, design = self.write_ledgers(root)
            receipt = hashlib.sha256(f"primary-a\0tool.py\0{'a' * 64}".encode()).hexdigest()
            bindings = root / "bindings.jsonl"
            bindings.write_text(
                json.dumps({"schema_version": 2, "type": "bindings"}) + "\n"
                + json.dumps({"receipt_id": receipt, "resolution": "implemented", "module_ids": [], "project_evidence_ids": ["missing"]}) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ReconciliationError):
                reconcile_ledgers(
                    manifest,
                    design,
                    module_count=4,
                    registry_digest="c" * 64,
                    skill_sha256="d" * 64,
                    test_count=10,
                    bindings_path=bindings,
                    project_evidence={},
                )
            with self.assertRaises(ReconciliationError):
                reconcile_ledgers(
                    manifest,
                    design,
                    module_count=4,
                    registry_digest="c" * 64,
                    skill_sha256="d" * 64,
                    test_count=10,
                    project_evidence={"broken": {"evidence_type": "contract", "artifact_sha256": "bad", "verification_sha256": "f" * 64}},
                )

    def test_missing_one_to_one_design_record_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest, design = self.write_ledgers(Path(temporary), omit_design=True)
            with self.assertRaises(ReconciliationError):
                reconcile_ledgers(manifest, design, module_count=4, registry_digest="c" * 64, skill_sha256="d" * 64, test_count=10)

    def test_duplicate_source_identity_fails_in_either_ledger(self):
        for option in ("duplicate_manifest", "duplicate_design"):
            with self.subTest(option=option), tempfile.TemporaryDirectory() as temporary:
                manifest, design = self.write_ledgers(Path(temporary), **{option: True})
                with self.assertRaises(ReconciliationError):
                    reconcile_ledgers(manifest, design, module_count=4, registry_digest="c" * 64, skill_sha256="d" * 64, test_count=10)


if __name__ == "__main__":
    unittest.main()
