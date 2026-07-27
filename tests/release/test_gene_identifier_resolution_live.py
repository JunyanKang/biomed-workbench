import unittest
from biomed_workbench.services.eutils import EUtilitiesError

from biomed_workbench.capabilities.evidence import resolve_gene_identifier


class GeneIdentifierResolutionLiveTests(unittest.TestCase):
    def test_ncbi_tp53_human_resolution_is_exact_and_reusable(self):
        try:
            result = resolve_gene_identifier("TP53", "human")
        except EUtilitiesError as exc:
            self.skipTest(f"NCBI network unavailable: {exc}")

        self.assertEqual(result["resolution_status"], "resolved")
        self.assertEqual(result["resolved"]["gene_id"], "7157")
        self.assertEqual(result["resolved"]["taxon_id"], "9606")
        self.assertEqual(result["resolved"]["symbol"], "TP53")


if __name__ == "__main__":
    unittest.main()
