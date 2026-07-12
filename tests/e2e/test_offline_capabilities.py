import json
import math
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def execute(capability_id, payload):
    result = subprocess.run(
        [sys.executable, "tools/run_tool.py", capability_id, "--input", json.dumps(payload)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    parsed = json.loads(result.stdout)
    if parsed["status"] != "completed":
        raise AssertionError(parsed)
    return parsed["output"]


class OfflineCapabilityE2ETests(unittest.TestCase):
    def test_sequence_inspect(self):
        output = execute("sequence-inspect", {"sequence": "ATGCGC", "alphabet": "dna"})
        self.assertAlmostEqual(output["gc_percent"], 66.666667)

    def test_data_profile(self):
        output = execute("data-profile", {"rows": [{"sample": "A", "count": 1}, {"sample": "B", "count": None}]})
        self.assertEqual(output["columns"]["count"]["missing_count"], 1)

    def test_primer_design(self):
        output = execute(
            "primer-design",
            {"template": "GCGTACGATCGATGCTAGCTAGGCTAACGTTAGCGATCGTACGATCGATGCTAGCATCGATGCGTACGATCG", "max_pairs": 2},
        )
        self.assertEqual(len(output["pairs"]), 2)

    def test_crispr_design(self):
        output = execute("crispr-design", {"sequence": "AAAGACTGACTGACTGACTGACTTGGTTT"})
        self.assertGreaterEqual(len(output["guides"]), 1)

    def test_restriction_plan(self):
        output = execute("restriction-plan", {"sequence": "AAAAGAATTCTTT", "enzymes": ["EcoRI"]})
        self.assertEqual(output["sites"][0]["start"], 5)

    def test_sequence_back_translate(self):
        output = execute("sequence-back-translate", {"protein": "MKW", "organism": "human"})
        self.assertEqual(output["dna"], "ATGAAGTGG")

    def test_dilution_plan(self):
        output = execute(
            "dilution-plan",
            {"initial_concentration": 100, "dilution_factor": 10, "steps": 2, "final_volume_ul": 1000},
        )
        self.assertEqual(output["steps"][-1]["concentration"], 1.0)

    def test_pcr_plan(self):
        output = execute(
            "pcr-plan",
            {
                "reactions": 8,
                "reaction_volume_ul": 20,
                "components": {"master_mix": 10, "forward_primer": 1, "reverse_primer": 1, "template": 2},
                "overage_percent": 10,
            },
        )
        self.assertAlmostEqual(output["master_mix"]["water"], 52.8)

    def test_dose_response(self):
        output = execute(
            "dose-response",
            {"concentrations": [0.1, 1, 10, 100], "responses": [98, 80, 20, 2], "direction": "decreasing"},
        )
        self.assertTrue(output["monotonic"])

    def test_growth_curve(self):
        output = execute(
            "growth-curve",
            {"times": [0, 1, 2, 3], "values": [0.05 * math.exp(0.7 * time) for time in range(4)], "window": 3},
        )
        self.assertAlmostEqual(output["max_growth_rate_per_time"], 0.7, places=6)

    def test_expression_qc(self):
        output = execute("expression-qc", {"genes": ["A", "B"], "samples": ["S1", "S2"], "matrix": [[10, 0], [5, 5]]})
        self.assertEqual(output["library_sizes"]["S1"], 15.0)

    def test_differential_expression(self):
        output = execute("differential-expression", {"genes": ["G"], "group_a": [[10, 11, 12]], "group_b": [[1, 2, 3]]})
        self.assertGreater(output["results"][0]["log2_fold_change"], 2)

    def test_enrichment_analysis(self):
        output = execute("enrichment-analysis", {"query_genes": ["A", "B"], "gene_sets": {"P": ["A", "B", "C"]}, "background_genes": ["A", "B", "C", "D", "E"]})
        self.assertEqual(output["results"][0]["overlap_count"], 2)

    def test_single_cell_qc(self):
        output = execute("single-cell-qc", {"genes": ["MT-A", "B"], "cells": ["c1"], "matrix": [[5], [5]], "min_counts": 1, "min_genes": 1, "max_mito_percent": 40})
        self.assertIn("high_mitochondrial_fraction", output["cells"][0]["flags"])

    def test_variant_summary(self):
        output = execute("variant-summary", {"variants": [{"chrom": "1", "ref": "A", "alt": "G", "filter": "PASS"}]})
        self.assertEqual(output["transition_count"], 1)

    def test_network_analysis(self):
        output = execute("network-analysis", {"edges": [["A", "B"], ["B", "C"]]})
        self.assertEqual(output["hubs"][0]["node"], "B")

    def test_image_profile(self):
        output = execute("image-profile", {"image": [[0, 1], [2, 3]]})
        self.assertEqual(output["mean"], 1.5)

    def test_image_segment(self):
        output = execute("image-segment", {"image": [[0, 5], [0, 5]], "threshold": 4, "connectivity": 4})
        self.assertEqual(output["components"][0]["area"], 2)

    def test_image_colocalization(self):
        output = execute("image-colocalization", {"channel_a": [[0, 1], [2, 3]], "channel_b": [[0, 2], [4, 6]]})
        self.assertAlmostEqual(output["pearson_r"], 1.0)

    def test_point_tracking(self):
        output = execute("point-tracking", {"frames": [[[0, 0]], [[1, 0]], [[2, 0]]], "max_distance": 2})
        self.assertEqual(len(output["tracks"][0]["points"]), 3)

    def test_clinical_deidentify(self):
        output = execute("clinical-deidentify", {"record": {"patient_name": "Jane", "note": "jane@example.org"}})
        self.assertNotIn("jane@example.org", str(output["record"]))

    def test_cohort_summary(self):
        output = execute("cohort-summary", {"records": [{"age": 20, "sex": "F"}, {"age": 40, "sex": "M"}], "continuous": ["age"], "categorical": ["sex"]})
        self.assertEqual(output["continuous"]["age"]["median"], 30.0)

    def test_biomarker_performance(self):
        output = execute("biomarker-performance", {"labels": [0, 0, 1, 1], "scores": [0.1, 0.4, 0.35, 0.8], "threshold": 0.3})
        self.assertAlmostEqual(output["roc_auc"], 0.75)

    def test_survival_analysis(self):
        output = execute("survival-analysis", {"durations": [1, 2, 2, 3], "events": [1, 1, 0, 1]})
        self.assertEqual(output["median_survival"], 2.0)

    def test_clinical_report_audit(self):
        output = execute("clinical-report-audit", {"text": "Title Abstract Case presentation Timeline Diagnosis Treatment Follow-up Consent", "standard": "CARE"})
        self.assertIn("timeline", output["present_sections"])

    def test_manuscript_audit(self):
        output = execute("manuscript-audit", {"sections": {"abstract":"A","introduction":"I","results":"R","discussion":"D","methods":"M"}, "claims": [{"claim":"C","citation_count":1,"evidence":"experiment"}], "figure_count": 1, "data_availability": True, "code_availability": True})
        self.assertTrue(output["ready"])

    def test_citation_audit(self):
        output = execute("citation-audit", {"references": [{"authors":"A","title":"T","year":2020,"journal":"J","doi":"10.1000/x"}]})
        self.assertEqual(output["complete_count"], 1)

    def test_response_matrix(self):
        output = execute("response-matrix", {"comments": [{"reviewer":"1","comment":"C","response":"R","action":"A","status":"completed"}]})
        self.assertEqual(output["unresolved_indices"], [])

    def test_figure_specification(self):
        output = execute("figure-specification", {"title":"F","panels":[{"label":"a","claim":"C","data_source":"D","plot":"scatter"}]})
        self.assertTrue(output["ready"])

    def test_patent_disclosure_audit(self):
        output = execute("patent-disclosure-audit", {"problem":"P","solution":"S","essential_features":["E"],"examples":["X"],"alternatives":["A"],"prior_art":["R"]})
        self.assertTrue(output["ready_for_claim_drafting"])


if __name__ == "__main__":
    unittest.main()
