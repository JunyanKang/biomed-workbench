import json
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[2]
MODULE_IDS = (
    "bulk-chromatin-accessibility",
    "bulk-dna-methylation",
    "bulk-nascent-transcription",
    "bulk-r-loop-mapping",
    "bulk-rbp-rna-binding",
    "bulk-ribosome-profiling",
    "bulk-rna-modification-enrichment",
    "bulk-three-dimensional-genome",
)


class BulkAssayContractEvidenceTests(unittest.TestCase):
    def test_contract_reports_are_current_and_do_not_claim_biological_execution(self):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        for module_id in MODULE_IDS:
            report = json.loads(
                (ROOT / "reports" / f"{module_id}-contract-verification.json").read_text(encoding="utf-8")
            )
            self.assertTrue(report["passed"])
            self.assertEqual(report["module_id"], module_id)
            self.assertEqual(report["module_version"], registry.get(module_id).version)
            self.assertEqual(report["registry_digest"], registry.digest)
            self.assertTrue(report["execution"]["packaged_contract_executed"])
            self.assertTrue(report["execution"]["contract_reloaded"])
            self.assertTrue(report["execution"]["input_immutability_verified"])
            self.assertFalse(report["execution"]["external_workflow_executed"])
            self.assertFalse(report["execution"]["biological_result_generated"])
            self.assertFalse(report["execution"]["public_data_acceptance"])


if __name__ == "__main__":
    unittest.main()
