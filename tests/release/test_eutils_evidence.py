import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "eutils-live-verification.json"
ZERO_KEY_REPORT = ROOT / "reports" / "eutils-live-zero-key-verification.json"


class EUtilitiesEvidenceTests(unittest.TestCase):
    def test_live_report_covers_multiple_database_families_with_key(self):
        payload = json.loads(REPORT.read_text(encoding="utf-8"))
        databases = {check["database"] for check in payload["checks"]}

        self.assertTrue(payload["passed"])
        self.assertEqual(payload["credential_mode"], "api_key")
        self.assertGreaterEqual(len(payload["checks"]), 10)
        self.assertTrue({"pubmed", "pmc", "gene", "protein", "nuccore", "clinvar", "sra"} <= databases)
        self.assertIn("gene_evidence_bundle", databases)
        self.assertTrue(all(check["passed"] for check in payload["checks"]))

    def test_live_report_contains_no_secret_or_request_query(self):
        serialized = REPORT.read_text(encoding="utf-8")

        self.assertNotIn("api_key=", serialized.lower())
        self.assertNotIn("NCBI_API_KEY", serialized)
        self.assertNotIn("/Users/", serialized)

    def test_zero_key_supplement_covers_info_literature_and_variant_workflows(self):
        payload = json.loads(ZERO_KEY_REPORT.read_text(encoding="utf-8"))
        covered = {(check["name"], check["database"]) for check in payload["checks"] if check["passed"]}

        self.assertTrue(payload["passed"])
        self.assertEqual(payload["credential_mode"], "zero_key")
        self.assertTrue(
            {
                ("info", "entrez"),
                ("composed_workflow", "literature_evidence_bundle"),
                ("composed_workflow", "variant_evidence_bundle"),
            }
            <= covered
        )


if __name__ == "__main__":
    unittest.main()
