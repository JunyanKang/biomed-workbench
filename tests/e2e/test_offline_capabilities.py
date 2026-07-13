import json
import math
import subprocess
import sys
import unittest
from pathlib import Path

from biomed_workbench.capabilities.revision import build_revision_base


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


def execute_first_module_case(capability_id):
    case_path = ROOT / "biomed_workbench" / "modules" / "builtin" / capability_id / "tests" / "cases.json"
    payload = json.loads(case_path.read_text(encoding="utf-8"))["cases"][0]["input"]
    return execute(capability_id, payload)


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

    def test_single_cell_foundation_workflow(self):
        output = execute("single-cell-foundation-workflow", {
            "objective": "Establish a quality-controlled single-cell RNA-seq object for donor-aware analysis.",
            "input_artifact_id": "artifact-scrna-raw", "input_format": "h5ad", "assay_type": "sc-rna",
            "species": "Homo sapiens", "biological_sample_key": "donor_id", "batch_keys": ["library_id"],
            "raw_count_location": "layers.counts", "requested_backend": "auto", "expected_modalities": ["rna"],
            "declared_thresholds": {}, "design_notes": "Four donors per condition; library is nested within donor."
        })
        self.assertEqual(output["handoff_type"], "codex_generated_project_analysis")
        self.assertTrue(output["execution_policy"]["observed_execution_required"])
        self.assertTrue(output["execution_policy"]["planned_output_is_not_evidence"])
        self.assertEqual({item["name"] for item in output["tool_profiles"]}, {"scanpy", "seurat"})

    def test_variant_summary(self):
        output = execute("variant-summary", {"variants": [{"chrom": "1", "ref": "A", "alt": "G", "filter": "PASS"}]})
        self.assertEqual(output["transition_count"], 1)

    def test_network_analysis(self):
        output = execute("network-analysis", {"edges": [["A", "B"], ["B", "C"]]})
        self.assertEqual(output["hubs"][0]["node"], "B")

    def test_multi_sample_variant_concordance(self):
        output = execute("multi-sample-variant-concordance", {
            "samples": ["S1", "S2", "S3"],
            "reference_build": "GRCh38",
            "reference_sequence_digest": "a" * 64,
            "normalization": "split-left-normalized-biallelic",
            "variants": [
                {"chrom": "1", "position": 100, "ref": "A", "alt": "G", "states": {"S1": "alternate", "S2": "alternate", "S3": "not_callable"}, "phases": {"S1": {"phase_set": "PS1", "haplotypes": [1]}, "S2": {"phase_set": "PS1", "haplotypes": [1, 2]}}},
                {"chrom": "1", "position": 120, "ref": "C", "alt": "T", "states": {"S1": "alternate", "S2": "reference", "S3": "reference"}},
            ],
        })
        pair = output["pairwise"][0]
        self.assertEqual(pair["jointly_callable_count"], 2)
        self.assertEqual(pair["shared_alternate_count"], 1)
        self.assertEqual(output["sample_summaries"][2]["not_callable_count"], 1)
        self.assertEqual(len(output["haplotype_signatures"]), 2)

    def test_ddr_coexpression_hypothesis_network(self):
        output = execute("ddr-coexpression-hypothesis-network", {
            "sample_ids": [f"S{i}" for i in range(1, 9)],
            "expression": {
                "ATM": [1, 2, 3, 4, 5, 6, 7, 8],
                "CHEK2": [2, 4, 6, 8, 10, 12, 14, 16],
                "MKI67": [8, 1, 7, 2, 6, 3, 5, 4]
            },
            "ddr_genes": ["ATM", "CHEK2"],
            "mutated_samples": {"ATM": ["S1", "S2"]},
            "method": "spearman",
            "minimum_paired_samples": 8,
            "minimum_absolute_correlation": 0.9,
            "false_discovery_rate": 0.05
        })
        self.assertEqual(output["edge_count"], 1)
        self.assertEqual(output["functional_dependency_hypotheses"][0]["interpretation"], "functional_dependency_hypothesis_requires_independent_perturbation_evidence")
        self.assertIn("not synthetic lethality", output["limitations"][0])

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

    def test_assertion_citation_coverage_audit(self):
        output = execute_first_module_case("assertion-citation-coverage-audit")
        self.assertEqual(output["uncovered_candidate_count"], 1)
        self.assertEqual(output["overall_status"], "blocked")

    def test_claim_evidence_integrity_audit(self):
        output = execute_first_module_case("claim-evidence-integrity-audit")
        self.assertEqual(output["overall_status"], "passed")
        self.assertEqual(output["claim_results"][0]["claim_state"], "supported")

    def test_temporal_integrity_audit(self):
        output = execute_first_module_case("temporal-integrity-audit")
        self.assertEqual(output["overall_status"], "blocked")
        self.assertEqual(output["assertion_results"][0]["issues"][0]["code"], "TEMPORAL_ANACHRONISTIC_SOURCE")

    def test_response_matrix(self):
        output = execute("response-matrix", {"comments": [{"reviewer":"1","comment":"C","response":"R","action":"A","status":"completed"}]})
        self.assertEqual(output["unresolved_indices"], [])

    def test_manuscript_revision_base(self):
        output = execute("manuscript-revision-base", {
            "document_id": "paper-base-e2e", "version_id": "v1",
            "blocks": [
                {"id": None, "kind": "heading", "text": "Results"},
                {"id": "B00009", "kind": "paragraph", "text": "Existing result."},
                {"id": None, "kind": "paragraph", "text": "Validation result.\n"},
            ],
        })
        self.assertEqual([block["id"] for block in output["blocks"]], ["B00010", "B00009", "B00011"])
        self.assertRegex(output["document_hash"], r"^[0-9a-f]{64}$")

    def test_manuscript_revision_lineage(self):
        base = build_revision_base("paper-e2e", "v1", [
            {"id": "B00001", "kind": "heading", "text": "Results"},
            {"id": "B00002", "kind": "paragraph", "text": "The marker caused the phenotype."},
            {"id": "B00003", "kind": "paragraph", "text": "An independent analysis was performed."},
        ])
        payload = {
            "base_document": base,
            "patch": {
                "patch_id": "patch-e2e", "revision_round": 1, "base_document_hash": base["document_hash"],
                "emitted_by": "revision-writer", "operations": [{
                    "op_id": "op-e2e", "op": "replace_block", "target_block_id": "B00002",
                    "expected_block_hash": base["blocks"][1]["hash"],
                    "new_blocks": [{"kind": "paragraph", "text": "The marker was associated with the phenotype."}],
                    "comment_ids": ["R1.1"], "roadmap_item_ids": ["roadmap-1"],
                    "rationale": "Match claim strength to the supplied independent analysis."
                }]
            },
            "review_items": [{
                "id": "R1.1", "reviewer": "Reviewer 1", "comment": "Validate or soften the causal claim.",
                "action": "ACCEPT_ANALYSIS", "readiness": "ready_to_submit", "risk_level": "high",
                "manuscript_block_ids": ["B00002"], "evidence_ids": ["analysis-e2e"],
                "response_text": "We added the independent analysis and revised the statement to describe an association.",
                "status": "completed", "conflicting_with": []
            }],
            "policy": {"structural_acknowledged": False, "touched_ratio_threshold": 0.6, "terminal_policy": "strict", "editor_priority_comment_ids": []},
            "audit_provenance": {"audit_id": "audit-e2e", "audit_version": "1.0.0", "reviewed_at": "2026-07-13", "independent_from_writer": True, "comment_extraction_complete": True}
        }
        output = execute("manuscript-revision-lineage", payload)
        self.assertEqual(output["apply_status"], "applied")
        self.assertTrue(output["release_safe"])
        self.assertEqual(output["revised_document"]["parent_document_hash"], base["document_hash"])

    def test_figure_specification(self):
        output = execute("figure-specification", {"title":"F","panels":[{"label":"a","claim":"C","data_source":"D","plot":"scatter"}]})
        self.assertTrue(output["ready"])

    def test_patent_disclosure_audit(self):
        output = execute("patent-disclosure-audit", {"problem":"P","solution":"S","essential_features":["E"],"examples":["X"],"alternatives":["A"],"prior_art":["R"]})
        self.assertTrue(output["ready_for_claim_drafting"])

    def test_qpcr_relative_expression(self):
        measurements = [
            {"sample": sample, "assay": assay, "ct": ct}
            for sample, assay, values in (
                ("control", "target", [20.0, 20.2]), ("control", "ref", [16.0, 16.2]),
                ("treated", "target", [18.0, 18.2]), ("treated", "ref", [16.0, 16.2]),
            )
            for ct in values
        ]
        output = execute("qpcr-relative-expression", {"measurements": measurements, "target_assay": "target", "reference_assays": ["ref"], "calibrator_samples": ["control"]})
        treated = next(row for row in output["samples"] if row["sample"] == "treated")
        self.assertAlmostEqual(treated["relative_expression"], 4.0)

    def test_immunoassay_quantification(self):
        standards = [{"concentration": x, "response": 0.1 + 0.4 * x} for x in [0, 1, 2, 3]]
        output = execute("immunoassay-quantification", {"standards": standards, "unknowns": [{"sample": "u1", "response": 0.7, "dilution_factor": 2}]})
        self.assertAlmostEqual(output["unknowns"][0]["reported_concentration"], 3.0)

    def test_flow_cytometry_summary(self):
        output = execute("flow-cytometry-summary", {
            "events": [{"FSC": 100, "CD3": 5}, {"FSC": 120, "CD3": 12}, {"FSC": 10, "CD3": 20}],
            "gates": [{"name": "cells", "parent": "all", "conditions": {"FSC": {"min": 50}}}, {"name": "positive", "parent": "cells", "conditions": {"CD3": {"min": 10}}}],
        })
        self.assertEqual(output["gates"][-1]["event_count"], 1)

    def test_enzyme_kinetics(self):
        output = execute("enzyme-kinetics", {"observations": [{"substrate": s, "velocity": 10 * s / (3 + s)} for s in [0.5, 1, 2, 5, 10, 20]]})
        self.assertAlmostEqual(output["parameters"]["km"], 3.0, places=4)

    def test_glycosylation_scan(self):
        output = execute("glycosylation-scan", {"protein": "MANVTNPSNAT", "context_radius": 2})
        self.assertEqual([row["start"] for row in output["n_linked_sequons"]], [3, 9])

    def test_golden_gate_plan(self):
        output = execute("golden-gate-plan", {"fragments": [
            {"name": "a", "sequence": "ATGCGCAT", "left_overhang": "AATG", "right_overhang": "GGCT"},
            {"name": "b", "sequence": "ATGAAATAG", "left_overhang": "GGCT", "right_overhang": "CGCT"},
        ]})
        self.assertTrue(output["assembly_ready"])

    def test_tumor_mutation_burden(self):
        output = execute("tumor-mutation-burden", {"variants": [{"id": "v1", "effect": "missense", "filter": "PASS", "allele_fraction": 0.2, "somatic": True}], "callable_megabases": 2})
        self.assertEqual(output["tmb_mutations_per_mb"], 0.5)

    def test_adverse_event_summary(self):
        output = execute("adverse-event-summary", {"events": [{"participant": "p1", "term": "Nausea", "grade": 2, "serious": False, "relatedness": "possible"}], "enrolled_participants": 4})
        self.assertEqual(output["by_term"]["Nausea"]["participant_incidence_percent"], 25.0)

    def test_reviewer_assessment(self):
        output = execute("reviewer-assessment", {"claims": [{"id": "c1", "claim": "Marker causally drives fate", "evidence_design": "observational", "replicated": False}], "review_domains": {"methods_reproducible": False, "statistics_adequate": True, "data_available": True, "ethics_resolved": True}, "novelty": "high"})
        self.assertEqual(output["recommendation"], "major_revision")


if __name__ == "__main__":
    unittest.main()
