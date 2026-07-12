import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "research-engine-verification.json"
FIXTURES = ROOT / "tests" / "fixtures" / "research-cycles"


class ResearchEngineEvidenceTests(unittest.TestCase):
    def test_report_covers_all_plan_types_gates_revisions_transitions_and_replays(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        scenarios = report["scenarios"]

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_count"], 48)
        self.assertGreaterEqual(report["test_count"], 306)
        self.assertEqual(
            set(report["execution_contracts"]),
            {"scientific_command", "command_input_binding", "command_output_binding", "bounded_process_result"},
        )
        self.assertEqual(report["scenario_count"], 4)
        self.assertEqual({item["plan_type"] for item in scenarios}, {"single", "serial", "parallel", "mixed"})
        self.assertEqual(report["strict_compatibility_blocks"], 4)
        self.assertEqual(report["plan_revisions"], 4)
        self.assertEqual(report["alternative_substitutions"], 4)
        self.assertEqual(report["successful_replays"], 4)
        self.assertTrue(all(item["failed_gate_code"] and item["hypothesis_transition"][0] != item["hypothesis_transition"][1] for item in scenarios))
        self.assertTrue(all(item["revision_count"] >= 1 and item["alternative_substitution_count"] >= 1 for item in scenarios))
        self.assertTrue(all(item["evidence_count"] >= 1 and item["replay_passed"] for item in scenarios))

    def test_fixture_and_report_digests_match(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        reported = {item["id"]: item["final_state_digest"] for item in report["scenarios"]}
        fixtures = {payload["id"]: payload["expected_replay_digest"] for payload in (json.loads(path.read_text()) for path in FIXTURES.glob("*.json"))}

        self.assertEqual(reported, fixtures)
        self.assertTrue(all(len(value) == 64 for value in fixtures.values()))

    def test_report_and_fixtures_are_path_credential_and_source_neutral(self):
        text = REPORT.read_text(encoding="utf-8") + "".join(path.read_text(encoding="utf-8") for path in FIXTURES.glob("*.json"))
        for marker in ("/Users/", "/private/", "NCBI_API_KEY", "nvapi-", "source_path"):
            self.assertNotIn(marker, text)
        self.assertGreaterEqual(len(json.loads(REPORT.read_text())["limitations"]), 4)

    def test_large_artifact_contract_is_project_relative_and_content_addressed(self):
        from biomed_workbench.kernel.artifact_store import ArtifactPayload

        digest = "a" * 64
        payload = ArtifactPayload("reads", f"sha256/aa/{digest}/payload", "application/gzip", 100, digest).to_dict()
        serialized = json.dumps(payload, sort_keys=True)

        self.assertEqual(set(payload), {"role", "object_key", "media_type", "byte_size", "sha256"})
        self.assertFalse(Path(payload["object_key"]).is_absolute())
        for marker in ("/Users/", "/Volumes/", "file://", "sample.fastq", "API_KEY"):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
