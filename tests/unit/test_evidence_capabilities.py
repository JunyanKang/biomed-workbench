import unittest
from unittest.mock import patch

from biomed_workbench.capabilities.evidence import gene_evidence, literature_evidence, variant_evidence
from biomed_workbench.services.eutils import LinkResult, SearchResult, SummaryResult


class EvidenceCapabilityTests(unittest.TestCase):
    def test_gene_evidence_composes_gene_protein_clinvar_and_pubmed(self):
        client = self._client()
        client.search.return_value = SearchResult("gene", 1, ("7157",), "TP53", None, None)
        client.summary.return_value = SummaryResult("gene", ({"uid": "7157", "name": "TP53", "description": "tumor protein p53"},))
        client.link.side_effect = [
            LinkResult("gene", "protein", ("7157",), ("4552149", "P04637"), ("gene_protein",)),
            LinkResult("gene", "clinvar", ("7157",), ("123",), ("gene_clinvar",)),
            LinkResult("gene", "pubmed", ("7157",), ("1000", "1001"), ("gene_pubmed",)),
        ]

        with patch("biomed_workbench.capabilities.evidence.EUtilitiesClient", return_value=client):
            result = gene_evidence("TP53", organism="human", max_links=1)

        self.assertEqual(result["gene_records"][0]["name"], "TP53")
        self.assertEqual(result["linked"]["protein"]["ids"], ["4552149"])
        self.assertEqual(result["linked"]["clinvar"]["total"], 1)
        self.assertEqual(result["linked"]["pubmed"]["total"], 2)
        self.assertEqual(client.link.call_count, 3)

    def test_variant_evidence_links_clinvar_to_gene_and_literature(self):
        client = self._client()
        client.search.return_value = SearchResult("clinvar", 1, ("123",), "TP53", None, None)
        client.summary.return_value = SummaryResult("clinvar", ({"uid": "123", "title": "Pathogenic TP53 variant"},))
        client.link.side_effect = [
            LinkResult("clinvar", "gene", ("123",), ("7157",), ("clinvar_gene",)),
            LinkResult("clinvar", "pubmed", ("123",), ("1000",), ("clinvar_pubmed",)),
        ]

        with patch("biomed_workbench.capabilities.evidence.EUtilitiesClient", return_value=client):
            result = variant_evidence("TP53[gene]", max_records=1)

        self.assertEqual(result["variant_records"][0]["uid"], "123")
        self.assertEqual(result["linked"]["gene"]["ids"], ["7157"])

    def test_literature_evidence_keeps_query_translation_and_records(self):
        client = self._client()
        client.search.return_value = SearchResult("pubmed", 2, ("1", "2"), "retinal development", None, None)
        client.summary.return_value = SummaryResult("pubmed", ({"uid": "1", "title": "A"}, {"uid": "2", "title": "B"}))

        with patch("biomed_workbench.capabilities.evidence.EUtilitiesClient", return_value=client):
            result = literature_evidence("retinal development", max_records=2)

        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["query_translation"], "retinal development")

    @staticmethod
    def _client():
        from unittest.mock import Mock

        return Mock()


if __name__ == "__main__":
    unittest.main()
