import unittest
from biomed_workbench.capabilities.evidence import gene_ortholog_evidence
from biomed_workbench.services.eutils import EUtilitiesError
from biomed_workbench.services.public_databases import PublicDatabaseError

class GeneOrthologEvidenceLiveTests(unittest.TestCase):
    def test_ncbi_tp53_to_mouse_record_is_bounded_and_explicit(self):
        try:
            result = gene_ortholog_evidence("7157",10090,10)
        except (EUtilitiesError, PublicDatabaseError) as exc:
            self.skipTest(f"NCBI network unavailable: {exc}")
        self.assertEqual(result["source"]["symbol"],"TP53")
        self.assertEqual(result["target_taxon_id"],"10090")
        self.assertEqual(result["total_target_orthologs"],1)
        self.assertEqual(result["orthologs"][0]["symbol"],"Trp53")
        self.assertEqual(result["orthologs"][0]["gene_id"],"22059")
        self.assertEqual(result["orthologs"][0]["ensembl_gene_ids"],["ENSMUSG00000059552"])

if __name__=="__main__": unittest.main()
