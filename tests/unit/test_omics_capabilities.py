import unittest

from biomed_workbench.capabilities.omics import (
    differential_expression,
    enrichment_analysis,
    expression_qc,
    network_summary,
    single_cell_qc,
    variant_summary,
)


class OmicsCapabilityTests(unittest.TestCase):
    def test_expression_qc_reports_library_and_detection_metrics(self):
        result = expression_qc(
            genes=["A", "B", "C"],
            samples=["S1", "S2"],
            matrix=[[10, 0], [5, 5], [0, 15]],
        )
        self.assertEqual(result["library_sizes"], {"S1": 15.0, "S2": 20.0})
        self.assertEqual(result["detected_genes"], {"S1": 2, "S2": 2})
        self.assertEqual(result["zero_fraction"], 2 / 6)

    def test_differential_expression_ranks_effect_and_controls_fdr(self):
        result = differential_expression(
            genes=["up", "flat"],
            group_a=[[10, 11, 12, 13, 14], [5, 5, 5, 5, 5]],
            group_b=[[1, 2, 3, 4, 5], [5, 5, 5, 5, 5]],
            pseudocount=0.5,
        )
        by_gene = {row["gene"]: row for row in result["results"]}
        self.assertGreater(by_gene["up"]["log2_fold_change"], 1)
        self.assertLess(by_gene["up"]["adjusted_p_value"], 0.01)
        self.assertEqual(by_gene["flat"]["p_value"], 1.0)

    def test_enrichment_uses_background_and_bh_correction(self):
        result = enrichment_analysis(
            query_genes=["A", "B", "C"],
            gene_sets={"pathway_1": ["A", "B", "X"], "pathway_2": ["Y", "Z"]},
            background_genes=["A", "B", "C", "X", "Y", "Z", "Q", "R"],
        )
        rows = {row["term"]: row for row in result["results"]}
        self.assertEqual(rows["pathway_1"]["overlap_genes"], ["A", "B"])
        self.assertGreater(rows["pathway_1"]["fold_enrichment"], 1)
        self.assertEqual(rows["pathway_2"]["overlap_count"], 0)

    def test_single_cell_qc_computes_cell_metrics_and_threshold_flags(self):
        result = single_cell_qc(
            genes=["MT-A", "B", "C"],
            cells=["c1", "c2"],
            matrix=[[5, 0], [5, 1], [0, 1]],
            mitochondrial_prefixes=["MT-"],
            min_counts=3,
            max_mito_percent=40,
        )
        cells = {row["cell"]: row for row in result["cells"]}
        self.assertEqual(cells["c1"]["mitochondrial_percent"], 50.0)
        self.assertIn("high_mitochondrial_fraction", cells["c1"]["flags"])
        self.assertIn("low_counts", cells["c2"]["flags"])

    def test_variant_summary_counts_types_filters_and_titv(self):
        result = variant_summary(
            [
                {"chrom": "1", "ref": "A", "alt": "G", "filter": "PASS"},
                {"chrom": "1", "ref": "C", "alt": "T", "filter": "PASS"},
                {"chrom": "2", "ref": "A", "alt": "C", "filter": "q10"},
                {"chrom": "2", "ref": "A", "alt": "AT", "filter": "PASS"},
            ]
        )
        self.assertEqual(result["type_counts"], {"indel": 1, "snv": 3})
        self.assertEqual(result["transition_count"], 2)
        self.assertEqual(result["transversion_count"], 1)
        self.assertEqual(result["ti_tv_ratio"], 2.0)

    def test_network_summary_finds_components_and_hubs(self):
        result = network_summary(edges=[["A", "B"], ["B", "C"], ["D", "E"]])
        self.assertEqual(result["node_count"], 5)
        self.assertEqual(result["component_count"], 2)
        self.assertEqual(result["degree"]["B"], 2)
        self.assertEqual(result["hubs"][0]["node"], "B")


if __name__ == "__main__":
    unittest.main()
