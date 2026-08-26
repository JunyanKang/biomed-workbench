import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_execution_readiness import (
    _portable_validation_identity,
    _write_run_receipt_archive,
    build,
)


class ExecutionReadinessTests(unittest.TestCase):
    def test_run_specific_receipts_are_archived_outside_portable_catalog_identity(self):
        validation = {
            "module_id": "example",
            "module_version": "1.0.0",
            "controlled_fixture_receipt_digest": "a" * 64,
            "controlled_fixture_receipts": [{
                "full_normalized_output_digest": "b" * 64,
                "runtime_versions": {"python": "3.14.3", "kernel": "0.2.0-dev"},
            }],
        }
        with tempfile.TemporaryDirectory() as temporary:
            target = _write_run_receipt_archive([validation], Path(temporary))
            payload = json.loads(target.read_text(encoding="utf-8"))
            digest = payload.pop("archive_digest")
            self.assertEqual(
                digest,
                hashlib.sha256(
                    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
            )
            self.assertEqual(payload["entries"][0]["receipts"], validation["controlled_fixture_receipts"])
            self.assertIn("platform", payload["executor"])

    def test_portable_fixture_identity_excludes_host_specific_observation(self):
        validation = {
            "controlled_fixture_receipt_digest": "a" * 64,
            "controlled_fixture_receipts": [
                {
                    "case_name": "controlled",
                    "case_digest": "b" * 64,
                    "module_id": "example",
                    "module_version": "1.0.0",
                    "compatibility_row_id": "python",
                    "full_normalized_output_digest": "c" * 64,
                    "validated_projection_digest": "d" * 64,
                    "runtime_versions": {"python": "3.14.3", "platform": "macOS"},
                    "reload_method": "json-round-trip",
                    "round_trip_kind": "process-json",
                }
            ],
        }
        baseline = _portable_validation_identity(validation)
        other_host = copy.deepcopy(validation)
        other_host["controlled_fixture_receipts"][0]["full_normalized_output_digest"] = "e" * 64
        other_host["controlled_fixture_receipts"][0]["runtime_versions"] = {
            "python": "3.10.18",
            "platform": "linux",
        }
        self.assertEqual(_portable_validation_identity(other_host), baseline)

        changed_scientific_projection = copy.deepcopy(validation)
        changed_scientific_projection["controlled_fixture_receipts"][0][
            "validated_projection_digest"
        ] = "f" * 64
        self.assertNotEqual(
            _portable_validation_identity(changed_scientific_projection), baseline
        )

    def test_statuses_distinguish_contract_executor_and_public_validation(self):
        report = build()
        self.assertEqual(report["schema_version"], 8)
        self.assertIn("validation_scope_counts", report)
        self.assertIn("engineering_validated", report["validation_scope_counts"])
        self.assertIn("method_validated", report["validation_scope_counts"])
        self.assertEqual(report["validation_scope_counts"]["project_promoted"], 0)
        self.assertIn("controlled_fixture_process_json_round_trip", report["axis_counts"])
        self.assertIn("controlled_fixture_artifact_payload_reloaded", report["axis_counts"])
        self.assertEqual(report["axis_counts"]["contract_valid"], report["module_count"])
        self.assertLess(report["axis_counts"]["representative_or_public_case_validated"], report["module_count"])
        self.assertEqual(report["axis_counts"]["current_project_reviewed"], 0)
        self.assertGreater(report["axis_counts"]["fixture_declared"], report["axis_counts"]["controlled_fixture_executed_and_reloaded"])
        self.assertFalse(report["single_maturity_count_is_authoritative"])
        self.assertNotIn("manual-adaptation", report["counts"])
        by_id = {record["module_id"]: record for record in report["records"]}
        self.assertTrue(by_id["bulk-ribosome-profiling"]["executor_ready"])
        self.assertTrue(by_id["bulk-r-loop-mapping"]["executor_ready"])
        self.assertTrue(by_id["bulk-r-loop-mapping"]["evidence_axes"]["adapter_static_reachable"])
        cuttag = next(
            row for row in by_id["bulk-r-loop-mapping"]["assay_readiness"]
            if row["assay"] == "cuttag"
        )
        self.assertEqual(cuttag["executor_module_id"], "bulk-chromatin-peak-calling")
        self.assertEqual(len(cuttag["executor_paths"]), 2)
        fastqc = by_id["read-quality-fastqc"]
        self.assertTrue(fastqc["engineering_validated"])
        self.assertFalse(fastqc["project_promoted"])
        self.assertIsNotNone(fastqc["controlled_fixture_portable_identity_digest"])
        self.assertEqual(fastqc["entry_surface_reachability"]["cli"]["mode"], "strict-project-artifact-execution")
        self.assertFalse(fastqc["entry_surface_reachability"]["mcp"]["reachable"])
        handoff = by_id["single-cell-batch-integration"]
        self.assertEqual(handoff["entry_surface_reachability"]["cli"]["mode"], "execution-handoff")
        self.assertFalse(handoff["entry_surface_reachability"]["cli"]["scientific_completion"])


if __name__ == "__main__":
    unittest.main()
