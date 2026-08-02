import json
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.evidence_scope import evidence_scope_is_current
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.services.public_databases import (
    ALPHAFOLD_CONTRACT_VERSION,
    BIORXIV_CONTRACT_VERSION,
    CLINICAL_TRIALS_CONTRACT_VERSION,
    CROSSREF_CONTRACT_VERSION,
    EUROPE_PMC_CONTRACT_VERSION,
    PUBCHEM_CONTRACT_VERSION,
    RCSB_CONTRACT_VERSION,
    RCSB_SEARCH_CONTRACT_VERSION,
    STRING_CONTRACT_VERSION,
)


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "public-database-live-verification.json"
MODULE_IDS = {
    "citation-record-resolution",
    "preprint-evidence",
    "chemical-evidence",
    "clinical-trial-evidence",
    "structure-evidence",
    "structure-search",
    "structure-polymer-entities",
    "structure-ligands",
    "alphafold-structure-evidence",
    "protein-interaction-network-evidence",
}


class PublicDatabaseEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.registry = ModuleRegistry.discover(BUILTIN_ROOT)

    def test_live_evidence_is_bound_to_current_modules_and_contracts(self):
        expected_contracts = {
            "alphafold-db-api": ALPHAFOLD_CONTRACT_VERSION,
            "biorxiv-details": BIORXIV_CONTRACT_VERSION,
            "clinicaltrials-gov-api": CLINICAL_TRIALS_CONTRACT_VERSION,
            "crossref-rest": CROSSREF_CONTRACT_VERSION,
            "europe-pmc-rest": EUROPE_PMC_CONTRACT_VERSION,
            "pubchem-pug-rest": PUBCHEM_CONTRACT_VERSION,
            "rcsb-pdb-data-api": RCSB_CONTRACT_VERSION,
            "rcsb-pdb-search-api": RCSB_SEARCH_CONTRACT_VERSION,
            "string-api": STRING_CONTRACT_VERSION,
        }

        self.assertTrue(self.report["passed"])
        self.assertTrue(evidence_scope_is_current(self.report, self.registry))
        self.assertEqual(set(self.report["module_ids"]), MODULE_IDS)
        self.assertEqual(self.report["contracts"], expected_contracts)

    def test_all_database_checks_and_module_packages_pass(self):
        expected_checks = {
            "citation_record_resolution",
            "preprint_version_history",
            "compound_identity",
            "trial_design_record",
            "structure_entry_context",
            "structure_attribute_search",
            "structure_polymer_entities",
            "structure_bound_ligands",
            "structure_prediction_metadata",
            "protein_interaction_network",
        }
        packages = self.report["module_package_validation"]

        self.assertEqual({item["name"] for item in self.report["checks"]}, expected_checks)
        self.assertTrue(all(item["passed"] for item in self.report["checks"]))
        self.assertEqual(set(packages), MODULE_IDS)
        for module_id, package in packages.items():
            self.assertTrue(package["valid"])
            self.assertEqual(package["executed_test_cases"], 1)
            self.assertEqual(package["module_version"], self.registry.get(module_id).version)

    def test_scientific_quality_assertions_are_explicit(self):
        summary = self.report["scientific_summary"]

        self.assertGreaterEqual(len(summary), 9)
        self.assertEqual(set(summary.values()), {True})
        self.assertTrue(summary["cross_source_disagreement_not_silently_merged"])
        self.assertTrue(summary["preprint_versions_not_collapsed"])
        self.assertTrue(summary["alphafold_model_version_and_confidence_context_retained"])
        self.assertTrue(summary["string_mapping_network_type_score_and_release_retained"])
        self.assertTrue(summary["no_new_credentials_required"])

    def test_public_evidence_contains_no_local_path_or_credential(self):
        serialized = REPORT.read_text(encoding="utf-8")

        for marker in ("/Users/", "/private/", "file://", "api_key=", "ACCESS_TOKEN=", "sk-"):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
