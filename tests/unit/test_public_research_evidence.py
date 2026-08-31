import json
import unittest

from biomed_workbench.services.public_databases import HTTPResponse, PublicJSONClient
from biomed_workbench.services.research_evidence import (
    query_public_research_evidence,
    synthesize_public_evidence,
)


class PublicResearchEvidenceTests(unittest.TestCase):
    def test_every_registered_operation_uses_its_source_specific_container(self):
        cases = [
            ("gwas-catalog", "studies-by-trait", {"_embedded": {"studies": [{"accessionId": "GCST1"}]}}),
            ("gwas-catalog", "associations-by-gene", {"_embedded": {"associations": [{"riskFrequency": 0.1}]}}),
            ("chembl", "molecule-search", {"molecules": [{"molecule_chembl_id": "CHEMBL25"}]}),
            ("chembl", "activities-by-molecule", {"activities": [{"activity_id": 1}]}),
            ("pride", "projects", [{"accession": "PXD1"}]),
            ("biostudies", "studies", {"hits": [{"accession": "S-BSST1"}]}),
            ("encode", "experiments", {"@graph": [{"accession": "ENCSR1"}]}),
            ("human-protein-atlas", "gene", [{"Gene": "BANP"}]),
            ("mgnify", "studies", {"data": [{"id": "MGYS1"}]}),
        ]
        for source, operation, payload in cases:
            with self.subTest(source=source, operation=operation):
                def transport(url, headers, timeout, body=payload):
                    return HTTPResponse(200, {"Content-Type": "application/json"}, json.dumps(body).encode())

                result = query_public_research_evidence(
                    source, operation, "retina", 1,
                    client=PublicJSONClient(transport=transport, retries=0),
                )
                self.assertEqual(result["returned_count"], 1)
                self.assertEqual(result["source"], source)

    def test_query_uses_registered_endpoint_and_normalizes_records(self):
        observed = {}

        def transport(url, headers, timeout):
            observed["url"] = url
            return HTTPResponse(200, {"Content-Type": "application/json"}, json.dumps({
                "molecules": [{"molecule_chembl_id": "CHEMBL25", "pref_name": "ASPIRIN"}],
            }).encode())

        result = query_public_research_evidence(
            "chembl", "molecule-search", "aspirin", 10,
            client=PublicJSONClient(transport=transport, retries=0),
        )
        self.assertIn("/chembl/api/data/molecule/search.json", observed["url"])
        self.assertIn("q=aspirin", observed["url"])
        self.assertEqual(result["records"][0]["molecule_chembl_id"], "CHEMBL25")

    def test_unknown_source_cannot_be_used_as_arbitrary_url(self):
        with self.assertRaises(ValueError):
            query_public_research_evidence("arbitrary", "get", "https://example.org")

    def test_synthesis_detects_entity_mismatch_and_preserves_observations(self):
        result = synthesize_public_evidence(
            "Is BANP associated with retinal development?",
            [{
                "source": "example", "record_id": "r1", "evidence_type": "expression",
                "observation": "Expression was detected", "source_url": "https://example.org/r1",
                "entity": "OTHER", "supports": "context",
            }],
            expected_entity="BANP",
        )
        self.assertFalse(result["usable_for_interpretation"])
        self.assertEqual(result["concerns"][0]["code"], "ENTITY_MISMATCH")


if __name__ == "__main__":
    unittest.main()
