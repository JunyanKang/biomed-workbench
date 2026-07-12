import unittest

from biomed_workbench.capabilities.molecular import (
    back_translate,
    crispr_guides,
    design_primers,
    restriction_sites,
)


class MolecularCapabilityTests(unittest.TestCase):
    def test_primer_design_returns_facing_pair_with_quality_metrics(self):
        template = "GCGTACGATCGATGCTAGCTAGGCTAACGTTAGCGATCGTACGATCGATGCTAGCATCGATGCGTACGATCG"
        result = design_primers(template, min_length=18, max_length=22, target_tm=58.0, max_pairs=3)

        self.assertTrue(result["pairs"])
        pair = result["pairs"][0]
        self.assertTrue(pair["forward"]["sequence"] in template)
        self.assertGreaterEqual(pair["amplicon_length"], 36)
        self.assertLessEqual(abs(pair["forward"]["tm_c"] - pair["reverse"]["tm_c"]), 5.0)
        self.assertIn("off-target", " ".join(result["limitations"]).lower())

    def test_crispr_guides_find_forward_and_reverse_pam_contexts(self):
        sequence = "AAA" + "GACTGACTGACTGACTGACT" + "TGG" + "TTT" + "CCA" + "AGTCAGTCAGTCAGTCAGTC" + "AAA"
        result = crispr_guides(sequence, guide_length=20)

        strands = {guide["strand"] for guide in result["guides"]}
        self.assertEqual(strands, {"+", "-"})
        self.assertTrue(all(len(guide["guide"]) == 20 for guide in result["guides"]))
        self.assertTrue(all(guide["pam"].endswith("GG") for guide in result["guides"] if guide["strand"] == "+"))

    def test_restriction_sites_report_one_based_cut_context(self):
        result = restriction_sites("AAAAGAATTCTTTGAATTC", enzymes=["EcoRI"])

        self.assertEqual([site["start"] for site in result["sites"]], [5, 14])
        self.assertEqual(result["sites"][0]["motif"], "GAATTC")

    def test_back_translation_is_deterministic_and_round_trips(self):
        result = back_translate("MKW", organism="human")

        self.assertEqual(result["dna"], "ATGAAGTGG")
        self.assertEqual(result["protein"], "MKW")
        self.assertEqual(result["organism"], "human")


if __name__ == "__main__":
    unittest.main()
