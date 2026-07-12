import json
import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from biomed_workbench.services.eutils import (
    CORE_DATABASES,
    EUtilitiesClient,
    EUtilitiesError,
    HTTPResponse,
)


class RecordingTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, url, data, headers, timeout):
        self.requests.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return self.responses.pop(0)


def json_response(value, status=200):
    return HTTPResponse(status=status, headers={"content-type": "application/json"}, body=json.dumps(value).encode())


class EUtilitiesContractTests(unittest.TestCase):
    def test_core_database_surface_spans_literature_sequences_and_archives(self):
        self.assertTrue(
            {"pubmed", "pmc", "gene", "protein", "nuccore", "sra", "gds", "biosample", "bioproject", "clinvar"}
            <= CORE_DATABASES
        )

    def test_search_normalizes_json_and_uses_zero_key_mode(self):
        transport = RecordingTransport(
            [json_response({"esearchresult": {"count": "2", "idlist": ["7157", "22059"], "querytranslation": "TP53"}})]
        )
        client = EUtilitiesClient(transport=transport, sleeper=lambda _seconds: None)

        result = client.search("gene", "TP53[Gene Name]", retmax=2)

        self.assertEqual(result.database, "gene")
        self.assertEqual(result.count, 2)
        self.assertEqual(result.ids, ("7157", "22059"))
        query = parse_qs(urlparse(transport.requests[0]["url"]).query)
        self.assertEqual(query["db"], ["gene"])
        self.assertEqual(query["retmode"], ["json"])
        self.assertNotIn("api_key", query)

    def test_optional_key_and_contact_metadata_are_shared_by_all_databases(self):
        responses = [
            json_response({"esearchresult": {"count": "0", "idlist": []}}),
            json_response({"esearchresult": {"count": "0", "idlist": []}}),
        ]
        transport = RecordingTransport(responses)
        with patch.dict(os.environ, {"NCBI_API_KEY": "test-key", "NCBI_EMAIL": "researcher@example.org"}, clear=False):
            client = EUtilitiesClient(transport=transport, sleeper=lambda _seconds: None)
            client.search("pubmed", "retina")
            client.search("clinvar", "TP53")

        for request in transport.requests:
            query = parse_qs(urlparse(request["url"]).query)
            self.assertEqual(query["api_key"], ["test-key"])
            self.assertEqual(query["email"], ["researcher@example.org"])
            self.assertEqual(query["tool"], ["biomed_workbench"])

    def test_summary_fetch_and_cross_database_link_are_composable(self):
        transport = RecordingTransport(
            [
                json_response({"result": {"uids": ["7157"], "7157": {"uid": "7157", "name": "TP53"}}}),
                HTTPResponse(200, {"content-type": "text/plain"}, b">NP_000537.3\nMEEPQ\n"),
                json_response(
                    {
                        "linksets": [
                            {
                                "ids": ["7157"],
                                "linksetdbs": [{"dbto": "protein", "linkname": "gene_protein", "links": ["4552149"]}],
                            }
                        ]
                    }
                ),
            ]
        )
        client = EUtilitiesClient(transport=transport, sleeper=lambda _seconds: None)

        summary = client.summary("gene", ["7157"])
        fetched = client.fetch("protein", ["NP_000537.3"], rettype="fasta", retmode="text")
        linked = client.link("gene", "protein", ["7157"])

        self.assertEqual(summary.records[0]["name"], "TP53")
        self.assertTrue(fetched.text.startswith(">NP_000537.3"))
        self.assertEqual(linked.links, ("4552149",))

    def test_history_search_can_feed_summary_without_copying_ids(self):
        transport = RecordingTransport(
            [
                json_response(
                    {
                        "esearchresult": {
                            "count": "1200",
                            "idlist": [],
                            "webenv": "MCID_abc",
                            "querykey": "1",
                        }
                    }
                ),
                json_response({"result": {"uids": []}}),
            ]
        )
        client = EUtilitiesClient(transport=transport, sleeper=lambda _seconds: None)

        search = client.search("pubmed", "developmental retina", retmax=0, use_history=True)
        client.summary("pubmed", webenv=search.webenv, query_key=search.query_key)

        query = parse_qs(urlparse(transport.requests[1]["url"]).query)
        self.assertEqual(query["WebEnv"], ["MCID_abc"])
        self.assertEqual(query["query_key"], ["1"])

    def test_long_requests_switch_to_post_and_errors_never_expose_key(self):
        transport = RecordingTransport([json_response({"error": "bad request"}, status=400)])
        with patch.dict(os.environ, {"NCBI_API_KEY": "private-key-value"}, clear=False):
            client = EUtilitiesClient(transport=transport, sleeper=lambda _seconds: None)
            with self.assertRaises(EUtilitiesError) as caught:
                client.fetch("gene", [str(index) for index in range(500)])

        self.assertIsNotNone(transport.requests[0]["data"])
        self.assertNotIn("private-key-value", str(caught.exception))

    def test_invalid_database_and_unbounded_page_are_rejected_before_network(self):
        transport = RecordingTransport([])
        client = EUtilitiesClient(transport=transport, sleeper=lambda _seconds: None)

        with self.assertRaises(ValueError):
            client.search("gene&api_key=leak", "TP53")
        with self.assertRaises(ValueError):
            client.search("gene", "TP53", retmax=100_001)
        self.assertEqual(transport.requests, [])


if __name__ == "__main__":
    unittest.main()
