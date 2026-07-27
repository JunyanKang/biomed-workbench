import unittest
from unittest.mock import patch

from biomed_workbench.capabilities.evidence import dbsnp_rsid_evidence, gene_evidence, literature_evidence, resolve_gene_identifier, variant_evidence
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

    def test_dbsnp_rsid_evidence_preserves_exact_reference_identifier(self):
        client = self._client()
        client.search.return_value = SearchResult("snp", 1, ("12345",), "rs12345", None, None)
        client.summary.return_value = SummaryResult("snp", ({"uid": "12345", "snp_id": "rs12345", "title": "Reference SNP"},))

        with patch("biomed_workbench.capabilities.evidence.EUtilitiesClient", return_value=client):
            result = dbsnp_rsid_evidence("RS12345")

        self.assertEqual(result["rsid"], "rs12345")
        self.assertEqual(result["resolution_status"], "resolved")
        self.assertEqual(result["records"][0]["uid"], "12345")

    def test_gene_identifier_resolution_requires_one_exact_current_symbol(self):
        client = self._client()
        client.search.return_value = SearchResult("gene", 2, ("7157", "999"), "TP53", None, None)
        client.summary.return_value = SummaryResult(
            "gene",
            (
                {"uid": "7157", "name": "TP53", "description": "tumor protein p53", "organism": {"taxid": 9606, "commonname": "human", "scientificname": "Homo sapiens"}},
                {"uid": "999", "name": "TP53P1", "description": "pseudogene", "organism": {"taxid": 9606, "commonname": "human", "scientificname": "Homo sapiens"}},
            ),
        )

        result = resolve_gene_identifier("TP53", "human", client=client)

        self.assertEqual(result["resolution_status"], "resolved")
        self.assertEqual(result["resolved"]["gene_id"], "7157")
        self.assertEqual(len(result["candidates"]), 2)

    def test_gene_identifier_resolution_keeps_ambiguous_candidates_unusable(self):
        client = self._client()
        client.search.return_value = SearchResult("gene", 2, ("1", "2"), "ABC", None, None)
        client.summary.return_value = SummaryResult(
            "gene",
            (
                {"uid": "1", "name": "ABC", "organism": {"taxid": 9606, "commonname": "human", "scientificname": "Homo sapiens"}},
                {"uid": "2", "nomenclaturesymbol": "ABC", "organism": {"taxid": 9606, "commonname": "human", "scientificname": "Homo sapiens"}},
            ),
        )

        result = resolve_gene_identifier("ABC", "human", client=client)

        self.assertEqual(result["resolution_status"], "ambiguous")
        self.assertIsNone(result["resolved"])
        self.assertTrue(result["warnings"])

    def test_gene_identifier_resolution_rejects_an_exact_symbol_from_the_wrong_species(self):
        client = self._client()
        client.search.return_value = SearchResult("gene", 1, ("22059",), "Trp53", None, None)
        client.summary.return_value = SummaryResult(
            "gene",
            (
                {"uid": "22059", "name": "TP53", "organism": {"taxid": 10090, "commonname": "house mouse", "scientificname": "Mus musculus"}},
            ),
        )

        result = resolve_gene_identifier("TP53", "human", client=client)

        self.assertEqual(result["resolution_status"], "not_found")
        self.assertIsNone(result["resolved"])

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
