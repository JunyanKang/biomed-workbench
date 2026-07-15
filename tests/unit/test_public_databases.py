import json
import unittest

from biomed_workbench.services.public_databases import (
    HTTPResponse,
    PublicDatabaseError,
    PublicJSONClient,
    alphafold_structure_records,
    clinical_trial_records,
    preprint_record,
    pubchem_compound,
    rcsb_ligand_records,
    rcsb_polymer_entity_records,
    rcsb_structure_search,
    rcsb_structure_records,
    resolve_citation_record,
)


class FixtureTransport:
    def __init__(self, routes):
        self.routes = routes
        self.urls = []

    def __call__(self, url, _headers, _timeout):
        self.urls.append(url)
        for fragment, response in self.routes:
            if fragment in url:
                payload = response() if callable(response) else response
                if isinstance(payload, HTTPResponse):
                    return payload
                return HTTPResponse(200, {"Content-Type": "application/json"}, json.dumps(payload).encode())
        raise AssertionError(f"unmatched fixture URL: {url}")


class PublicDatabaseTests(unittest.TestCase):
    def client(self, routes):
        return PublicJSONClient(transport=FixtureTransport(routes), retries=0, sleeper=lambda _: None)

    def test_citation_resolution_preserves_cross_source_disagreement(self):
        client = self.client(
            [
                (
                    "api.crossref.org/v1/works/10.1000%2Ftest",
                    {
                        "message": {
                            "DOI": "10.1000/test",
                            "title": ["Registered title"],
                            "type": "journal-article",
                            "publisher": "Example Publisher",
                            "container-title": ["Example Journal"],
                            "published": {"date-parts": [[2025, 1, 2]]},
                            "author": [{"given": "A", "family": "Author"}],
                            "is-referenced-by-count": 4,
                            "relation": {},
                            "update-to": [],
                        }
                    },
                ),
                (
                    "europepmc/webservices/rest/search",
                    {
                        "resultList": {
                            "result": [
                                {"doi": "10.1000/test", "title": "Repository title", "pmid": "123"},
                                {"doi": "10.1000/other", "title": "Wrong DOI"},
                            ]
                        }
                    },
                ),
            ]
        )
        result = resolve_citation_record("https://doi.org/10.1000/TEST", client=client)
        self.assertEqual(result["query"]["doi"], "10.1000/test")
        self.assertEqual(result["crossref"]["title"], "Registered title")
        self.assertEqual([record["pmid"] for record in result["europe_pmc_records"]], ["123"])
        self.assertEqual(result["agreement"]["europe_pmc_exact_doi_matches"], 1)
        self.assertIn("disagree", result["limitations"][0])

    def test_preprint_versions_are_retained_and_sorted(self):
        client = self.client(
            [
                (
                    "api.biorxiv.org/details/biorxiv/10.1101/2024.01.01.123456/na/json",
                    {
                        "collection": [
                            {"doi": "10.1101/2024.01.01.123456", "version": "2", "date": "2024-02-01", "published": "10.1000/final"},
                            {"doi": "10.1101/2024.01.01.123456", "version": "1", "date": "2024-01-01", "published": "NA"},
                        ]
                    },
                )
            ]
        )
        result = preprint_record("10.1101/2024.01.01.123456", "biorxiv", client=client)
        self.assertEqual([record["version"] for record in result["versions"]], ["1", "2"])
        self.assertEqual(result["latest_version"]["version"], "2")
        self.assertEqual(result["published_dois"], ["10.1000/final"])

    def test_pubchem_retains_identity_and_stereochemistry(self):
        properties = {
            "PropertyTable": {
                "Properties": [
                    {
                        "CID": 2244,
                        "Title": "Aspirin",
                        "MolecularFormula": "C9H8O4",
                        "SMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
                        "ConnectivitySMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
                        "InChIKey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
                    }
                ]
            }
        }
        synonyms = {"InformationList": {"Information": [{"CID": 2244, "Synonym": ["Aspirin", "Acetylsalicylic acid"]}]}}
        client = self.client([("/property/", properties), ("/cid/2244/synonyms/", synonyms)])
        result = pubchem_compound("aspirin", client=client)
        self.assertEqual(result["identity_checks"]["unique_cids"], [2244])
        self.assertTrue(result["identity_checks"]["stereochemistry_fields_retained"])
        self.assertEqual(result["synonyms"][1], "Acetylsalicylic acid")

    def test_clinical_trial_parser_retains_protocol_and_results_state(self):
        study = {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT00000001", "briefTitle": "Trial", "officialTitle": "A Trial"},
                "designModule": {
                    "studyType": "INTERVENTIONAL",
                    "phases": ["PHASE2"],
                    "enrollmentInfo": {"count": 120, "type": "ACTUAL"},
                    "designInfo": {"allocation": "RANDOMIZED", "interventionModel": "PARALLEL"},
                },
                "statusModule": {"overallStatus": "COMPLETED"},
            },
            "hasResults": True,
            "resultsSection": {"participantFlowModule": {}},
        }
        client = self.client([("/api/v2/studies", {"studies": [study], "totalCount": 1})])
        result = clinical_trial_records("retina", client=client)
        self.assertEqual(result["studies"][0]["nct_id"], "NCT00000001")
        self.assertEqual(result["studies"][0]["enrollment"]["count"], 120)
        self.assertTrue(result["studies"][0]["has_results"])
        self.assertEqual(result["api_total_count"], 1)
        self.assertFalse(result["records_truncated"])
        self.assertEqual(result["local_post_filters_applied"], [])

    def test_clinical_trial_filters_paginate_and_reconcile_total(self):
        def study(nct_id):
            return {
                "protocolSection": {
                    "identificationModule": {"nctId": nct_id, "briefTitle": nct_id},
                    "designModule": {"studyType": "INTERVENTIONAL", "phases": ["PHASE2"]},
                    "statusModule": {"overallStatus": "COMPLETED"},
                },
                "hasResults": False,
            }

        class PagingTransport:
            def __init__(self):
                self.urls = []

            def __call__(self, url, _headers, _timeout):
                self.urls.append(url)
                payload = (
                    {"studies": [study("NCT00000002")], "totalCount": 2, "nextPageToken": "next-token"}
                    if "pageToken=" not in url
                    else {"studies": [study("NCT00000001")]}
                )
                return HTTPResponse(200, {}, json.dumps(payload).encode())

        transport = PagingTransport()
        client = PublicJSONClient(transport=transport, retries=0, sleeper=lambda _: None)
        result = clinical_trial_records(
            filters={
                "condition": "retinal degeneration",
                "overall_status": ["COMPLETED"],
                "phase": ["PHASE2", "PHASE3"],
                "enrollment_min": 10,
                "first_posted_end": "2025-12-31",
                "location_city": "Boston",
                "location_country": "United States",
                "location_recruiting_only": True,
                "investigator": "Jane Smith",
                "investigator_role": "official",
                "sponsor_name": "National Institutes of Health",
                "sponsor_scope": "any",
                "eligibility_keywords": ["confirmed diagnosis"],
            },
            page_size=1,
            max_records=10,
            client=client,
        )
        self.assertEqual(result["nct_ids"], ["NCT00000001", "NCT00000002"])
        self.assertEqual(result["api_total_count"], 2)
        self.assertEqual(len(result["provenance"]["requests"]), 2)
        self.assertFalse(result["records_truncated"])
        first_url = transport.urls[0]
        self.assertIn("query.cond=retinal+degeneration", first_url)
        self.assertIn("filter.overallStatus=COMPLETED", first_url)
        self.assertIn("SEARCH%5BLocation%5D", first_url)
        self.assertIn("LocationCountry", first_url)
        self.assertIn("OverallOfficialName", first_url)
        self.assertIn("CollaboratorName", first_url)
        self.assertIn("EligibilityCriteria", first_url)

    def test_clinical_trial_truncation_and_invalid_filters_are_explicit(self):
        study = {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT00000001"},
                "designModule": {"studyType": "OBSERVATIONAL"},
                "statusModule": {"overallStatus": "COMPLETED"},
            }
        }
        client = self.client([("/api/v2/studies", {"studies": [study], "totalCount": 20, "nextPageToken": "more"})])
        result = clinical_trial_records("retina", page_size=1, max_records=1, client=client)
        self.assertTrue(result["records_truncated"])
        self.assertTrue(result["next_page_token_present"])
        with self.assertRaises(ValueError):
            clinical_trial_records(filters={"unknown": "value"}, client=client)
        with self.assertRaises(ValueError):
            clinical_trial_records(filters={"phase": ["PHASE9"]}, client=client)

    def test_rcsb_parser_validates_identifier_and_retains_quality_context(self):
        payload = {
            "rcsb_id": "4HHB",
            "struct": {"title": "Hemoglobin"},
            "exptl": [{"method": "X-RAY DIFFRACTION"}],
            "rcsb_entry_info": {"resolution_combined": [1.74]},
            "rcsb_accession_info": {"initial_release_date": "1984-07-17"},
            "rcsb_primary_citation": {"pdbx_database_id_DOI": "10.1000/example"},
            "rcsb_entry_container_identifiers": {"polymer_entity_ids": ["1", "2"]},
            "pdbx_database_status": {"status_code": "REL"},
        }
        client = self.client([("/rest/v1/core/entry/4HHB", payload)])
        result = rcsb_structure_records(["4hhb"], client=client)
        self.assertEqual(result["structures"][0]["resolution_combined"], [1.74])
        self.assertEqual(result["structures"][0]["experimental_methods"], ["X-RAY DIFFRACTION"])

    def test_rcsb_search_pages_and_reconciles_api_total(self):
        class SearchTransport:
            def __init__(self):
                self.payloads = []

            def __call__(self, _url, _headers, body, _timeout):
                request = json.loads(body)
                self.payloads.append(request)
                start = request["request_options"]["paginate"]["start"]
                page = (
                    [{"identifier": "4HHB", "score": 1.0}, {"identifier": "1TUP", "score": 0.9}]
                    if start == 0
                    else [{"identifier": "1CRN", "score": 0.8}]
                )
                return HTTPResponse(200, {}, json.dumps({"total_count": 3, "result_set": page}).encode())

        transport = SearchTransport()
        client = PublicJSONClient(post_transport=transport, retries=0, sleeper=lambda _: None)
        result = rcsb_structure_search(
            organism="Homo sapiens",
            experimental_method="X-RAY DIFFRACTION",
            max_resolution=2.5,
            max_records=3,
            client=client,
        )
        self.assertEqual([record["pdb_id"] for record in result["records"]], ["4HHB", "1TUP", "1CRN"])
        self.assertEqual(result["total_count"], 3)
        self.assertFalse(result["records_truncated"])
        self.assertEqual(len(transport.payloads), 2)
        self.assertEqual(transport.payloads[1]["request_options"]["paginate"]["start"], 2)

    def test_rcsb_search_treats_first_page_204_as_explicit_zero_results(self):
        class EmptySearchTransport:
            def __call__(self, _url, _headers, _body, _timeout):
                return HTTPResponse(204, {}, b"")

        client = PublicJSONClient(post_transport=EmptySearchTransport(), retries=0, sleeper=lambda _: None)
        result = rcsb_structure_search(text="no-such-structure-query", client=client)
        self.assertEqual(result["total_count"], 0)
        self.assertEqual(result["returned_count"], 0)
        self.assertEqual(result["records"], [])
        self.assertFalse(result["records_truncated"])
        self.assertEqual(result["provenance"]["requests"][0]["request"]["status_code"], 204)

    def test_rcsb_polymer_entities_preserve_sequence_and_not_found(self):
        entry = {"rcsb_entry_container_identifiers": {"polymer_entity_ids": ["1", "2"]}}
        entity = {
            "rcsb_id": "4HHB_1",
            "rcsb_polymer_entity": {"pdbx_description": "Hemoglobin subunit alpha"},
            "rcsb_polymer_entity_container_identifiers": {"entry_id": "4HHB", "entity_id": "1", "uniprot_ids": ["P69905"]},
            "entity_poly": {"rcsb_entity_polymer_type": "Protein", "rcsb_sample_sequence_length": 141, "pdbx_seq_one_letter_code_can": "VLSPADKT"},
            "rcsb_entity_source_organism": [{"scientific_name": "Homo sapiens", "ncbi_taxonomy_id": 9606}],
        }
        client = self.client(
            [
                ("/entry/4HHB", entry),
                ("/polymer_entity/4HHB/1", entity),
                ("/polymer_entity/4HHB/2", HTTPResponse(404, {}, b"{}")),
            ]
        )
        result = rcsb_polymer_entity_records("4hhb", include_sequences=True, client=client)
        self.assertEqual(result["entry_polymer_entity_count"], 2)
        self.assertEqual(result["entities"][0]["sequence"], "VLSPADKT")
        self.assertEqual(result["not_found"], ["2"])

    def test_rcsb_ligand_chain_retains_component_identity_and_missing_state(self):
        entry = {"rcsb_entry_container_identifiers": {"non_polymer_entity_ids": ["1", "2"]}}
        entity = {
            "rcsb_nonpolymer_entity_container_identifiers": {"entity_id": "1", "nonpolymer_comp_id": "HEM", "auth_asym_ids": ["A"]},
            "rcsb_nonpolymer_entity": {"pdbx_description": "Heme", "pdbx_number_of_molecules": 1},
        }
        component = {
            "chem_comp": {"id": "HEM", "name": "PROTOPORPHYRIN IX CONTAINING FE", "formula": "C34 H32 Fe N4 O4", "pdbx_formal_charge": 0},
            "rcsb_chem_comp_descriptor": {"InChIKey": "KABFMIBPWCXCRK-RGGAHWMASA-L", "SMILES_stereo": "[Fe]"},
        }
        client = self.client(
            [
                ("/entry/4HHB", entry),
                ("/nonpolymer_entity/4HHB/1", entity),
                ("/nonpolymer_entity/4HHB/2", HTTPResponse(404, {}, b"{}")),
                ("/chemcomp/HEM", component),
            ]
        )
        result = rcsb_ligand_records("4HHB", client=client)
        self.assertEqual(result["ligands"][0]["chemical_component"]["comp_id"], "HEM")
        self.assertEqual(result["not_found_entity_ids"], ["2"])
        self.assertFalse(result["records_truncated"])

    def test_alphafold_records_preserve_model_confidence_versions_and_absence(self):
        model = {
            "modelEntityId": "AF-P04637-F1",
            "entryId": "AF-P04637-F1",
            "providerId": "GDM",
            "toolUsed": "AlphaFold Monomer v2.0 pipeline",
            "uniprotAccession": "P04637",
            "uniprotId": "P53_HUMAN",
            "uniprotDescription": "Cellular tumor antigen p53",
            "gene": "TP53",
            "organismScientificName": "Homo sapiens",
            "taxId": 9606,
            "sequence": "MEEPQ",
            "uniprotStart": 1,
            "uniprotEnd": 5,
            "globalMetricValue": 72.5,
            "fractionPlddtVeryLow": 0.1,
            "fractionPlddtLow": 0.2,
            "fractionPlddtConfident": 0.3,
            "fractionPlddtVeryHigh": 0.4,
            "latestVersion": 6,
            "allVersions": [1, 2, 3, 4, 5, 6],
            "modelCreatedDate": "2025-08-01",
            "cifUrl": "https://alphafold.ebi.ac.uk/files/AF-P04637-F1-model_v6.cif",
            "paeDocUrl": "https://alphafold.ebi.ac.uk/files/AF-P04637-F1-predicted_aligned_error_v6.json",
        }
        client = self.client(
            [
                ("/api/prediction/P04637", [model]),
                ("/api/prediction/Q9Y6K9", HTTPResponse(404, {}, b"{}")),
            ]
        )
        result = alphafold_structure_records(["p04637", "Q9Y6K9"], include_sequence=True, client=client)
        self.assertEqual(result["requested_count"], 2)
        self.assertEqual(result["covered_count"], 1)
        self.assertEqual(result["not_covered_count"], 1)
        self.assertEqual(result["records"][0]["models"][0]["sequence"], "MEEPQ")
        self.assertEqual(result["records"][0]["models"][0]["global_plddt"], 72.5)
        self.assertEqual(result["records"][0]["models"][0]["fraction_plddt_sum"], 1.0)
        self.assertFalse(result["records"][1]["has_model"])
        self.assertTrue(result["provenance"]["requests"][1]["not_found"])

    def test_alphafold_blocks_invalid_accessions_and_confidence(self):
        with self.assertRaises(ValueError):
            alphafold_structure_records(["TP53"], client=self.client([]))
        bad = {"uniprotAccession": "P04637", "globalMetricValue": 101}
        with self.assertRaisesRegex(PublicDatabaseError, "pLDDT range"):
            alphafold_structure_records(
                ["P04637"],
                client=self.client([("/api/prediction/P04637", [bad])]),
            )

    def test_post_transport_rejects_unapproved_hosts_and_oversized_payloads(self):
        client = PublicJSONClient(post_transport=lambda *_: HTTPResponse(200, {}, b"{}"), retries=0)
        with self.assertRaises(ValueError):
            client.post_with_metadata("https://example.com", "/query", {})
        with self.assertRaises(ValueError):
            client.post_with_metadata("https://search.rcsb.org", "/rcsbsearch/v2/query", {"value": "x" * (1024 * 1024)})

    def test_transport_blocks_unapproved_hosts_and_invalid_responses(self):
        client = self.client([])
        with self.assertRaises(ValueError):
            client.get("https://example.com", "/data")
        invalid = PublicJSONClient(
            transport=lambda *_: HTTPResponse(200, {}, b"not-json"),
            retries=0,
            sleeper=lambda _: None,
        )
        with self.assertRaises(PublicDatabaseError):
            invalid.get("https://api.crossref.org", "/v1/works")
        failed = PublicJSONClient(
            transport=lambda *_: HTTPResponse(503, {}, b"{}"),
            retries=0,
            sleeper=lambda _: None,
        )
        with self.assertRaisesRegex(PublicDatabaseError, "HTTP 503"):
            failed.get("https://api.crossref.org", "/v1/works")


if __name__ == "__main__":
    unittest.main()
