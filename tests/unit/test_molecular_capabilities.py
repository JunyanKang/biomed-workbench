import unittest

from biomed_workbench.capabilities.molecular import (
    annotate_open_reading_frames,
    back_translate,
    crispr_guides,
    design_primers,
    extract_genbank_coding_sequences,
    localize_sequence_variants,
    simulate_pcr_amplicons,
    select_pcr_primer_pair,
    summarize_rna_secondary_structure,
    summarize_aligned_protein_conservation,
    summarize_cd_thermal_transition,
    pairwise_sequence_alignment,
    plan_sanger_verification_coverage,
    restriction_sites,
    screen_primer_pair_specificity,
    simulate_restriction_digest,
)


class MolecularCapabilityTests(unittest.TestCase):
    def test_primer_pair_specificity_reports_panel_off_targets_without_overclaiming(self):
        result = screen_primer_pair_specificity(
            "AAAACCCCGG",
            "AGCTACGATC",
            [
                {"id": "intended", "sequence": "AAAACCCCGGGGTTTTACGATCGTAGCT"},
                {"id": "off_target", "sequence": "AAAACCCCGGGGTTTTACGATCGTAGCT"},
                {"id": "negative", "sequence": "TTTTGGGGCCCCAAAATTTT"},
            ],
            "intended",
        )
        self.assertEqual(result["intended_product_count"], 1)
        self.assertEqual(result["off_target_reference_ids"], ["off_target"])
        self.assertEqual(result["specificity_status"], "not-specific-within-declared-panel")

    def test_sanger_verification_coverage_reuses_exact_existing_primer(self):
        template = "GCGTACGATCGATGCTAGCT" * 8
        result = plan_sanger_verification_coverage(
            template,
            target_start=0,
            target_end=100,
            existing_primers=[{"name": "project_forward", "sequence": template[:20]}],
            read_length=120,
            coverage_overlap=20,
            primer_length=20,
        )
        self.assertTrue(result["target_fully_covered"])
        self.assertEqual(result["recommended_primers"][0]["name"], "project_forward")
        self.assertEqual(result["recommended_primers"][0]["source"], "existing")

    def test_sanger_verification_coverage_designs_traceable_linear_read_plan(self):
        template = "GCGTACGATCGATGCTAGCT" * 100
        result = plan_sanger_verification_coverage(
            template,
            target_start=200,
            target_end=1300,
            read_length=700,
            coverage_overlap=100,
            primer_length=20,
        )
        self.assertTrue(result["target_fully_covered"])
        self.assertEqual(result["merged_target_coverage"], [{"start": 200, "end": 1300}])
        self.assertTrue(all(primer["source"] == "designed" for primer in result["recommended_primers"]))

    def test_primer_pair_selection_binds_ranked_candidate_to_explicit_pcr_request(self):
        designed = design_primers("GCGTACGATCGATGCTAGCTAGGCTAACGTTAGCGATCGTACGATCGATGCTAGCATCGATGCGTACGATCG", min_length=18, max_length=18, max_pairs=1)
        request = select_pcr_primer_pair(designed["template"], designed["pairs"])
        self.assertEqual(request["selected_candidate_index"], 0)
        self.assertEqual(request["template"], designed["template"])
        self.assertEqual(request["forward_primer"], designed["pairs"][0]["forward"]["sequence"])
    def test_cd_thermal_transition_reports_interpolated_midpoint_and_width(self):
        result = summarize_cd_thermal_transition([20, 30, 40, 50, 60], [10, 20, 50, 80, 90])
        self.assertEqual(result["summary"]["transition_midpoint_c"], 40.0)
        self.assertEqual(result["summary"]["transition_10_percent_c"], 28.0)
        self.assertEqual(result["summary"]["transition_90_percent_c"], 52.0)
        self.assertEqual(result["summary"]["monotonicity_violation_count"], 0)

    def test_aligned_protein_conservation_reports_coverage_consensus_and_entropy(self):
        result = summarize_aligned_protein_conservation(["MKT-", "MRTQ", "MKTQ"], ["a", "b", "c"])
        self.assertEqual(result["summary"]["fully_conserved_column_count"], 2)
        self.assertEqual(result["columns"][1]["consensus_residue"], "K")
        self.assertEqual(result["columns"][1]["consensus_fraction"], 0.66666667)
        self.assertEqual(result["columns"][3]["coverage_fraction"], 0.66666667)

    def test_rna_secondary_structure_summary_validates_pairs_stems_and_sequence_classes(self):
        result = summarize_rna_secondary_structure("(((...)))", "GGGAAACCC")
        self.assertEqual(result["summary"]["base_pair_count"], 3)
        self.assertEqual(result["summary"]["stem_count"], 1)
        self.assertEqual(result["summary"]["pair_classes"]["GC"], 3)
        self.assertEqual(result["stems"][0]["pair_count"], 3)

    def test_rna_secondary_structure_rejects_unbalanced_notation(self):
        with self.assertRaisesRegex(ValueError, "unmatched"):
            summarize_rna_secondary_structure("((..)")

    def test_pcr_simulation_reports_linear_and_circular_exact_products(self):
        template = "AAAACCCCGGGGTTTTACGATCGTAGCT"
        linear = simulate_pcr_amplicons(template, "AAAACCCCGG", "AGCTACGATC")
        self.assertEqual(linear["forward_binding_site_count"], 1)
        self.assertEqual(linear["reverse_binding_site_count"], 1)
        self.assertEqual(linear["products"][0]["amplicon_length"], 28)
        self.assertFalse(linear["products"][0]["wraps_origin"])

        circular = simulate_pcr_amplicons("GATCGTAGCTAAAACCCCGGGGTTTT", "AAAACCCCGG", "AGCTACGATC", circular=True)
        self.assertEqual(len(circular["products"]), 1)
        self.assertTrue(circular["products"][0]["wraps_origin"])

    def test_sequence_variant_localization_reports_substitution_insertion_and_deletion_intervals(self):
        substitution = localize_sequence_variants("ACGT", "ATGT", reference_coordinate_offset=100)
        self.assertEqual(substitution["events"], [{
            "event_type": "substitution",
            "reference_interval": {"start": 101, "end": 102},
            "reference_sequence": "C",
            "alternate_sequence": "T",
        }])

        insertion = localize_sequence_variants("ACGA", "ACGTA")
        deletion = localize_sequence_variants("ACGT", "AGT")
        self.assertEqual(insertion["events"][0]["event_type"], "insertion")
        self.assertEqual(insertion["events"][0]["reference_interval"], {"start": 3, "end": 3})
        self.assertEqual(insertion["events"][0]["alternate_sequence"], "T")
        self.assertEqual(deletion["events"][0], {
            "event_type": "deletion",
            "reference_interval": {"start": 1, "end": 2},
            "reference_sequence": "C",
            "alternate_sequence": "",
        })

    def test_orf_annotation_reports_forward_and_reverse_half_open_coordinates(self):
        result = annotate_open_reading_frames("ATGAAATAATTATTTCAT", min_length=9, filter_nested=False)

        self.assertEqual(result["summary"]["total_orf_count"], 2)
        self.assertEqual(result["coordinate_system"], "zero-based half-open on supplied forward DNA sequence")
        self.assertEqual(result["orfs"], [
            {"start": 0, "end": 9, "strand": "+", "frame": 1, "length": 9, "sequence": "ATGAAATAA", "protein_sequence": "MK", "terminal_stop_codon": "TAA"},
            {"start": 9, "end": 18, "strand": "-", "frame": -1, "length": 9, "sequence": "ATGAAATAA", "protein_sequence": "MK", "terminal_stop_codon": "TAA"},
        ])

    def test_orf_annotation_rejects_ambiguous_or_unframed_minimum_length(self):
        with self.assertRaisesRegex(ValueError, "unambiguous"):
            annotate_open_reading_frames("ATGNAA")
        with self.assertRaisesRegex(ValueError, "divisible"):
            annotate_open_reading_frames("ATGAAATAA", min_length=8)

    def test_pairwise_alignment_reports_scoring_identity_and_half_open_blocks(self):
        result = pairwise_sequence_alignment("ACGT", "AGT", alphabet="dna")

        self.assertEqual(result["reference_aligned"], "ACGT")
        self.assertEqual(result["query_aligned"], "A-GT")
        self.assertEqual(result["exact_match_count"], 3)
        self.assertEqual(result["mismatch_count"], 0)
        self.assertEqual(result["gap_count"], 1)
        self.assertEqual(result["identity_fraction"], 1.0)
        self.assertEqual(result["coordinate_system"], "zero-based half-open")
        self.assertEqual(result["aligned_blocks"], [
            {"reference_start": 0, "reference_end": 1, "query_start": 0, "query_end": 1},
            {"reference_start": 2, "reference_end": 4, "query_start": 1, "query_end": 3},
        ])

    def test_pairwise_alignment_rejects_ambiguous_or_invalid_scoring_contracts(self):
        with self.assertRaisesRegex(ValueError, "unambiguous"):
            pairwise_sequence_alignment("ACGN", "ACGT")
        with self.assertRaisesRegex(ValueError, "gap scores"):
            pairwise_sequence_alignment("ACGT", "ACGT", open_gap_score=1.0)

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

    def test_restriction_digest_reports_linear_fragments_and_circular_origin_wrap(self):
        sequence = "AAAAGAATTCTTTGAATTC"
        linear = simulate_restriction_digest(sequence, ["EcoRI"])
        circular = simulate_restriction_digest(sequence, ["EcoRI"], circular=True)

        self.assertEqual(linear["unique_cut_count"], 2)
        self.assertEqual([fragment["length"] for fragment in linear["fragments"]], [9, 5, 5])
        self.assertEqual(circular["digestion_state"], "fragmented")
        self.assertEqual([fragment["length"] for fragment in circular["fragments"]], [10, 9])
        self.assertTrue(any(fragment["wraps_origin"] for fragment in circular["fragments"]))

    def test_restriction_site_module_can_attach_digest_without_changing_default_shape(self):
        result = restriction_sites("AAAAGAATTCTTTGAATTC", enzymes=["EcoRI"], include_digest=True, circular=False)

        self.assertEqual(result["digest"]["cut_sites"][0]["cut_position"], 5)
        self.assertEqual(result["digest"]["digestion_state"], "fragmented")

    def test_genbank_coding_sequence_extraction_matches_annotated_cds_and_checks_translation(self):
        record = """LOCUS       TESTREC                   39 bp    DNA     linear   SYN 01-JAN-2000
DEFINITION  synthetic test record.
ACCESSION   TEST000001
VERSION     TEST000001.1
FEATURES             Location/Qualifiers
     source          1..39
                     /organism="synthetic construct"
     CDS             4..15
                     /gene="testgene"
                     /locus_tag="LT0001"
                     /protein_id="TEST_0001"
                     /codon_start=1
                     /transl_table=1
                     /translation="MKF"
ORIGIN
        1 cccatgaaat tttaaacccc ggggttttaa acccgggtt
//
"""
        result = extract_genbank_coding_sequences(record, "LT0001")

        self.assertEqual(result["matched_cds_count"], 1)
        cds = result["coding_sequences"][0]
        self.assertEqual(cds["coding_sequence"], "ATGAAATTTTAA")
        self.assertEqual(cds["location_intervals"], [{"start": 3, "end": 15}])
        self.assertEqual(cds["translated_protein"], "MKF")
        self.assertTrue(cds["translation_match"])

    def test_back_translation_is_deterministic_and_round_trips(self):
        result = back_translate("MKW", organism="human")

        self.assertEqual(result["dna"], "ATGAAGTGG")
        self.assertEqual(result["protein"], "MKW")
        self.assertEqual(result["organism"], "human")


if __name__ == "__main__":
    unittest.main()
