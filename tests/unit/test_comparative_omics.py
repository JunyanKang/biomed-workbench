import unittest

from biomed_workbench.capabilities.omics import (
    ddr_coexpression_hypothesis_network,
    multi_sample_variant_concordance,
)


class ComparativeOmicsTests(unittest.TestCase):
    def test_not_callable_is_excluded_from_pairwise_denominator(self):
        output = multi_sample_variant_concordance(
            samples=["A", "B"],
            reference_build="GRCh38",
            reference_sequence_digest="b" * 64,
            normalization="split-left-normalized-biallelic",
            variants=[
                {"chrom": "1", "position": 1, "ref": "A", "alt": "C", "states": {"A": "alternate", "B": "not_callable"}},
                {"chrom": "1", "position": 2, "ref": "G", "alt": "T", "states": {"A": "reference", "B": "reference"}},
            ],
        )
        self.assertEqual(output["pairwise"][0]["jointly_callable_count"], 1)
        self.assertEqual(output["pairwise"][0]["genotype_state_concordance"], 1.0)
        self.assertEqual(output["pairwise"][0]["not_jointly_callable_count"], 1)

    def test_missing_sample_state_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly one state"):
            multi_sample_variant_concordance(
                samples=["A", "B"],
                reference_build="GRCh38",
                reference_sequence_digest="c" * 64,
                normalization="split-left-normalized-biallelic",
                variants=[{"chrom": "1", "position": 1, "ref": "A", "alt": "G", "states": {"A": "alternate"}}],
            )

    def test_homozygous_alternate_phase_marks_both_haplotypes(self):
        output = multi_sample_variant_concordance(
            samples=["A", "B"], reference_build="GRCh38",
            reference_sequence_digest="d" * 64,
            normalization="split-left-normalized-biallelic",
            variants=[{"chrom": "1", "position": 3, "ref": "A", "alt": "T", "states": {"A": "alternate", "B": "reference"}, "phases": {"A": {"phase_set": "P1", "haplotypes": [1, 2]}}}],
        )
        signature = output["haplotype_signatures"][0]
        self.assertEqual(signature["haplotype_1_alt_loci"], signature["haplotype_2_alt_loci"])

    def test_ddr_network_requires_multiplicity_and_effect_thresholds(self):
        output = ddr_coexpression_hypothesis_network(
            sample_ids=[f"S{i}" for i in range(8)],
            expression={"ATM": list(range(8)), "CHEK2": [2 * value for value in range(8)], "NOISE": [1, 4, 2, 7, 3, 0, 6, 5]},
            ddr_genes=["ATM", "CHEK2"],
            mutated_samples={"ATM": ["S0"]},
            method="pearson",
            minimum_paired_samples=8,
            minimum_absolute_correlation=0.95,
            false_discovery_rate=0.05,
        )
        self.assertEqual([(edge["gene_a"], edge["gene_b"]) for edge in output["edges"]], [("ATM", "CHEK2")])
        self.assertEqual(len(output["functional_dependency_hypotheses"]), 1)

    def test_ddr_network_does_not_treat_constant_vectors_as_edges(self):
        output = ddr_coexpression_hypothesis_network(
            sample_ids=[f"S{i}" for i in range(6)],
            expression={"ATM": [1, 2, 3, 4, 5, 6], "CONST": [1, 1, 1, 1, 1, 1], "CHEK2": [6, 5, 4, 3, 2, 1]},
            ddr_genes=["ATM"], mutated_samples={}, method="spearman",
            minimum_paired_samples=6, minimum_absolute_correlation=0.9, false_discovery_rate=0.05,
        )
        self.assertEqual(output["tested_pair_count"], 1)
        self.assertEqual(output["edge_count"], 1)


if __name__ == "__main__":
    unittest.main()
